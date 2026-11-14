import json
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, RULES, TASKS, SequenceProvider, TemporaryTestCase, fixture
from rtlflow.pipeline import _run_implementation as run_task
from rtlflow.project import bundle_text, parse_bundle
from rtlflow.providers import GenerationError


# Shared controller behavior is tested once. Two-arm parity and actual Skill
# loading are covered by test_comparison.py and test_skill_agent.py.
@unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
class PipelineTests(TemporaryTestCase):
    group = 'Baseline'

    def sequence(self, responses, task='and2', **settings):
        provider = SequenceProvider(responses)
        report = run_task(TASKS[task], provider, {'group':self.group,'max_repairs':2,'max_refactors':1,
                          'tool_timeout_seconds':2,'readability_threshold':100,**settings}, RULES, self.directory)
        return report, provider

    def test_real_multifile_functional_repair_and_snapshot(self):
        report, provider = self.sequence([fixture('add8.broken.v'), fixture('add8.v')], 'add8')
        self.assertEqual(report['functional_status'],'passed')
        self.assertTrue(report['repair_success'])
        self.assertEqual(report['repair_calls'],1)
        self.assertEqual(set(report['files_sha256']), {'child.v','top.v'})
        self.assertTrue((Path(report['final_source'])/'child.v').is_file())
        self.assertEqual(parse_bundle(Path(report['final_bundle']).read_text()),parse_bundle(fixture('add8.v')))
        self.assertEqual(provider.messages[1][2]['content'],fixture('add8.broken.v'))
        self.assertNotIn('AND truth table mismatch',provider.messages[1][3]['content'])

    def test_missing_dependency_then_repaired_with_complete_bundle(self):
        good=parse_bundle(fixture('and2.v')); bad=bundle_text({'top.v':good['top.v']})
        report, provider=self.sequence([bad,fixture('and2.v')])
        self.assertEqual(report['functional_status'],'passed')
        self.assertEqual(report['attempts'][0]['verification']['checks']['candidate_compile']['status'],'failed')
        self.assertIn('and2_leaf',provider.messages[1][-1]['content'])
        self.assertNotIn('UNIT_PROJECT_PASS',provider.messages[1][-1]['content'])

    def test_malformed_and_unsafe_bundle_get_repair_opportunity(self):
        report,_=self.sequence(['not JSON',fixture('and2.v')])
        self.assertEqual(report['functional_status'],'passed')
        self.assertTrue(report['repair_success'])
        self.assertEqual(report['attempts'][0]['verification']['checks']['bundle']['status'],'failed')

    def test_no_stale_files_carried_between_attempts(self):
        bad=parse_bundle(fixture('and2.broken.v'))
        bad['obsolete.v']='module obsolete; endmodule\n'
        report,_=self.sequence([bundle_text(bad),fixture('and2.v')])
        self.assertEqual(report['functional_status'],'passed')
        self.assertFalse((Path(report['final_source'])/'obsolete.v').exists())
        self.assertFalse((Path(report['attempts'][1]['source_directory'])/'obsolete.v').exists())

    def test_repair_limit_is_respected(self):
        for limit in (0, 1, 2):
            provider=SequenceProvider([fixture('and2.broken.v')])
            report=run_task(TASKS['and2'],provider,{'group':self.group,'max_repairs':limit},RULES,self.directory/str(limit))
            self.assertEqual(report['functional_status'],'failed')
            self.assertEqual(report['repair_calls'],limit)
            self.assertEqual(report['refactor_calls'],0)

    def test_refactor_rolls_back_entire_project(self):
        good=fixture('and2.v')
        with patch('rtlflow.pipeline.score_readability',return_value={'score':50,'status':'passed'}):
            report,_=self.sequence([good,fixture('and2.broken.v')])
        self.assertEqual(report['functional_status'],'passed')
        self.assertEqual(report['stop_reason'],'refactor_rejected_rolled_back')
        self.assertEqual(Path(report['final_bundle']).read_text(),good)
        self.assertFalse(report['attempts'][1]['refactor_accepted'])

    def test_refactor_accepted_only_after_function_and_score_improve(self):
        good=fixture('and2.v')
        with patch('rtlflow.pipeline.score_readability',side_effect=[{'score':40,'status':'passed'}, {'score':60,'status':'passed'}]):
            report,_=self.sequence([good,good])
        self.assertTrue(report['attempts'][1]['refactor_accepted'])
        self.assertEqual(report['selected_attempt'],1)
        self.assertEqual(report['readability_score'],60)

    def test_worse_score_and_api_error_keep_known_good_project(self):
        for last in (fixture('and2.v'),GenerationError('API unavailable')):
            provider=SequenceProvider([fixture('and2.v'),last])
            with patch('rtlflow.pipeline.score_readability',side_effect=[{'score':50,'status':'passed'}, {'score':40,'status':'passed'}]):
                report=run_task(TASKS['and2'],provider,{'group':self.group,'readability_threshold':100},RULES,
                                self.directory/('api' if isinstance(last,Exception) else 'score'))
            self.assertEqual(report['functional_status'],'passed')
            self.assertEqual(report['stop_reason'],'refactor_rejected_rolled_back')
            self.assertEqual(report['selected_attempt'],0)

    def test_api_error_during_repair_keeps_last_artifact(self):
        report,_=self.sequence([fixture('add8.broken.v'),GenerationError('API unavailable')],'add8')
        self.assertEqual(report['functional_status'],'failed')
        self.assertEqual(report['stop_reason'],'generation_error')
        self.assertTrue(Path(report['final_bundle']).is_file())

    def test_malformed_last_repair_retains_last_complete_snapshot(self):
        for task in ('and2', 'add8'):
            broken = fixture(task + '.broken.v')
            provider = SequenceProvider([broken, 'not JSON'])
            report = run_task(TASKS[task], provider, {'max_repairs': 1, 'max_refactors': 0},
                              RULES, self.directory/task)
            self.assertEqual(report['functional_status'], 'failed')
            self.assertEqual(report['stop_reason'], 'repair_limit')
            self.assertEqual(report['selected_attempt'], 0)
            self.assertEqual(Path(report['final_bundle']).read_text(), broken)
            self.assertEqual(report['generation_failures'], 1)
            self.assertEqual(report['last_error_code'], 'invalid_project_bundle')
            self.assertFalse(report['attempts'][1]['selected_final'])

    def test_malformed_repair_can_still_be_repaired_with_remaining_budget(self):
        report, provider = self.sequence([fixture('and2.broken.v'), 'not JSON', fixture('and2.v')],
                                         max_refactors=0)
        self.assertEqual(report['functional_status'], 'passed')
        self.assertEqual(report['selected_attempt'], 2)
        self.assertEqual(report['repair_calls'], 2)
        self.assertEqual(provider.messages[2][-2]['content'], 'not JSON')

    def test_unavailable_refactor_score_rolls_back_instead_of_crashing(self):
        with patch('rtlflow.pipeline.score_readability', side_effect=[
                {'score': 40, 'status': 'passed'}, {'score': None, 'status': 'not_run'}]):
            report, _ = self.sequence([fixture('and2.v'), fixture('and2.v')])
        self.assertEqual(report['functional_status'], 'passed')
        self.assertEqual(report['stop_reason'], 'refactor_rejected_rolled_back')
        self.assertEqual(report['selected_attempt'], 0)

    def test_systemverilog_multifile_project(self):
        files={p.replace('.v','.sv'):c.replace('wire','logic') for p,c in parse_bundle(fixture('and2.v')).items()}
        report,_=self.sequence([bundle_text(files)],language='systemverilog')
        self.assertEqual(report['functional_status'],'passed')
        self.assertEqual(set(report['files_sha256']),{'child.sv','top.sv'})


