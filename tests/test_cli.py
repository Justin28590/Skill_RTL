"""CLI selection defaults and isolated multi-language orchestration; no real API calls."""
import contextlib
import csv
import io
import json
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, RULES, TASKS, SequenceProvider, ImplementationTestCase as TemporaryTestCase, fixture
from rtlflow.cli import load_settings, main, planned_calls
from rtlflow.languages import LANGUAGES
from rtlflow.pipeline import GROUPS, run_language_matrix
from rtlflow.design import load_design_matrix
from rtlflow.providers import GenerationError


class CLITests(TemporaryTestCase):
    def check_data(self, *args):
        with patch('rtlflow.cli.create_provider') as provider, \
                patch('rtlflow.cli.run_batch') as batch, \
                patch('rtlflow.cli.run_group_comparison') as comparison, \
                patch('rtlflow.cli.run_language_matrix') as matrix, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--check-data', *args]), 0)
        for tool in (provider, batch, comparison, matrix):
            tool.assert_not_called()
        return json.loads(out.getvalue())

    def test_help_lists_only_the_simplified_selectors(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as raised:
            main(['-h'])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn('--group GROUP [GROUP ...]', out.getvalue())
        self.assertIn('--language LANG [LANG ...]', out.getvalue())
        self.assertNotIn('--groups', out.getvalue())
        self.assertNotIn('--all-groups', out.getvalue())
        self.assertIn('默认各任务已支持的全部语言', out.getvalue())
        self.assertIn('target_languages', out.getvalue())
        self.assertIn('并非每个任务都支持三种语言', out.getvalue())

    def test_default_all_languages_tasks_and_groups_offline(self):
        result = self.check_data()
        self.assertEqual(result['languages'], list(LANGUAGES))
        self.assertEqual(result['groups'], list(GROUPS))
        self.assertEqual(result['total'], sum(item['total'] for item in result['by_language'].values()))
        ids = {key for item in result['by_language'].values() for key in item['task_ids']}
        self.assertEqual(result['task_count'], len(ids))
        self.assertEqual(set(result['task_ids']), ids)
        self.assertEqual(result['task_group_runs'], result['total'] * len(GROUPS))
        settings = load_settings(ROOT/'configs/glm.json')
        for key, expected in planned_calls(settings, GROUPS, result['total']).items():
            self.assertEqual(result[key], expected)
        self.assertEqual(result['model_calls'], 0)

    def test_omitted_selectors_ignore_legacy_config_selection(self):
        settings = {**load_settings(ROOT/'configs/glm.json'), 'language': 'chisel', 'group': 'Skill'}
        with patch('rtlflow.cli.load_settings', return_value=settings):
            result = self.check_data()
        self.assertEqual(result['languages'], list(LANGUAGES))
        self.assertEqual(result['groups'], list(GROUPS))

    def test_task_only_uses_all_supported_targets(self):
        for task_id, languages in (
            ('aes', ['verilog', 'systemverilog']),
            ('systolic_matmul', ['systemverilog']),
            ('chisel_double_buffer_fifo', ['chisel']),
        ):
            with self.subTest(task_id=task_id):
                result = self.check_data('--task', task_id)
                if len(languages) == 1:
                    self.assertEqual(result['language'], languages[0])
                    self.assertEqual(result['task_ids'], [task_id])
                else:
                    self.assertEqual(result['languages'], languages)
                    for item in result['by_language'].values():
                        self.assertEqual(item['task_ids'], [task_id])
                self.assertEqual(result['total'], len(languages))
                self.assertEqual(result['groups'], list(GROUPS))

    def test_multiple_values_and_repeated_flags(self):
        expected = self.check_data('--task', 'aes', 'cmac', '--language', 'systemverilog', 'verilog',
                                   '--group', 'Skill', 'Baseline')
        repeated = self.check_data('--task', 'aes', '--task', 'cmac',
                                   '--language', 'systemverilog', '--language', 'verilog',
                                   '--group', 'Skill', '--group', 'Baseline')
        self.assertEqual(repeated, expected)
        self.assertEqual(expected['languages'], ['systemverilog', 'verilog'])
        self.assertEqual(expected['groups'], ['Skill', 'Baseline'])
        self.assertEqual(expected['total'], 4)
        mixed = self.check_data('--task', 'aes', 'systolic_matmul', 'chisel_double_buffer_fifo',
                                '--group', 'Skill')
        self.assertEqual(mixed['by_language']['verilog']['task_ids'], ['aes'])
        self.assertEqual(set(mixed['by_language']['systemverilog']['task_ids']), {'aes', 'systolic_matmul'})
        self.assertEqual(mixed['by_language']['chisel']['task_ids'], ['chisel_double_buffer_fifo'])
        self.assertEqual(mixed['task_count'], 3)
        self.assertEqual(mixed['task_group_runs'], 4)

    def test_invalid_or_removed_flags_fail_before_provider(self):
        for args in (
            ['--groups', 'Skill'], ['--all-groups'], ['--gro', 'Skill'],
            ['--group', 'Skill', 'Skill'], ['--group', 'Skill', '--group', 'Skill'],
            ['--task', 'aes', 'aes'], ['--language', 'verilog', 'verilog'],
            ['--language', 'python'], ['--task'],
        ):
            with self.subTest(args=args), patch('rtlflow.cli.create_provider') as provider, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)
            provider.assert_not_called()

    def test_unmatched_task_is_not_silently_dropped(self):
        for args in (
            ['--task', 'not_a_task'],
            ['--language', 'chisel', '--task', 'aes'],
            ['--language', 'verilog', '--task', 'aes', 'systolic_matmul'],
            ['--language', 'verilog', '--task', 'aes', 'not_a_task'],
        ):
            with self.subTest(args=args), patch('rtlflow.cli.create_provider') as provider, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            provider.assert_not_called()

    def test_default_generation_dispatches_the_full_matrix(self):
        with patch('rtlflow.cli.run_language_matrix', return_value={'passed': 0, 'total': 1}) as runner, \
                patch('rtlflow.cli.create_provider') as provider, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 1)
        self.assertEqual(list(runner.call_args.args[0]), list(LANGUAGES))
        self.assertEqual(runner.call_args.args[4], list(GROUPS))
        provider.assert_not_called()

    def test_single_compatible_language_keeps_flat_output(self):
        output = self.directory/'systolic'
        with patch('rtlflow.cli.run_group_comparison', return_value={'passed': 1, 'total': 1}) as runner, \
                patch('rtlflow.cli.run_language_matrix') as matrix, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--task', 'systolic_matmul', '--output', str(output)]), 0)
        self.assertEqual(runner.call_args.args[2]['language'], 'systemverilog')
        self.assertEqual(runner.call_args.args[5], output)
        matrix.assert_not_called()

    def test_all_selected_data_validated_before_generation(self):
        with patch('rtlflow.cli.load_design_matrix', side_effect=ValueError('invalid requirements')), \
                patch('rtlflow.cli.create_provider') as provider, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--task', 'aes']), 2)
        provider.assert_not_called()
        with self.assertRaises(ValueError):
            load_design_matrix(ROOT/'data/requirements.json', ['aes'], [])

    def test_matrix_artifacts_and_cli_exit_status_without_api_or_compilers(self):
        task_matrix = {language: [TASKS['and2']] for language in ('verilog', 'systemverilog')}
        for groups in (['Skill'], list(GROUPS)):
            output = self.directory/f'groups-{len(groups)}'
            providers, configs = [], []

            def factory(settings):
                configs.append(dict(settings))
                provider = SequenceProvider([GenerationError('offline failure')])
                providers.append(provider)
                return provider

            with patch('rtlflow.cli.load_design_matrix', return_value=task_matrix), \
                    patch('rtlflow.cli.create_provider', side_effect=factory), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--group', *groups, '--output', str(output)]), 1)
            summary = json.loads((output/'summary.json').read_text())
            self.assertEqual(summary['languages'], list(task_matrix))
            self.assertIsNone(summary['language'])
            self.assertEqual(summary['task_count'], 1)
            self.assertEqual(summary['task_language_runs'], 2)
            self.assertEqual(summary['total'], 2 * len(groups))
            self.assertEqual(summary['not_run'], summary['total'])
            self.assertEqual(summary['passed'], 0)
            self.assertEqual(summary['provider_calls'], sum(len(p.messages) for p in providers))
            self.assertEqual(len(providers), 2 * len(groups))
            self.assertEqual([(c['language'], c['group']) for c in configs],
                             [(language, group) for language in task_matrix for group in groups])
            config = json.loads((output/'config.json').read_text())
            self.assertNotIn('language', config)
            self.assertNotIn('group', config)
            self.assertEqual(config['languages'], list(task_matrix))
            self.assertEqual(config['groups'], groups)
            with (output/'summary.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([(r['language'], r['group']) for r in rows],
                             [(language, group) for language in task_matrix for group in groups])
            for language in task_matrix:
                self.assertEqual(summary['by_language'][language]['total'], len(groups))
                for group in groups:
                    parent = output/language/group if len(groups) > 1 else output/language
                    self.assertTrue((parent/'and2/report.json').is_file())
            with patch('rtlflow.cli.create_provider') as provider, \
                    patch('rtlflow.cli.load_design_matrix', return_value=task_matrix), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--group', *groups, '--output', str(output)]), 2)
            provider.assert_not_called()

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_matrix_success_and_failure_counts_after_real_hdl_verification(self):
        task_matrix = {language: [TASKS['and2']] for language in ('verilog', 'systemverilog')}
        settings = {'provider': 'mock', 'tasks': 'unused', 'max_repairs': 0, 'max_refactors': 0}
        for fail_verilog in (False, True):
            output = self.directory/f'verified-{fail_verilog}'

            def factory(config):
                broken = fail_verilog and config['language'] == 'verilog'
                return SequenceProvider([fixture('and2.broken.v' if broken else 'and2.v')])

            with patch('rtlflow.cli.load_design_matrix', return_value=task_matrix), \
                    patch('rtlflow.cli.load_settings', return_value=settings), \
                    patch('rtlflow.cli.create_provider', side_effect=factory), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--output', str(output)]), 1 if fail_verilog else 0)
            summary = json.loads((output/'summary.json').read_text())
            self.assertEqual(summary['total'], 4)
            self.assertEqual(summary['passed'], 2 if fail_verilog else 4)
            self.assertEqual(summary['failed'], 2 if fail_verilog else 0)
            self.assertEqual(summary['not_run'], 0)
            self.assertEqual(summary['by_language']['systemverilog']['passed'], 2)
            self.assertEqual(settings, {'provider': 'mock', 'tasks': 'unused', 'max_repairs': 0, 'max_refactors': 0})

    def test_invalid_matrix_rejected_before_output_and_provider(self):
        for matrix, groups in (({}, GROUPS), ({'bad': [TASKS['and2']]}, GROUPS),
                               ({'verilog': []}, GROUPS), ({'verilog': [TASKS['and2']]}, []),
                               ({'verilog': [TASKS['and2']]}, ['Baseline', 'Baseline'])):
            with patch('rtlflow.cli.create_provider') as provider, self.assertRaises(ValueError):
                run_language_matrix(matrix, provider, {}, RULES, groups, self.directory/'bad')
            provider.assert_not_called()
            self.assertFalse((self.directory/'bad').exists())
