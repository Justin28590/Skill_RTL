import contextlib
import io
import json
import re
from unittest.mock import patch

from helpers import ROOT, RULES, TASKS, TemporaryTestCase, fixture
from rtlflow.cli import load_settings, main
from rtlflow.pipeline import initial_messages
from rtlflow.project import bundle_text, parse_bundle
from rtlflow.providers import GenerationError
from rtlflow.score import score_readability


class CoreTests(TemporaryTestCase):
    def test_project_bundle_roundtrip_and_unique_json_fence(self):
        text = fixture('and2.v')
        self.assertEqual(bundle_text(parse_bundle(text)), text)
        self.assertEqual(parse_bundle('```json\n'+text+'```'), parse_bundle(text))
        for response in ('no code', 'module dut; endmodule', text+'\n'+text, '```json\n'+text+'```\nexplanation'):
            with self.assertRaises(GenerationError): parse_bundle(response)

    def test_readability_rules_unchanged(self):
        code = parse_bundle(fixture('and2.v'))['child.v']
        clean = score_readability(code)
        self.assertEqual(sum(d['weight'] for d in clean['dimensions'].values()), 100)
        self.assertGreater(clean['score'], score_readability(code.replace('    ', '\t'))['score'])
        self.assertEqual(clean['score'], 94)
        self.assertEqual(clean['method'], 'static-heuristic-v1')
        sv = score_readability(code.replace('wire', 'logic'), 'systemverilog')
        self.assertEqual(sv['score'], 94)
        self.assertEqual(sv['method'], 'static-sv-heuristic-v1')

    def test_prompts_use_only_public_contract(self):
        task = {**TASKS['and2'], 'reference': 'SECRET_REFERENCE', 'testbench_path': 'SECRET_TB',
                'required_output': 'SECRET_VERDICT', 'contract_text': 'PUBLIC_CONTRACT_SENTINEL'}
        for language in ('verilog', 'systemverilog'):
            for group in ('Baseline', 'Skill'):
                messages = initial_messages(task, group, RULES, language)
                system, user = [m['content'] for m in messages]
                self.assertIn('PUBLIC_CONTRACT_SENTINEL', user)
                self.assertNotIn('PUBLIC_CONTRACT_SENTINEL', system)
                self.assertNotIn('rtl-readable', system)
                self.assertEqual(user.startswith('请调用 rtl-readable Skill，'), group == 'Skill')
                self.assertEqual('read_skill' in system, group == 'Skill')
                self.assertNotIn(RULES, system+user)
                for secret in ('SECRET_REFERENCE', 'SECRET_TB', 'SECRET_VERDICT'):
                    self.assertNotIn(secret, system+user)
                self.assertIn('完整 JSON', system)
                self.assertIn('所有文件', system)

    def test_bad_config_fields_and_limits(self):
        path = self.directory/'config.json'
        for extra in ({'max_repairs':-1}, {'max_refactors':11}, {'api_key':'secret'},
                      {'tool_timeout_seconds':0}, {'temperature':float('nan')},
                      {'max_repairs':True}, {'max_tokens':0}, {'provider':'unknown'},
                      *({'group': group} for group in 'ABCD')):
            path.write_text(json.dumps({'provider':'glm','tasks':'tasks.json',**extra}))
            with self.assertRaises(ValueError):load_settings(path)

    def test_first_party_document_links_exist(self):
        documents = [ROOT/'README.md', ROOT/'tests/README.md', ROOT/'data/README.md', ROOT/'data/project-rtl/README.md',
                     *sorted((ROOT/'docs').glob('*.md'))]
        for document in documents:
            for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', document.read_text()):
                if '://' in target or target.startswith('#'):
                    continue
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / target.split('#', 1)[0]).exists())

    def test_invalid_cli_inputs_fail_before_provider(self):
        for args in (['--task','and2'], ['--language','chisel','--task','aes'], ['--config','missing.json']):
            with patch('rtlflow.cli.create_provider') as provider, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
                provider.assert_not_called()
