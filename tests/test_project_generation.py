"""Actual corpus integration, not a model capability benchmark."""
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, SkillHTTPReplay, ImplementationTestCase as TemporaryTestCase
from rtlflow.cli import main
from rtlflow.project import bundle_text, load_projects, verify_project, write_bundle
from scripts.verify_project_replay import reference_bundle


class ProjectGenerationDataTests(TemporaryTestCase):
    def test_catalog_has_public_contracts_and_separate_test_adapters(self):
        path = ROOT / 'data/project-rtl/tasks.json'
        catalog = json.loads(path.read_text())
        tasks = load_projects(path, language='systemverilog') + load_projects(path, language='chisel')
        self.assertTrue(tasks)
        self.assertCountEqual([t['id'] for t in tasks], [t['id'] for t in catalog['tasks']])
        self.assertEqual(len({t['contract'] for t in tasks}), len(tasks))
        for task in tasks:
            with self.subTest(task=task['id']):
                self.assertTrue(task['contract_text'].strip())
                self.assertEqual(set(task['public_parameters']), set(task['design_tops']))
                self.assertTrue(task['candidate_testbench_files'])
                self.assertTrue(all(p.startswith('tests/') for p in task['candidate_testbench_files']))

    @unittest.skipUnless(HAS_ICARUS,'requires Icarus/vvp')
    def test_archived_project_implementation_fake_http_missing_fifo_then_repair(self):
        task=load_projects(ROOT/'data/project-rtl/tasks.json',['wbuart32'])[0]
        good=reference_bundle(task)
        bad={name:code for name,code in good.items() if name!='ufifo.v'}
        replay=SkillHTTPReplay([bundle_text(bad),bundle_text(good)])
        output=self.directory/'real-uart-project'
        with patch.dict(os.environ,{'GLM_API_KEY':'UNIT_ONLY_FAKE_KEY'},clear=True), \
                patch('rtlflow.providers.urllib.request.urlopen',side_effect=replay), \
                patch('rtlflow.cli.load_design_matrix', return_value={'verilog': [task]}), \
                contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            status=main(['--language','verilog','--task','wbuart32','--group','Skill','--output',str(output)])
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