class UnavailableTests(TemporaryTestCase):
    group = 'Baseline'

    def test_missing_tools_do_not_trigger_model_repairs(self):
        provider=SequenceProvider([fixture('and2.v')])
        with patch('rtlflow.project.shutil.which',return_value=None):
            report=run_task(TASKS['and2'],provider,{'group':self.group},RULES,self.directory)
        self.assertEqual(report['functional_status'],'not_run')
        self.assertEqual(report['repair_calls'],0)

    def test_api_failure_is_not_functional_failure_and_has_no_final(self):
        provider=SequenceProvider([GenerationError('unavailable')])
        report=run_task(TASKS['and2'],provider,{'group':self.group},RULES,self.directory)
        self.assertEqual(report['functional_status'],'not_run')
        self.assertIsNone(report['final_source'])
        self.assertEqual(report['repair_calls'],0)

    def test_unsupported_chisel_fails_before_generation(self):
        provider=SequenceProvider(['unused'])
        with self.assertRaisesRegex(ValueError,'Chisel'):
            run_task(TASKS['and2'],provider,{'language':'chisel'},RULES,self.directory)
        self.assertEqual(provider.messages,[])

    def test_unavailable_score_skips_refactor(self):
        provider=SequenceProvider([fixture('and2.v')])
        with patch('rtlflow.pipeline.verify_project',return_value={'functional_status':'passed','checks':{}}), \
                patch('rtlflow.pipeline.score_readability',return_value={'score':None,'status':'not_run'}):
            report=run_task(TASKS['and2'],provider,{'group':self.group},RULES,self.directory)
        self.assertEqual(report['refactor_calls'],0)
        self.assertEqual(report['stop_reason'],'readability_unavailable_refactor_skipped')
