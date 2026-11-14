"""Source-only scoring and both-arm refactor policy; no JVM or model required."""
import csv
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import RULES, SequenceProvider, TemporaryTestCase
from rtlflow.chisel_score import CHISEL_SCORE_VERSION, _mask_scala
from rtlflow.pipeline import run_group_comparison, run_task
from rtlflow.project import bundle_text, parse_bundle, write_bundle
from rtlflow.score import score_readability

SOURCE = '''import chisel3._

// Forward the input without adding latency.
class Forward extends RawModule {
  val dataIn = IO(Input(UInt(8.W)))
  val dataOut = IO(Output(UInt(8.W)))
  dataOut := dataIn
}
'''
PLAIN = SOURCE.replace('// Forward the input without adding latency.\n', '')
TASK = {'id': 'source-score-only', 'design_tops': ['Forward'], 'contract_text': 'Unit-only forwarder.',
        'chisel_tops': [{'module': 'Forward', 'class': 'Forward', 'args': []}],
        'dataset_provenance': {'dataset': 'unit-only', 'manifest_sha256': '0' * 64}}


class ChiselScoreTests(unittest.TestCase):
    def score(self, code):
        return score_readability(code, 'chisel')

    def test_source_score_schema_and_determinism(self):
        result = self.score(SOURCE)
        self.assertEqual(result, self.score(SOURCE))
        self.assertEqual(result['method'], CHISEL_SCORE_VERSION)
        self.assertEqual(result['language'], 'chisel')
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['score'], 100)
        self.assertEqual({name: dim['weight'] for name, dim in result['dimensions'].items()},
                         {'naming': 25, 'structure': 25, 'complexity': 20, 'comments': 15, 'style': 15})
        self.assertEqual(self.score(PLAIN)['score'], 90)

    def test_scala_declarations_and_common_pattern_bindings(self):
        result = self.score('''// intent
class X[T <: Data] extends Module {
  val a = Wire(Bool())
  var b = 0
  def c = a
  object D
  trait E
  val f :: g :: Nil = Enum(2)
  val (h, value) = (1, 2)
  val i = 0
  val j = 0
  val k = 0
}
''')
        self.assertEqual(result['dimensions']['naming']['issues'],
                         [f'单字符声明名：{name}' for name in ['D', 'E', 'X', 'a', 'b', 'c', 'f', 'g', 'h']])
        self.assertEqual(result['dimensions']['naming']['score'], 0)

    def test_semicolon_separation_and_for_enumerator_exemptions(self):
        for code, count in [('val first = 0; val second = 1', 1),
                            ('val first = 0;\nval second = 1;', 0),
                            ('for (i <- 0 until 2; j <- 0 until 2) { consume(i, j) }', 0),
                            ('for { i <- 0 until 2; j <- 0 until 2 } yield (i, j)', 0),
                            ('for (i <- 0 until 2; j <- 0 until 2) { val first = i; consume(first) }', 1)]:
            with self.subTest(code=code):
                dimension = self.score(code)['dimensions']['structure']
                self.assertEqual(len(dimension['issues']), count)
                self.assertEqual(dimension['score'], 25 - 3 * count)

    def test_brace_depth_and_multiline_mux_not_sibling_calls(self):
        deep = 'class Forward { when(enable) { when(ready) { when(valid) { work() } } } }'
        complexity = self.score(deep)['dimensions']['complexity']
        self.assertEqual(complexity['score'], 15)
        self.assertIn('嵌套深度为 4', complexity['issues'][0])
        nested = 'val result = Mux(ready,\n  Mux(valid, first, second), third)'
        self.assertEqual(self.score(nested)['dimensions']['complexity']['issues'], ['第 2 行嵌套 Mux 调用'])
        siblings = 'val first = Mux(ready, left, right)\nval second = Mux(valid, left, right)'
        self.assertEqual(self.score(siblings)['dimensions']['complexity']['score'], 20)

    def test_nested_comments_and_literals_preserve_line_numbers(self):
        code = '''/* intent /* nested */ val x = 1; val y = 2 {{{{ */
val message = "https://example.invalid/ /* not a comment */"
val escaped = "quoted \\" // still a string"
val template = s"""${Mux(flag, Mux(flag, left, right), other)}
val z = 0; val q = 1 {{{{
"""
val brace = '{'
val quote = '\\''
val slash = '/'
val first = 0; val second = 1
'''
        clean, has_comment = _mask_scala(code)
        self.assertTrue(has_comment)
        self.assertEqual(len(clean), len(code))
        self.assertEqual([i for i, c in enumerate(clean) if c == '\n'],
                         [i for i, c in enumerate(code) if c == '\n'])
        result = self.score(code)['dimensions']
        self.assertEqual(result['naming']['issues'], [])
        self.assertEqual(result['complexity']['issues'], [])
        self.assertEqual(result['structure']['issues'], ['第 10 行包含分号分隔的多个语句'])

    def test_fake_and_empty_comments_do_not_earn_comment_credit(self):
        for text in ['"// comment"', '"/* comment */"', "'/'", '"""// comment\n/* comment */"""']:
            with self.subTest(text=text):
                self.assertEqual(self.score('val message = ' + text)['dimensions']['comments']['score'], 5)
        for text in ['//\n', '/**/\n', '/** \n * \n */\n']:
            self.assertEqual(self.score(text + PLAIN)['dimensions']['comments']['score'], 5)
        self.assertEqual(self.score('/** design intent */\n' + PLAIN)['dimensions']['comments']['score'], 15)

    def test_style_penalties_and_bounds(self):
        code = SOURCE + '\tval longName = 0  \n' + '// ' + 'x' * 98 + '\n'
        style = self.score(code)['dimensions']['style']
        self.assertEqual(style['score'], 12)
        result = self.score(('val x = Mux(flag, Mux(flag, left, right), other); val y = 0\t \n') * 40)
        self.assertEqual(result['score'], 24)  # Names are deduplicated: 19 naming + 5 comments.
        for dim in result['dimensions'].values():
            self.assertGreaterEqual(dim['score'], 0)
            self.assertLessEqual(dim['score'], dim['weight'])

    def test_blank_and_comment_only_are_not_scored_as_readable_programs(self):
        for text in ['', ' \n\t', '// intent', '/* only a comment */']:
            with self.subTest(text=text):
                result = self.score(text)
                self.assertEqual(result['status'], 'not_run')
                self.assertIsNone(result['score'])
                self.assertEqual(result['reason'], 'no_scala_code')
        with self.assertRaises(ValueError):
            score_readability(SOURCE, 'scala')


