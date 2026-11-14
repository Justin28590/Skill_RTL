import copy
import signal
import sys
import unittest
from unittest.mock import Mock, patch

from helpers import HAS_ICARUS, TASKS, TemporaryTestCase, fixture
from rtlflow.project import bundle_text, include_policy, parse_bundle, verify_project, write_bundle
from rtlflow.providers import GenerationError
from rtlflow.verify import run_command


class ProcessTests(TemporaryTestCase):
    def test_timeout_is_failure_with_saved_logs(self):
        result=run_command([sys.executable,'-c',"import time; print('start',flush=True); time.sleep(5)"],
                           self.directory,'timeout',0.2)
        self.assertEqual(result['reason'],'timeout');self.assertIn('start',result['stdout'])

    def test_missing_executable_not_run(self):
        self.assertEqual(run_command(['/does/not/exist'],self.directory,'missing',1)['status'],'not_run')

    def test_interrupt_kills_process_group(self):
        process=Mock(pid=12345);process.wait.side_effect=[KeyboardInterrupt(),None]
        with patch('rtlflow.verify.subprocess.Popen',return_value=process),patch('rtlflow.verify.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):run_command(['unused'],self.directory,'interrupt',1)
        kill.assert_called_once_with(12345,signal.SIGKILL)


class BundleGuards(TemporaryTestCase):
    def test_unsafe_duplicate_and_conflicting_paths_rejected_before_write(self):
        for name in ('/tmp/escape.v','../escape.v','a/../b.v','a\\b.v','.secret.v','a/.hidden/file.v','a//b.v','a/./b.v','build.py'):
            with self.subTest(name=name),self.assertRaises(GenerationError):
                parse_bundle(bundle_text({name:'module x; endmodule'}))
        for text in ('{"files":[],"files":[]}',
                     '{"files":[{"path":"a.v","path":"b.v","content":"module x; endmodule"}]}',
                     '{"files":[{"path":"a.v","content":"x"},{"path":"a.v","content":"y"}]}'):
            with self.assertRaises(GenerationError):parse_bundle(text)
        with self.assertRaises(GenerationError):parse_bundle(bundle_text({'a.v':'x','a.v/child.v':'y'}))

    def test_size_empty_and_extra_fields_rejected(self):
        for text in ('{"files":[]}', '{"files":[],"command":"shell"}',
                     '{"files":[{"path":"x.v","content":""}]}',
                     bundle_text({f'x{i}.v':'module x; endmodule' for i in range(129)})):
            with self.assertRaises(GenerationError):parse_bundle(text)
        with self.assertRaises(GenerationError):parse_bundle(bundle_text({'x.v':'x'*2_000_001}))

    def test_disk_changes_or_symlinks_rejected_before_execution(self):
        files=parse_bundle(fixture('and2.v'))
        source=self.directory/'source';write_bundle(files,source)
        (source/'child.v').write_text('module changed; endmodule\n')
        result=verify_project(files,source,TASKS['and2'],self.directory/'check1',{})
        self.assertEqual(result['checks']['source_policy']['reason'],'candidate_snapshot_mismatch')
        external=self.directory/'external.v';external.write_text(files['child.v'])
        (source/'child.v').unlink();(source/'child.v').symlink_to(external)
        result=verify_project(files,source,TASKS['and2'],self.directory/'check2',{})
        self.assertEqual(result['checks']['source_policy']['reason'],'candidate_snapshot_mismatch')
        self.assertEqual(result['checks']['preprocess']['status'],'not_run')

    def test_external_macro_and_traversal_includes_rejected(self):
        for code in ('`include "/etc/passwd"','`include "../secret.v"','`include `PATH',
                     '`define P `include "secret.v"','`line 1 "other.v" 0','`define A a``b'):
            self.assertEqual(include_policy({'top.v':code})['status'],'failed',code)


@unittest.skipUnless(HAS_ICARUS,'requires iverilog/vvp')
class VerificationTests(TemporaryTestCase):
    def check(self,files=None,task=None,settings=None):
        files=files or parse_bundle(fixture('and2.v'))
        count=len(list(self.directory.iterdir()))
        source=self.directory/f'source{count}';work=self.directory/f'checks{count}'
        write_bundle(files,source)
        return verify_project(files,source,task or TASKS['and2'],work,settings or {'tool_timeout_seconds':1})

    def test_compile_is_not_functional_success_and_x_outputs_fail(self):
        for expression in ("1'b0","1'bx"):
            files=parse_bundle(fixture('and2.v'));files['child.v']=files['child.v'].replace('a & b',expression)
            result=self.check(files)
            self.assertEqual(result['checks']['compile']['status'],'passed')
            self.assertEqual(result['functional_status'],'failed')

    def test_missing_submodule_rejected_without_reference_fallback(self):
        files=parse_bundle(fixture('and2.v'));del files['child.v']
        result=self.check(files)
        self.assertFalse(result['reference_rtl_linked'])
        self.assertEqual(result['checks']['candidate_compile']['status'],'failed')
        self.assertEqual(result['checks']['simulation']['status'],'not_run')

    def test_safe_nested_project_local_include(self):
        files=parse_bundle(fixture('and2.v'))
        files['include/defs.vh']='`define BOOL_AND(a,b) ((a)&(b))\n'
        files['child.v']='`include "include/defs.vh"\n'+files['child.v'].replace('a & b','`BOOL_AND(a,b)')
        self.assertEqual(self.check(files)['functional_status'],'passed')

    def test_macros_cannot_hide_system_tasks_or_reference_files(self):
        for extra in ('initial $display("UNIT_PROJECT_PASS");',
                      '`define STOP $finish\ninitial `STOP;','initial $readmemh("/etc/passwd",mem);',
                      'wire z=tb.dut.y;','wire z=tb[0].secret;','initial force tb.flag=1;',
                      'class SoftwareOnly; int x; endclass',
                      'import "DPI-C" function int system(input string command);'):
            files=parse_bundle(fixture('and2.v'))
            files['child.v']=files['child.v'].replace('endmodule',extra+'\nendmodule')
            result=self.check(files)
            self.assertEqual(result['checks']['source_policy']['status'],'failed',extra)
            self.assertEqual(result['checks']['simulation']['status'],'not_run')

    def test_candidate_macros_cannot_disable_trusted_checks(self):
        files=parse_bundle(fixture('and2.broken.v'))
        files['top.v']='`define SKIP_TEST\n'+files['top.v']
        task=copy.deepcopy(TASKS['and2'])
        tb=self.directory/'guarded.v'
        tb.write_text('module tb; wire y; and2 dut(1\'b1,1\'b1,y); initial begin #1;\n'
                      '`ifndef SKIP_TEST\nif(y !== 1\'b1) $fatal(1,"wrong");\n`endif\n'
                      '$display("UNIT_PROJECT_PASS"); $finish; end endmodule\n')
        task.update(dataset_root=str(self.directory),candidate_testbench_files=[tb.name])
        result=self.check(files,task)
        self.assertEqual(result['checks']['compile']['status'],'passed')
        self.assertEqual(result['functional_status'],'failed')
        self.assertNotIn('`define',__import__('pathlib').Path(result['checks']['candidate_compile']['command'][-1]).read_text())

    def test_testbench_cannot_supply_a_missing_design_module(self):
        files=parse_bundle(fixture('and2.v'))
        leaf=self.directory/'reference.v';leaf.write_text(files.pop('child.v'))
        task=copy.deepcopy(TASKS['and2'])
        task['candidate_testbench_files'].append(str(leaf))
        result=self.check(files,task)
        self.assertEqual(result['checks']['candidate_compile']['status'],'failed')
        self.assertEqual(result['checks']['compile']['status'],'not_run')

    def test_parameter_branch_cannot_borrow_testbench_design_logic(self):
        task=copy.deepcopy(TASKS['and2'])
        tb=self.directory/'parameter_tb.v'
        tb.write_text('module tb; wire y; and2 #(.PROFILE(1)) dut(1\'b1,1\'b1,y); '
                      'initial begin #1; if(y !== 1) $fatal; $display("UNIT_PROJECT_PASS"); $finish; end endmodule\n'
                      'module hidden_helper(input a,b,output y); assign y=a&b; endmodule\n')
        task.update(dataset_root=str(self.directory),candidate_testbench_files=[tb.name])
        files=parse_bundle(fixture('and2.v'))
        files['top.v']='''module and2 #(parameter PROFILE=0)(input a,b,output y);
          generate if(PROFILE) begin
            hidden_helper borrowed(a,b,y);
          end else begin
            and2_leaf own(a,b,y);
          end endgenerate
        endmodule
        '''
        result=self.check(files,task)
        self.assertEqual(result['checks']['candidate_compile']['status'],'passed')
        self.assertEqual(result['checks']['compile']['status'],'passed')
        self.assertEqual(result['checks']['hierarchy']['reason'],'non_candidate_design_dependency')
        self.assertEqual(result['checks']['simulation']['status'],'not_run')

    def test_extra_top_ports_are_not_silently_accepted(self):
        files=parse_bundle(fixture('and2.v'));files['top.v']=files['top.v'].replace('output wire [0:0] y','output wire [0:0] y, output extra')
        result=self.check(files)
        self.assertEqual(result['checks']['interface']['status'],'failed')
        self.assertEqual(result['checks']['simulation']['status'],'not_run')

    def test_monolithic_placeholder_not_project_hierarchy(self):
        files={'top.v':'module and2(input a,b,output y); assign y=a&b; endmodule\n'}
        result=self.check(files)
        self.assertEqual(result['checks']['hierarchy']['status'],'failed')

    def test_zero_exit_or_pass_marker_cannot_hide_failure(self):
        for text in ('$finish;', '$display("UNIT_PROJECT_PASS"); $display("ERROR: incorrect"); $finish;',
                     '$display("UNIT_PROJECT_PASS"); $fatal(1,"incorrect");'):
            task=copy.deepcopy(TASKS['and2'])
            original=__import__('pathlib').Path(task['dataset_root'])/task['candidate_testbench_files'][0]
            tb=self.directory/f'tb{len(list(self.directory.iterdir()))}.v'
            # Keep DUT connected/elaborated but deliberately weaken/corrupt the TB verdict.
            tb.write_text('module tb; wire y; and2 dut(1\'b0,1\'b0,y); initial begin #1; '+text+' end endmodule')
            task['dataset_root']=str(self.directory);task['candidate_testbench_files']=[tb.name]
            result=self.check(task=task)
            self.assertEqual(result['functional_status'],'failed')

    def test_simulation_timeout_is_bounded(self):
        task=copy.deepcopy(TASKS['and2'])
        tb=self.directory/'timeout_tb.v'
        tb.write_text("module tb; reg a=0; always #1 a=~a; wire y; and2 dut(a,a,y); endmodule")
        task.update(dataset_root=str(self.directory),candidate_testbench_files=[tb.name],simulation_timeout_seconds=0.1)
        result=self.check(task=task,settings={'tool_timeout_seconds':0.2})
        self.assertEqual(result['checks']['simulation']['reason'],'timeout')
