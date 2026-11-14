"""Actual corpus integration, not a model capability benchmark."""
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, SkillHTTPReplay, TemporaryTestCase
from rtlflow.cli import main
from rtlflow.project import bundle_text, load_projects, masked, verify_project, write_bundle
from rtlflow.project_dataset import sha256
from scripts.verify_project_replay import reference_bundle


class ProjectGenerationDataTests(TemporaryTestCase):
    def test_layout_has_one_spec_per_task_and_separate_tests(self):
        root = ROOT / 'data/project-rtl'
        catalog = json.loads((root / 'tasks.json').read_text())
        self.assertEqual(catalog['schema_version'], 'project-rtl-v2')
        self.assertEqual({p.name for p in root.iterdir() if p.is_dir()}, {'specs', 'sources', 'tests'})
        specifications = {t['specification'] for t in catalog['tasks']}
        self.assertEqual(len(specifications), 32)
        self.assertEqual(specifications, {str(p.relative_to(root)) for p in (root / 'specs').glob('*.md')})
        for task in catalog['tasks']:
            self.assertNotIn('public_specification', task)
            self.assertNotIn('contract', task['generation'])
            self.assertEqual(task['specification_sha256'], sha256(root / task['specification']))
            self.assertTrue(all(p.startswith('tests/') for p in task['generation']['candidate_testbench_files']))

    def test_all_projects_have_public_contracts_blackbox_tests_and_parameters(self):
        tasks=load_projects(ROOT/'data/project-rtl/tasks.json',language='systemverilog')
        tasks+=load_projects(ROOT/'data/project-rtl/tasks.json',language='chisel')
        self.assertEqual(len(tasks),32)
        for task in tasks:
            self.assertIn('## 顶层接口',task['contract_text'])
            self.assertIn('## 编译配置',task['contract_text'])
            self.assertEqual(set(task['public_parameters']),set(task['design_tops']))
            self.assertTrue(task['candidate_testbench_files'])
            self.assertFalse(any('/src/rtl/' in name for name in task['candidate_testbench_files']))
            for name in task['candidate_testbench_files']:
                text=masked((Path(task['dataset_root'])/name).read_text())
                self.assertNotIn('dut.core.',text)
                self.assertNotIn('dut.cmac_inst.',text)
                self.assertNotIn('dut.block_reg',text)
        cmac=next(t for t in tasks if t['id']=='cmac')
        self.assertTrue(any('K1/K2' in item for v in cmac['testbench_adaptations'].values() for item in v['changes']))
        self.assertIn('51级',next(t for t in tasks if t['id']=='triple_des')['contract_text'])
        self.assertIn('0x03020100',next(t for t in tasks if t['id']=='md5')['contract_text'])

    @unittest.skipUnless(os.environ.get("RTL_VALIDATE_EVIDENCE") == "1",
                         "local evidence check: set RTL_VALIDATE_EVIDENCE=1 (see docs/验收.md)")
    def test_published_candidate_evidence_matches_current_validator_and_sources(self):
        base=ROOT/'artifacts/project-rtl/candidate'
        for language in ('verilog','systemverilog','chisel'):
            directory=base/language
            summary=json.loads((directory/'summary.json').read_text())
            count={'verilog':27,'systemverilog':30,'chisel':2}[language]
            self.assertEqual((summary['total'],summary['passed'],summary['negative_controls_passed']),(count,count,count))
            self.assertEqual(summary['model_calls'],0)
            self.assertEqual(summary['manifest_sha256'],sha256(ROOT/'data/project-rtl/tasks.json'))
            for name,value in summary['validator_sha256'].items():
                self.assertEqual(sha256(ROOT/name),value,name)
            for task in summary['tasks']:
                report_path=directory/task['report']
                self.assertEqual(sha256(report_path),task['report_sha256'])
                result=json.loads(report_path.read_text())
                self.assertFalse(result['reference_rtl_linked'])
                self.assertEqual(result['functional_status'],'passed')
                self.assertEqual(result['negative_control_status'],'passed')
                self.assertEqual(result['negative_control']['checks']['compile']['status'],'passed')
                for name,value in result['source_sha256'].items():
                    self.assertEqual(sha256(report_path.parent/'source'/name),value)
                    self.assertEqual(sha256(report_path.parent/'negative/source'/name),value)
                self.assertEqual(sha256(report_path.parent/'negative/fault.v'),result['fault_sha256'])
                for name,value in result['logs_sha256'].items():
                    self.assertEqual(sha256(report_path.parent/name),value)

    def test_task_selection_and_unsupported_language_rejected(self):
        path=ROOT/'data/project-rtl/tasks.json'
        self.assertEqual([t['id'] for t in load_projects(path,['wbuart32'])],['wbuart32'])
        with self.assertRaises(ValueError):load_projects(path,['and2'])
        self.assertEqual(len(load_projects(path,language='chisel')),2)
        with self.assertRaisesRegex(ValueError,'不支持'):load_projects(path,['aes'],language='chisel')
        legacy=self.directory/'legacy.json'
        legacy.write_text('{"schema_version":"project-generation-v1"}')
        with self.assertRaises(ValueError):load_projects(legacy)

    @unittest.skipUnless(HAS_ICARUS,'requires Icarus/vvp')
    def test_real_project_cli_fake_http_missing_fifo_then_repair(self):
        task=load_projects(ROOT/'data/project-rtl/tasks.json',['wbuart32'])[0]
        good=reference_bundle(task)
        bad={name:code for name,code in good.items() if name!='ufifo.v'}
        replay=SkillHTTPReplay([bundle_text(bad),bundle_text(good)])
        output=self.directory/'real-uart-project'
        with patch.dict(os.environ,{'GLM_API_KEY':'UNIT_ONLY_FAKE_KEY'},clear=True), \
                patch('rtlflow.providers.urllib.request.urlopen',side_effect=replay), \
                contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            status=main(['--task','wbuart32','--group','Skill','--output',str(output)])
        self.assertEqual(status,0)
        report=json.loads((output/'wbuart32/report.json').read_text())
        self.assertTrue(report['repair_success'])
        self.assertEqual(report['provider_calls'],3)
        self.assertEqual(report['model_calls'],9)
        self.assertEqual(report['refactor_calls'],1)
        self.assertEqual(report['stop_reason'],'refactor_rejected_rolled_back')
        self.assertEqual(report['attempts'][1]['verification']['checks']['hierarchy']['module_type_count'],4)
        self.assertTrue((Path(report['final_source'])/'ufifo.v').is_file())
        for request in replay.requests:
            text=json.dumps(request)
            self.assertNotIn('PROJECT_RTL_PASS wbuart32',text)
            self.assertNotIn('setup readback',text)
            self.assertNotIn('UNIT_ONLY_FAKE_KEY',text)
        self.assertFalse(report['attempts'][1]['verification']['reference_rtl_linked'])

    @unittest.skipUnless(HAS_ICARUS,'requires Icarus/vvp')
    def test_cmac_no_longer_requires_internal_state_names(self):
        task=load_projects(ROOT/'data/project-rtl/tasks.json',['cmac'])[0]
        files=reference_bundle(task)
        # Change every original cmac wrapper/core local register/instance name used by the old TB.
        for name in files:
            if name in ('cmac.v','cmac_core.v'):
                for token in ('cmac_inst','block_reg','key_reg','k1_reg','k2_reg','result_reg','final_size_reg'):
                    files[name]=files[name].replace(token,'candidate_'+token)
        source=self.directory/'candidate';write_bundle(files,source)
        result=verify_project(files,source,task,self.directory/'checks',{'tool_timeout_seconds':15})
        self.assertEqual(result['functional_status'],'passed',result['checks']['compile'])

    @unittest.skipUnless(HAS_ICARUS,'requires Icarus/vvp')
    def test_cpu_software_pass_messages_do_not_replace_independent_results(self):
        task=load_projects(ROOT/'data/project-rtl/tasks.json',['picorv32_axi'])[0]
        files=reference_bundle(task)
        fault=self.directory/'signature_fault.v'
        fault.write_text('module signature_fault; initial begin\n'
                         'force testbench.project_signature.dut.mem_axi_wdata = 0;\n'
                         'repeat(45) $display("..OK"); $display("ALL TESTS PASSED.");\n'
                         'end endmodule\n')
        task['candidate_testbench_files']=[*task['candidate_testbench_files'],str(fault)]
        task['testbench_tops']=[*task['testbench_tops'],'signature_fault']
        source=self.directory/'candidate';write_bundle(files,source)
        result=verify_project(files,source,task,self.directory/'checks',{'tool_timeout_seconds':15})
        self.assertEqual(result['checks']['compile']['status'],'passed')
        self.assertEqual(result['checks']['interface']['status'],'passed')
        self.assertEqual(result['checks']['hierarchy']['status'],'passed')
        self.assertEqual(result['functional_status'],'failed')
        verdict=result['checks']['simulation']['verdict']
        self.assertTrue(all(count >= rule['min_count'] for count,rule in
                            zip(verdict['positive_match_counts'][:-1],task['required_output'][:-1])))
        self.assertIn('independent CPU arithmetic signature',result['checks']['simulation']['stdout'])

    @unittest.skipUnless(HAS_ICARUS,'requires Icarus/vvp')
    def test_required_public_parameter_not_just_silently_ignored(self):
        task=load_projects(ROOT/'data/project-rtl/tasks.json',['wbuart32'])[0]
        files=reference_bundle(task)
        files['wbuart.v']=files['wbuart.v'].replace('HARDWARE_FLOW_CONTROL_PRESENT','RENAMED_PARAMETER')
        source=self.directory/'candidate';write_bundle(files,source)
        result=verify_project(files,source,task,self.directory/'checks',{'tool_timeout_seconds':10})
        self.assertEqual(result['functional_status'],'failed')
        self.assertEqual(result['checks']['interface']['reason'],'missing_public_parameters')
        self.assertEqual(result['checks']['simulation']['status'],'not_run')
