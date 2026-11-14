import contextlib
import csv
import io
import json
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, RULES, TASKS, SequenceProvider, ImplementationTestCase as TemporaryTestCase, fixture
from rtlflow.cli import main, planned_calls
from rtlflow.pipeline import GROUPS, run_group_comparison, _run_implementation as run_task
from rtlflow.providers import GenerationError
from rtlflow.skill_tools import SKILL_RELOAD_REQUEST


class ComparisonTests(TemporaryTestCase):
    def test_default_all_groups_and_explicit_subset(self):
        for args, groups in (([], list(GROUPS)),
                             (['--group', 'Skill', 'Baseline'], ['Skill', 'Baseline'])):
            with self.subTest(args=args), \
                    patch('rtlflow.cli.run_group_comparison', return_value={'passed': 1, 'total': 1}) as runner, \
                    patch('rtlflow.cli.create_provider'), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--language', 'verilog', '--task', 'aes', *args]), 0)
                self.assertEqual(runner.call_args.args[4], groups)

    def test_single_group_and_offline_check_matrix(self):
        for group in GROUPS:
            with patch('rtlflow.cli.create_provider'), \
                    patch('rtlflow.cli.run_batch', return_value={'passed': 1, 'total': 1}) as batch, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--language', 'verilog', '--task', 'aes', '--group', group]), 0)
                self.assertEqual(batch.call_args.args[2]['group'], group)
        with patch('rtlflow.cli.create_provider') as provider, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--language', 'verilog', '--check-data', '--task', 'aes', '--task', 'cmac']), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result['total'], 2)
            self.assertEqual(result['groups'], list(GROUPS))
            self.assertEqual(result['task_group_runs'], 4)
            self.assertEqual(result['max_provider_calls'], 48)
            self.assertEqual(result['max_model_calls'], 168)
            self.assertEqual(result['model_calls'], 0)
            provider.assert_not_called()

    def test_old_and_duplicate_cli_groups_are_rejected(self):
        for args in ([ '--group', g] for g in 'ABCD'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--group', 'Baseline', 'Baseline'])

    def test_invalid_groups_empty_tasks_and_existing_output_rejected(self):
        for groups, tasks in (([], [TASKS['and2']]), (['Baseline', 'Baseline'], [TASKS['and2']]),
                              (['X'], [TASKS['and2']]), (['A'], [TASKS['and2']]), (['Baseline'], [])):
            with self.assertRaises(ValueError):
                run_group_comparison(tasks, lambda _: None, {}, RULES, groups, self.directory/'bad')
        path = self.directory/'existing'
        path.mkdir()
        with self.assertRaises(FileExistsError):
            run_group_comparison([TASKS['and2']], lambda _: None, {}, RULES, ['Baseline'], path)
        for group in 'ABCD':
            provider = SequenceProvider(['unused'])
            with self.assertRaises(ValueError):
                run_task(TASKS['and2'], provider, {'group': group}, RULES, self.directory/'bad')
            self.assertEqual(provider.messages, [])
        self.assertFalse((self.directory/'bad').exists())

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_groups_have_independent_projects_and_equal_feedback_and_budgets(self):
        providers, configs = [], []

        def factory(settings):
            configs.append(settings)
            provider = SequenceProvider([fixture('and2.broken.v'), fixture('and2.v')])
            providers.append(provider)
            return provider

        settings = {'max_repairs': 1, 'max_refactors': 1, 'readability_threshold': 100}
        with patch('rtlflow.pipeline.score_readability', return_value={'score': 50, 'status': 'passed'}):
            summary = run_group_comparison([TASKS['and2']], factory, settings, RULES, GROUPS, self.directory/'run')
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['passed'], 2)
        self.assertEqual([len(p.messages) for p in providers], [3, 3])
        self.assertEqual([{k: v for k, v in c.items() if k != 'group'} for c in configs], [settings, settings])
        self.assertEqual([s is not None for s in providers[0].skills], [False]*3)
        self.assertEqual([s is not None for s in providers[1].skills], [True]*3)
        # Previous candidate and diagnostic feedback stay identical; only Skill's
        # fresh-session loading instruction differs, not the repair task or budget.
        for index in (1, 2):
            baseline, skill = providers[0].messages[index], providers[1].messages[index]
            self.assertEqual(baseline[2], skill[2])
            self.assertEqual(skill[3], {'role': 'user', 'content': SKILL_RELOAD_REQUEST + baseline[3]['content']})
        rows = summary['by_task']['and2']
        for group in GROUPS:
            row = rows[group]
            self.assertEqual(row['functional_status'], 'passed')
            self.assertEqual(row['initial_functional_status'], 'failed')
            self.assertEqual(row['effective_max_repairs'], 1)
            self.assertEqual(row['effective_max_refactors'], 1)
            self.assertEqual(row['repair_calls'], 1)
            self.assertEqual(row['refactor_calls'], 1)
            self.assertEqual(row['stop_reason'], 'refactor_rejected_rolled_back')
            self.assertEqual(row['skill_requested'], group == 'Skill')
        self.assertNotEqual(rows['Baseline']['final_source'], rows['Skill']['final_source'])
        with (self.directory/'run/summary.csv').open() as stream:
            csv_rows = list(csv.DictReader(stream))
        self.assertEqual([r['group'] for r in csv_rows], list(GROUPS))
        self.assertEqual([r['effective_max_repairs'] for r in csv_rows], ['1', '1'])

    def test_zero_and_custom_budgets_are_shared(self):
        for repairs, refactors in ((0, 0), (3, 2)):
            settings = {'provider': 'glm', 'max_repairs': repairs, 'max_refactors': refactors, 'max_agent_turns': 6}
            attempts = 1 + repairs + refactors
            self.assertEqual(planned_calls(settings, GROUPS, 2),
                             {'max_provider_calls': 4*(attempts+8), 'max_model_calls': 14*(attempts+8)})
            for group in GROUPS:
                summary = run_group_comparison([TASKS['and2']], lambda _: SequenceProvider(['not JSON']),
                                              settings, RULES, [group], self.directory/f'{group}-{repairs}')
                row = summary['by_task']['and2'][group]
                self.assertEqual(row['repair_calls'], repairs)
                self.assertEqual(row['refactor_calls'], 0)
                self.assertEqual(row['effective_max_refactors'], refactors)

    def test_provider_failure_does_not_skip_remaining_groups(self):
        summary = run_group_comparison([TASKS['and2']], lambda _: SequenceProvider([GenerationError('offline failure')]),
                                       {}, RULES, GROUPS, self.directory/'run')
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['not_run'], 2)
        self.assertEqual(summary['provider_calls'], 2)
