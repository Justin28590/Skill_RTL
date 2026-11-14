"""Language routing and JSON transport regressions from the systolic pilot.

Only small synthetic contracts are used; no paid calls or task-answer fixtures.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, RULES, SequenceProvider, SkillHTTPReplay, TemporaryTestCase
from rtlflow.design import design_messages, parse_json, validate_contract
from rtlflow.pipeline import run_task
from rtlflow.providers import GLMProvider
from test_design_flow import APPROVE, example


def fenced(value):
    return "```json\n" + value + "\n```"


class DesignProtocolTests(unittest.TestCase):
    def test_language_specific_examples_are_valid_contracts(self):
        for language in ('verilog', 'systemverilog', 'chisel'):
            with self.subTest(language=language):
                messages = design_messages(example()[0], language)
                prompt = messages[0]['content']
                contract = json.loads(next(line for line in prompt.splitlines() if line.startswith('{')))
                self.assertEqual(validate_contract(contract, language), contract)
                self.assertIn('不要Markdown代码围栏', prompt)
                self.assertIn('tops仅列对外公开的独立入口', prompt)
                self.assertIn('内部子模块的职责写入description', prompt)
                self.assertIn('目标语言：' + language, messages[1]['content'])
                if language == 'chisel':
                    self.assertEqual(contract['tops'][0]['parameters'], {})
                    self.assertEqual(contract['chisel_tops'][0]['module'], contract['tops'][0]['name'])
                    self.assertIn('Chisel6.5.0', prompt)
                else:
                    for irrelevant in ('Chisel6.5.0', 'firtool', 'uint_width', '全限定类名'):
                        self.assertNotIn(irrelevant, prompt)
                    self.assertEqual(contract['chisel_tops'], [])
                    self.assertEqual(contract['configurations'][1]['parameters'], {'WIDTH': 4})
        with self.assertRaisesRegex(ValueError, '目标语言'):
            design_messages(example()[0], 'unknown')

    def test_json_envelope_normalization_is_explicit_and_preserves_content(self):
        value = {'body': 'literal ```json and "quoted" text', 'nested': {'value': 3}}
        raw = json.dumps(value)
        for response, removed in ((raw, False), (' \n' + raw + '\t', False),
                                  (fenced(raw), True), (' \n```json \r\n' + raw + '\r\n```\t', True)):
            with self.subTest(response=response):
                audit = {}
                self.assertEqual(parse_json(response, audit=audit), value)
                self.assertEqual(audit, {'json_wrapper_removed': removed})

    def test_json_normalization_never_extracts_repairs_or_accepts_partial_documents(self):
        invalid = [
            'Here is JSON:\n' + fenced('{}'), fenced('{}') + '\nexplanation',
            fenced('{}') + '\n' + fenced('{}'), '```json\n{}', '```json\n{\n```',
            '```python\n{}\n```', '{} {}', '{"a":1,}', '[{}]', 'null',
            '{"nested":{"a":1,"a":2}}', fenced('{"a":1,"a":2}'),
            '{"value":NaN}', fenced('{"value":Infinity}'), '{"value":-Infinity}',
            None, ' ' * 2_000_001,
        ]
        for index, response in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(ValueError):
                parse_json(response)

    def test_language_and_parameter_errors_are_reported_together_without_mutation(self):
        contract = deepcopy(example()[1])
        contract['chisel_tops'] = [{'module': 'ChosenAdder', 'class': 'wrong.Language', 'args': [8]}]
        contract['configurations'][1]['parameters'] = {'DIM': 4}
        original = deepcopy(contract)
        with self.assertRaises(ValueError) as error:
            validate_contract(parse_json(fenced(json.dumps(contract))), 'systemverilog')
        diagnostic = str(error.exception)
        for detail in ('systemverilog', 'chisel_tops必须为[]', 'configurations[1]', 'DIM', 'BITS'):
            self.assertIn(detail, diagnostic)
        self.assertEqual(contract, original)


@unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
class DesignProtocolFlowTests(TemporaryTestCase):
    def test_fenced_semantic_failure_gets_one_complete_repair_then_full_skill_flow(self):
        task, contract, tb, rtl = example()
        bad = deepcopy(contract)
        bad['chisel_tops'] = [{'module': 'ChosenAdder', 'class': 'wrong.Language', 'args': [8]}]
        bad['configurations'][1]['parameters'] = {'DIM': 4}
        responses = [fenced(json.dumps(bad)), fenced(json.dumps(contract)), fenced(APPROVE),
                     fenced(tb), fenced(APPROVE), rtl]
        replay = SkillHTTPReplay(responses)
        settings = {'language': 'systemverilog', 'group': 'Skill', 'max_design_repairs': 1,
                    'max_verification_repairs': 0, 'max_repairs': 0, 'max_refactors': 0}
        with patch.dict(os.environ, {'GLM_API_KEY': 'unit-only'}, clear=True), \
                patch('rtlflow.providers.urllib.request.urlopen', side_effect=replay):
            report = run_task(task, GLMProvider(settings), settings, RULES, self.directory)
        self.assertEqual(report['functional_status'], 'passed')
        self.assertEqual(report['provider_calls'], 6)
        self.assertEqual(report['model_calls'], 18)  # Two Skill read turns per phase, including preparation.
        self.assertEqual(report['generation_error_counts'], {'invalid_design_contract': 1})
        self.assertEqual(report['design']['status'], 'frozen')
        self.assertEqual(report['verification_preparation']['status'], 'frozen')
        self.assertTrue(report['skill_loaded'])
        feedback = replay.requests[3]['messages'][-1]['content']
        for detail in ('systemverilog', 'chisel_tops必须为[]', 'DIM', 'BITS'):
            self.assertIn(detail, feedback)
        self.assertEqual(report['skill_loaded_calls'], 6)
        self.assertTrue(report['skill_all_calls_loaded'])
        for request in replay.requests:
            self.assertIn('tools', request)  # The Skill now guides every workflow role.
        stages = report['design']['attempts'] + report['verification_preparation']['attempts']
        for stage, original in zip(stages, responses[:5]):
            self.assertTrue(stage['json_wrapper_removed'])
            self.assertEqual(Path(stage['response_path']).read_text(), original)
        frozen = json.loads(Path(report['design']['frozen_contract_path']).read_text())
        self.assertEqual(frozen['contract'], contract)

    def test_invalid_fenced_contract_never_reaches_review_or_rtl_without_repair_budget(self):
        task, contract, _, _ = example()
        contract['chisel_tops'] = [{'module': 'ChosenAdder', 'class': 'wrong.Language', 'args': [8]}]
        provider = SequenceProvider([fenced(json.dumps(contract))])
        report = run_task(task, provider, {'language': 'systemverilog', 'max_design_repairs': 0},
                          RULES, self.directory)
        self.assertEqual(len(provider.messages), 1)
        self.assertEqual(provider.skills, [None])
        self.assertEqual(report['stop_reason'], 'design_not_frozen')
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['attempts'], [])
        self.assertIn('chisel_tops必须为[]', report['last_error'])
        self.assertTrue(report['design']['attempts'][0]['json_wrapper_removed'])

    def test_fenced_rejected_review_is_not_approval(self):
        task, contract, _, _ = example()
        rejection = json.dumps({'accepted': False, 'issues': ['ambiguous timing'], 'rationale': 'Not ready.'})
        provider = SequenceProvider([fenced(json.dumps(contract)), fenced(rejection)])
        report = run_task(task, provider, {'language': 'systemverilog', 'max_design_repairs': 0},
                          RULES, self.directory)
        self.assertEqual(report['stop_reason'], 'design_not_frozen')
        self.assertEqual(report['last_error_code'], 'design_review_rejected')
        self.assertEqual(report['provider_calls'], 2)
        self.assertEqual(report['attempts'], [])