class ChiselScorePipelineTests(TemporaryTestCase):
    def verifier(self, statuses):
        calls = []
        def verify(files, source, task, checks, settings):
            index = len(calls)
            calls.append(files)
            emitted = checks / 'emitted'
            # Distinct, deliberately unreadable RTL: source scoring must never consume it.
            write_bundle({'Forward.sv': f'module Forward; wire x; wire y; // RTL {index}\nendmodule\n'}, emitted)
            return {'functional_status': statuses[min(index, len(statuses) - 1)], 'checks': {},
                    'emitted_directory': str(emitted)}
        return verify, calls

    def test_refactor_accept_reject_and_source_rtl_snapshot_in_both_groups(self):
        for group in ('Baseline', 'Skill'):
            for case, last_source, status, accepted in [
                ('improved', SOURCE, 'passed', True),
                ('functional-regression', SOURCE, 'failed', False),
                ('verification-unavailable', SOURCE, 'not_run', False),
                ('unchanged-score', PLAIN, 'passed', False),
                ('worse-score', PLAIN.replace('  ', '\t'), 'passed', False),
            ]:
                with self.subTest(group=group, case=case):
                    provider = SequenceProvider([bundle_text({'Top.scala': text}) for text in (PLAIN, last_source)])
                    verify, calls = self.verifier(['passed', status])
                    with patch('rtlflow.pipeline.verify_project', side_effect=verify):
                        report = run_task(TASK, provider, {'language': 'chisel', 'group': group,
                            'readability_threshold': 95}, RULES, self.directory / group / case)
                    self.assertEqual(len(calls), 2)
                    self.assertEqual(report['refactor_calls'], 1)
                    self.assertEqual(report['attempts'][1]['refactor_accepted'], accepted)
                    self.assertEqual(report['selected_attempt'], int(accepted))
                    self.assertEqual(report['functional_status'], 'passed')
                    self.assertEqual(report['readability_score'], 100 if accepted else 90)
                    self.assertEqual(report['readability_method'], CHISEL_SCORE_VERSION)
                    self.assertEqual(report['readability_status'], 'passed')
                    self.assertEqual(report['stop_reason'], 'refactor_accepted' if accepted else 'refactor_rejected_rolled_back')
                    self.assertEqual(parse_bundle(Path(report['final_bundle']).read_text(), 'chisel'),
                                     {'Top.scala': SOURCE if accepted else PLAIN})
                    self.assertIn(f'RTL {int(accepted)}', (Path(report['final_rtl']) / 'Forward.sv').read_text())
                    feedback = provider.messages[1][-1]['content']
                    self.assertIn(CHISEL_SCORE_VERSION, feedback)
                    self.assertIn('缺少设计意图注释', feedback)
                    self.assertNotIn('module Forward', feedback)

    def test_high_score_zero_budget_and_unverified_candidates_do_not_refactor(self):
        for group in ('Baseline', 'Skill'):
            for case, code, status, budget in [('threshold', SOURCE, 'passed', 1),
                    ('zero-budget', PLAIN, 'passed', 0), ('failed', PLAIN, 'failed', 1),
                    ('missing-tools', PLAIN, 'not_run', 1)]:
                with self.subTest(group=group, case=case):
                    provider = SequenceProvider([bundle_text({'Top.scala': code})])
                    with patch('rtlflow.pipeline.verify_project', return_value={'functional_status': status, 'checks': {}}):
                        report = run_task(TASK, provider, {'language': 'chisel', 'group': group,
                            'max_repairs': 0, 'max_refactors': budget, 'readability_threshold': 95},
                            RULES, self.directory / group / case)
                    self.assertEqual(report['provider_calls'], 1)
                    self.assertEqual(report['refactor_calls'], 0)
                    self.assertEqual(report['readability_status'], 'passed')
                    self.assertIsNone(report['final_rtl'])

    def test_project_order_and_comparison_report_score_metadata(self):
        files = {'z/Top.scala': SOURCE, 'a/Helper.scala': '// Helper intent.\nclass Helper\n'}
        output = self.directory / 'comparison'
        with patch('rtlflow.pipeline.verify_project', return_value={'functional_status': 'passed', 'checks': {}}), \
             patch('rtlflow.pipeline.tool_versions', return_value={}):
            summary = run_group_comparison([TASK], lambda _: SequenceProvider([bundle_text(files)]),
                {'language': 'chisel'}, RULES, ['Baseline', 'Skill'], output)
        for group in ('Baseline', 'Skill'):
            entry = summary['by_task'][TASK['id']][group]
            self.assertEqual(entry['readability_method'], CHISEL_SCORE_VERSION)
            self.assertEqual(entry['readability_status'], 'passed')
            report = json.loads(Path(entry['report_path']).read_text())
            actual = dict(report['attempts'][0]['readability'])
            self.assertEqual(actual.pop('project_file_order'), sorted(files))
            self.assertEqual(actual, score_readability('\n'.join(files[p] for p in sorted(files)), 'chisel'))
        with (output / 'summary.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['readability_method'] == CHISEL_SCORE_VERSION for row in rows))
        self.assertTrue(all(row['readability_score'] == '100' for row in rows))
