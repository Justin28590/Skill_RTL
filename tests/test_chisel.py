"""Chisel project frontend. Real sbt tests opt in via RTL_CHISEL_INTEGRATION=1."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from helpers import ROOT, RULES, SequenceProvider, SkillHTTPReplay, TemporaryTestCase
from rtlflow.chisel import elaborate_chisel, scala_policy, validate_chisel_config
from rtlflow.cli import main
from rtlflow.pipeline import _run_implementation as run_task
from rtlflow.score import score_readability
from rtlflow.project import bundle_text, load_projects, parse_bundle, verify_project, write_bundle
from rtlflow.providers import GenerationError
from scripts.verify_project_replay import reference_bundle


class ChiselProjectTests(TemporaryTestCase):
    def task(self):
        return load_projects(ROOT/'data/project-rtl/tasks.json', ['chisel_double_buffer_fifo'], 'chisel')[0]

    def test_scala_bundle_protocol_and_build_files_rejected(self):
        good={'rtl/Top.scala':'import chisel3._\nclass Top extends Module { val io = IO(Output(Bool())); io := false.B }\n'}
        self.assertEqual(parse_bundle(bundle_text(good),'chisel'),good)
        for name in ('build.sbt','project/plugins.sbt','rtl/top.sv','../Top.scala','/tmp/Top.scala',
                     '.hidden/A.scala','RTLFlowMain.scala','rtl/RTLFlowMain.scala'):
            with self.subTest(name=name), self.assertRaises(GenerationError):
                parse_bundle(bundle_text({name:'class Top'}),'chisel')

    def test_host_io_blackboxes_and_custom_emitters_rejected(self):
        for text in ('import java.io._','object Start extends App {}','val x = scala.sys.process.Process("x")',
                     'class X extends BlackBox','circt.stage.ChiselStage.emitSystemVerilog(x)',
                     'println("x")','def main(args: Array[String]) = ()','val x = "\\u0061"'):
            self.assertEqual(scala_policy({'Top.scala':text})['status'],'failed',text)
        self.assertEqual(scala_policy(reference_bundle(self.task()))['status'],'passed')

    def test_constructor_contract_rejects_code_injection(self):
        for config in (None, [], [{'module':'Top','class':'Top(); java.lang.System.exit(0)','args':[]}],
                       [{'module':'Top','class':'Top','args':['new File("x")']}],
                       [{'module':'Top','class':'Top','args':[True]}]):
            with self.assertRaises(ValueError): validate_chisel_config(config,['Top'])
        validate_chisel_config([{'module':'Top','class':'pkg.Top','args':[8,{'uint_width':32}]}],['Top'])

    def test_missing_toolchain_is_not_run_and_never_uses_reference(self):
        task=self.task();files=reference_bundle(task)
        source=self.directory/'source';write_bundle(files,source)
        with patch('rtlflow.chisel.ROOT',self.directory), patch('rtlflow.chisel.reference_sources',side_effect=AssertionError('reference read')):
            result=verify_project(files,source,task,self.directory/'checks',{'language':'chisel'})
        self.assertEqual(result['functional_status'],'not_run')
        self.assertIn('missing_chisel_toolchain',result['checks']['elaboration']['reason'])
        self.assertFalse(result['reference_rtl_linked'])

    def test_snapshot_mismatch_is_rejected_before_build(self):
        task=self.task();files=reference_bundle(task)
        source=self.directory/'source';write_bundle(files,source)
        (source/next(iter(files))).write_text('tampered')
        with patch('rtlflow.chisel.elaborate_chisel') as tool:
            result=verify_project(files,source,task,self.directory/'checks',{'language':'chisel'})
        self.assertEqual(result['checks']['source_policy']['reason'],'candidate_snapshot_mismatch')
        tool.assert_not_called()

    def test_check_data_offline_and_language_filtered(self):
        with patch('rtlflow.cli.create_provider') as provider, patch('rtlflow.chisel.elaborate_chisel') as tool, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--language','chisel','--check-data']),0)
        result=json.loads(out.getvalue())
        self.assertGreater(result['total'], 0)
        self.assertEqual(result['workflow'], 'hardware-design-v1')
        provider.assert_not_called();tool.assert_not_called()

    def test_host_owned_multitop_emitter_and_sanitized_environment(self):
        task={'design_tops':['Top','Other'],'chisel_tops':[
            {'module':'Top','class':'pkg.Top','args':[8]}, {'module':'Other','class':'pkg.Other','args':[]}]}
        # No JVM needed. Mock presence and process call, inspect the real prepared build.
        original_exists=Path.exists
        def exists(p):
            return True if str(p).startswith(str(ROOT/'.tools/chisel')) else original_exists(p)
        with patch.object(Path,'exists',exists), patch('rtlflow.chisel.sha256',return_value='a'*64), \
             patch('rtlflow.chisel.run_command',return_value={'status':'failed','reason':'test_compile_error'}) as run:
            result=elaborate_chisel({'Top.scala':'package pkg\nclass Placeholder'},task,self.directory/'work')
        emitter=(self.directory/'work/build/src/main/scala/RTLFlowMain.scala').read_text()
        self.assertIn('new pkg.Top(8)',emitter);self.assertIn('new pkg.Other()',emitter)
        self.assertEqual(run.call_args.kwargs['env'],{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        self.assertIsNone(result['files'])
        self.assertIn('6.5.0',(self.directory/'work/build/build.sbt').read_text())

    @unittest.skipUnless(os.environ.get('RTL_CHISEL_INTEGRATION')=='1','explicit real sbt integration opt-in')
    def test_actual_source_scoring_refactor_and_functional_rollback(self):
        task = self.task()
        good = reference_bundle(task)
        plain = {name: re.sub(r'/\*[\s\S]*?\*/', '', code) for name, code in good.items()}
        broken = {name: code.replace('io.deq.bits := dataReg', 'io.deq.bits := 0.U')
                  for name, code in good.items()}
        original_score = score_readability('\n'.join(plain.values()), 'chisel')['score']
        for case, candidate, accepted in [('improved', good, True), ('regressed', broken, False)]:
            with self.subTest(case=case):
                provider = SequenceProvider([bundle_text(plain), bundle_text(candidate)])
                report = run_task(task, provider, {'language': 'chisel', 'group': 'Baseline',
                    'max_repairs': 0, 'max_refactors': 1, 'readability_threshold': 95},
                    RULES, self.directory / case)
                self.assertEqual(report['functional_status'], 'passed')
                self.assertEqual(report['refactor_calls'], 1)
                self.assertEqual(report['attempts'][1]['refactor_accepted'], accepted)
                self.assertEqual(report['selected_attempt'], int(accepted))
                self.assertEqual(report['readability_method'], 'static-chisel-heuristic-v1')
                self.assertEqual(report['readability_score'], original_score + (10 if accepted else 0))
                self.assertEqual(parse_bundle(Path(report['final_bundle']).read_text(), 'chisel'),
                                 good if accepted else plain)
                selected = report['attempts'][int(accepted)]
                for path in Path(report['final_rtl']).glob('*.sv'):
                    self.assertEqual(path.read_text(), (Path(selected['rtl_path']) / path.name).read_text())
                if not accepted:
                    checks = report['attempts'][1]['verification']['checks']
                    self.assertEqual(checks['elaboration']['status'], 'passed')
                    self.assertEqual(checks['simulation']['status'], 'failed')

    @unittest.skipUnless(os.environ.get('RTL_CHISEL_INTEGRATION')=='1','explicit real sbt integration opt-in')
    def test_actual_multifile_missing_child_repair_and_emitted_delivery(self):
        task=self.task();good=reference_bundle(task)
        bad={name:code for name,code in good.items() if name!='DoubleBufferFifo.scala'}
        replay=SkillHTTPReplay([bundle_text(bad),bundle_text(good)])
        output=self.directory/'run'
        with patch.dict(os.environ,{'GLM_API_KEY':'UNIT_ONLY_FAKE_KEY'}), \
             patch('rtlflow.providers.urllib.request.urlopen',side_effect=replay), \
             patch('rtlflow.chisel.reference_sources',side_effect=AssertionError('candidate reads reference')), \
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            status=main(['--language','chisel','--task',task['id'],'--group','Skill','--output',str(output)])
        self.assertEqual(status,0)
        report=json.loads((output/task['id']/'report.json').read_text())
        self.assertTrue(report['repair_success']);self.assertEqual(report['provider_calls'],2)
        self.assertEqual(report['attempts'][0]['verification']['checks']['elaboration']['status'],'failed')
        self.assertTrue((Path(report['final_source'])/'Fifo.scala').is_file())
        self.assertTrue(list(Path(report['final_rtl']).glob('*.sv')))
        self.assertNotEqual(report['final_source'],report['final_rtl'])
        self.assertNotEqual(report['source_sha256'],report['rtl_sha256'])
        self.assertEqual(report['readability_status'],'passed')
        self.assertEqual(report['readability_method'],'static-chisel-heuristic-v1')
        self.assertEqual(report['readability_score'],score_readability('\n'.join(good.values()),'chisel')['score'])
        self.assertGreaterEqual(report['attempts'][1]['verification']['checks']['hierarchy']['module_type_count'],2)
        for request in replay.requests:
            self.assertNotIn('EXPANSION_PASS',json.dumps(request))
            self.assertNotIn('UNIT_ONLY_FAKE_KEY',json.dumps(request))
