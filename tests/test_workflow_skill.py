"""Full-workflow Skill loading with fake HTTP, real read tools and HDL checks."""
import csv
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, RULES, SequenceProvider, SkillHTTPReplay, TemporaryTestCase
from rtlflow.design import model_call
from rtlflow.pipeline import run_batch, run_task, workflow_skill_report
from rtlflow.providers import GLMProvider
from rtlflow.skill_tools import SKILL_RELOAD_REQUEST, skill_capabilities
from test_design_flow import APPROVE, example
from test_skill_agent import reply

PREPARATION = ('design', 'design_review', 'verification_design', 'verification_review')


class WorkflowSkillTests(TemporaryTestCase):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {'GLM_API_KEY': 'unit-only-workflow'}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        guard = patch('rtlflow.providers.urllib.request.urlopen', side_effect=AssertionError('no live HTTP'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_each_preparation_role_loads_independently_and_routes_tb_language(self):
        messages = [{'role': 'system', 'content': 'Stage protocol.'}, {'role': 'user', 'content': 'Stage input.'}]
        original = json.dumps(messages)
        for language in ('verilog', 'systemverilog', 'chisel'):
            for phase in PREPARATION:
                with self.subTest(language=language, phase=phase):
                    settings = {'group': 'Skill', 'language': language}
                    replay = SkillHTTPReplay(['{}'])
                    directory = self.directory / (language + '-' + phase)
                    with patch('rtlflow.providers.urllib.request.urlopen', side_effect=replay):
                        text, attempt = model_call(GLMProvider(settings), 'unit', messages, directory, phase, settings)
                    self.assertEqual(text, '{}')
                    guide = 'systemverilog' if phase.startswith('verification_') else language
                    self.assertEqual(attempt['skill_language'], guide)
                    meta = attempt['generation_metadata']
                    self.assertTrue(meta['skill_loaded'])
                    self.assertEqual(meta['model_calls'], 3)
                    self.assertEqual(set(meta['skill_documents']), {'SKILL.md', 'rules.md', f'references/{guide}.md'})
                    first = replay.requests[0]
                    self.assertEqual([m['role'] for m in first['messages']], ['system', 'user'])
                    self.assertEqual(first['tools'][0]['function']['parameters']['properties']['path']['enum'], ['SKILL.md'])
                    self.assertIn('请调用 rtl-readable Skill', first['messages'][1]['content'])
                    self.assertNotIn('当前调用仅执行已冻结契约的RTL', first['messages'][0]['content'])
                    self.assertNotIn('## 通用规则', json.dumps(first, ensure_ascii=False))
                    self.assertEqual(json.dumps(messages), original)  # Never mutate another role's base prompt.
        with self.assertRaises(ValueError):
            skill_capabilities('verilog', 'unknown_phase')

    def test_baseline_preparation_never_injects_tools_or_skill_requests(self):
        messages = [{'role': 'system', 'content': 'Only JSON.'}, {'role': 'user', 'content': 'A public task.'}]
        provider = SequenceProvider(['{}'])
        for phase in PREPARATION:
            model_call(provider, 'unit', messages, self.directory / phase, phase, {'group': 'Baseline'})
        self.assertEqual(provider.skills, [None] * 4)
        self.assertEqual(provider.messages, [messages] * 4)

    def test_stage_capabilities_allow_tb_only_in_its_role(self):
        self.assertIn('不新建TB', skill_capabilities('systemverilog'))
        self.assertIn('不写RTL或TB', skill_capabilities('verilog', 'design'))
        self.assertIn('不改写提案', skill_capabilities('chisel', 'design_review'))
        self.assertIn('body/coverage/oracle_description', skill_capabilities('systemverilog', 'verification_design'))
        self.assertIn('有问题必须拒绝', skill_capabilities('systemverilog', 'verification_review'))
        for phase in PREPARATION:
            self.assertIn('不继承其他阶段', skill_capabilities('systemverilog', phase))
            self.assertIn('交付格式以本阶段协议为准', skill_capabilities('systemverilog', phase))

    def test_partial_loading_before_design_is_reported_without_advancing(self):
        task, contract, _, _ = example()
        replay = SkillHTTPReplay([json.dumps(contract)])
        def respond(request, **kwargs):
            body = json.loads(request.data)
            if any(message['role'] == 'tool' for message in body['messages']):
                return reply(json.dumps(contract))  # Only SKILL.md was read; refuse this result.
            return replay(request, **kwargs)
        settings = {'group': 'Skill', 'max_design_repairs': 2}
        with patch('rtlflow.providers.urllib.request.urlopen', side_effect=respond) as http:
            report = run_task(task, GLMProvider(settings), settings, RULES, self.directory)
        self.assertEqual(http.call_count, 2)
        self.assertEqual(report['provider_calls'], 1)
        self.assertFalse(report['skill_loaded'])
        self.assertEqual(report['skill_by_phase']['design']['status'], 'partial')
        self.assertEqual(set(report['skill_documents']), {'SKILL.md'})
        self.assertEqual(report['skill_evidence_phase'], 'design')
        self.assertEqual(report['last_error_code'], 'skill_not_loaded')
        self.assertEqual(report['attempts'], [])

    def test_rejected_review_reports_loading_before_rtl_without_claiming_completion(self):
        task, contract, _, _ = example()
        rejection = json.dumps({'accepted': False, 'issues': ['ambiguous edge'], 'rationale': 'Cannot freeze.'})
        replay = SkillHTTPReplay([json.dumps(contract), rejection])
        settings = {'group': 'Skill', 'max_design_repairs': 0}
        with patch('rtlflow.providers.urllib.request.urlopen', side_effect=replay):
            report = run_task(task, GLMProvider(settings), settings, RULES, self.directory)
        self.assertEqual(report['stop_reason'], 'design_not_frozen')
        self.assertEqual(report['last_error_code'], 'design_review_rejected')
        self.assertTrue(report['skill_loaded'])
        self.assertEqual(report['skill_loaded_calls'], 2)
        self.assertTrue(report['skill_all_calls_loaded'])  # Only the two reached calls, not the whole pipeline.
        self.assertFalse(report['implementation_skill_loaded'])
        self.assertEqual(report['skill_evidence_phase'], 'design_review')
        self.assertEqual(report['skill_by_phase']['verification_design']['status'], 'not_run')
        self.assertEqual(report['skill_by_phase']['initial']['status'], 'not_run')
        self.assertEqual(report['attempts'], [])

    def test_mock_requests_are_not_document_loading_evidence(self):
        task, contract, _, _ = example()
        rejection = json.dumps({'accepted': False, 'issues': ['ambiguous edge'], 'rationale': 'Cannot freeze.'})
        provider = SequenceProvider([json.dumps(contract), rejection])
        report = run_task(task, provider, {'group': 'Skill', 'max_design_repairs': 0}, RULES, self.directory)
        self.assertTrue(report['demo_only'])
        self.assertTrue(report['skill_requested'])
        self.assertEqual(report['skill_required_calls'], 2)
        self.assertEqual(report['skill_loaded_calls'], 0)
        self.assertFalse(report['skill_loaded'])
        self.assertFalse(report['skill_all_calls_loaded'])
        self.assertIsNot(provider.skills[0], provider.skills[1])
        for reader in provider.skills:
            self.assertEqual(reader.available_paths, ['SKILL.md'])
            self.assertEqual(reader.documents, {})

    def test_summary_preserves_selected_rtl_evidence_after_rollback(self):
        calls = [{'phase': phase, 'index': i, 'prompt_path': phase, 'generation_metadata': {
            'skill_loaded': True, 'skill_documents': {'rules.md': {'sha256': digest}}}}
            for i, (phase, digest) in enumerate((('initial', 'selected'), ('refactor', 'rejected')))]
        summary = workflow_skill_report(calls, 'Skill', calls, 0)
        self.assertEqual(summary['rules_sha256'], 'selected')
        self.assertEqual(summary['skill_evidence_phase'], 'initial')
        self.assertEqual(summary['skill_loaded_calls'], 2)
        self.assertTrue(summary['implementation_skill_loaded'])

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_every_phase_and_retry_loads_skill_with_isolated_contexts_and_real_hdl(self):
        reports, requests = {}, {}
        for group in ('Baseline', 'Skill'):
            task, contract, tb, rtl = example()
            bad_rtl = rtl.replace("{1'b0,a}+{1'b0,b}", "{1'b0,a}-{1'b0,b}")
            responses = ['DESIGN_DIALOGUE_ONLY', json.dumps(contract), APPROVE,
                         'VERIFIER_REPAIR_ONLY', tb, APPROVE, bad_rtl, rtl, rtl]
            replay = SkillHTTPReplay(responses)
            settings = {'group': group, 'language': 'verilog', 'max_design_repairs': 1,
                        'max_verification_repairs': 1, 'max_repairs': 1, 'max_refactors': 1,
                        'readability_threshold': 95}
            scores = [{'score': score, 'status': 'passed'} for score in (40, 40, 60)]
            output = self.directory / group
            with patch('rtlflow.providers.urllib.request.urlopen', side_effect=replay), \
                    patch('rtlflow.pipeline.score_readability', side_effect=scores):
                summary = run_batch([task], GLMProvider(settings), settings, RULES, output)
            report = json.loads((output / task['id'] / 'report.json').read_text())
            reports[group], requests[group] = report, replay.requests
            self.assertEqual(report['schema_version'], 6)
            self.assertEqual(report['functional_status'], 'passed')
            self.assertEqual(report['stop_reason'], 'refactor_accepted')
            self.assertEqual(report['provider_calls'], 9)
            self.assertEqual(report['model_calls'], 27 if group == 'Skill' else 9)
            self.assertEqual(report['tool_calls'], 27 if group == 'Skill' else 0)
            self.assertEqual(report['usage']['total_tokens'], report['model_calls'] * 57)
            self.assertEqual(report['skill_loaded_calls'], 9 if group == 'Skill' else 0)
            self.assertEqual(report['skill_all_calls_loaded'], group == 'Skill')
            self.assertEqual(report['implementation_skill_loaded'], group == 'Skill')
            self.assertEqual(summary['skill_loaded_calls'], report['skill_loaded_calls'])
            self.assertEqual(summary['skill_all_calls_loaded_runs'], int(group == 'Skill'))
            with (output / 'summary.csv').open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(int(row['skill_loaded_calls']), report['skill_loaded_calls'])
            calls = report['design']['attempts'] + report['verification_preparation']['attempts'] + report['attempts']
            self.assertEqual([call['phase'] for call in calls], ['design', 'design', 'design_review',
                'verification_design', 'verification_design', 'verification_review', 'initial', 'repair', 'refactor'])
            for call in calls:
                phase = call['phase']
                expected_guide = 'systemverilog' if phase.startswith('verification_') else 'verilog'
                metadata = call['generation_metadata']
                self.assertEqual(metadata['skill_loaded'], group == 'Skill')
                self.assertEqual(call['skill_requested'], group == 'Skill')
                trace = json.loads(Path(metadata['agent_trace_path']).read_text())
                first = trace['turns'][0]['request']
                self.assertFalse(any(m['role'] == 'tool' for m in first['messages']))
                self.assertEqual('tools' in first, group == 'Skill')
                if group == 'Skill':
                    self.assertEqual(call['skill_language'], expected_guide)
                    self.assertEqual(set(metadata['skill_documents']), {'SKILL.md', 'rules.md', f'references/{expected_guide}.md'})
                    self.assertEqual(first['tools'][0]['function']['parameters']['properties']['path']['enum'], ['SKILL.md'])
                    self.assertEqual([turn['request']['tool_choice'] for turn in trace['turns']],
                                     ['required', 'required', 'none'])
                    self.assertEqual(report['skill_by_phase'][phase]['status'], 'loaded')
                else:
                    self.assertEqual(metadata['skill_documents'], {})
                    self.assertEqual(report['skill_by_phase'][phase]['status'], 'not_requested')
                if len(first['messages']) > 2:
                    self.assertEqual(first['messages'][-1]['content'].startswith(SKILL_RELOAD_REQUEST), group == 'Skill')
                prompt = Path(call['prompt_path']).read_text()
                if phase in ('design_review', 'verification_design', 'verification_review', 'initial', 'repair', 'refactor'):
                    self.assertNotIn('DESIGN_DIALOGUE_ONLY', prompt)
                if phase not in ('verification_design',):
                    self.assertNotIn('VERIFIER_REPAIR_ONLY', prompt)
                if phase in ('initial', 'repair', 'refactor'):
                    self.assertNotIn('RTL_CHECK_FAIL: sum', prompt)  # No hidden TB in implementation/repair.
                if phase.endswith('_review'):
                    self.assertEqual([m['role'] for m in first['messages']], ['system', 'user'])
            self.assertEqual(report['skill_by_phase']['design']['calls'], 2)
            self.assertEqual(report['skill_by_phase']['verification_design']['calls'], 2)
        baseline_params = {k: v for k, v in requests['Baseline'][0].items() if k != 'messages'}
        for body in requests['Skill']:
            self.assertEqual({k: v for k, v in body.items() if k not in ('messages', 'tools', 'tool_choice')}, baseline_params)
        self.assertEqual(reports['Baseline']['source_sha256'], reports['Skill']['source_sha256'])

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_missing_skill_at_any_stage_stops_without_retry_or_fabricated_coverage(self):
        task, contract, tb, rtl = example()
        responses = [json.dumps(contract), APPROVE, tb, APPROVE, rtl]
        phases = [*PREPARATION, 'initial']
        for failed in range(5):
            with self.subTest(phase=phases[failed]):
                replay = SkillHTTPReplay(responses)
                def respond(request, **kwargs):
                    if replay.finals == failed:
                        return reply(responses[failed])  # A plausible result without reading the Skill.
                    return replay(request, **kwargs)
                settings = {'group': 'Skill', 'max_design_repairs': 2, 'max_verification_repairs': 2,
                            'max_repairs': 2, 'max_refactors': 1}
                with patch('rtlflow.providers.urllib.request.urlopen', side_effect=respond) as http:
                    report = run_task(task, GLMProvider(settings), settings, RULES, self.directory / str(failed))
                self.assertEqual(http.call_count, failed * 3 + 1)
                self.assertEqual(report['provider_calls'], failed + 1)
                self.assertEqual(report['last_error_code'], 'skill_not_loaded')
                self.assertEqual(report['functional_status'], 'not_run')
                self.assertEqual(report['skill_scope'], 'full_workflow')
                self.assertEqual(report['skill_required_calls'], failed + 1)
                self.assertEqual(report['skill_loaded_calls'], failed)
                self.assertEqual(report['skill_loaded'], failed > 0)
                self.assertFalse(report['skill_all_calls_loaded'])
                self.assertFalse(report['implementation_skill_loaded'])
                self.assertIsNone(report['final_source'])
                self.assertEqual(report['repair_calls'], 0)
                self.assertEqual(report['skill_by_phase'][phases[failed]]['status'], 'not_loaded')
                for phase in phases[failed + 1:]:
                    self.assertEqual(report['skill_by_phase'][phase]['status'], 'not_run')
                expected_stop = 'design_not_frozen' if failed < 2 else 'verification_not_frozen' if failed < 4 else 'generation_error'
                self.assertEqual(report['stop_reason'], expected_stop)
