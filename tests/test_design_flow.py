"""Requirements-first workflow; all model calls are offline, HDL checks are real."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT, RULES, SequenceProvider, TemporaryTestCase
from rtlflow.design import SCHEMA, design_messages, load_design_matrix, validate_contract, width
from rtlflow.design_verify import bind_verification, validate_testbench
from rtlflow.pipeline import run_task, run_group_comparison
from rtlflow.project import bundle_text
from rtlflow.providers import GenerationError

APPROVE = json.dumps({"accepted": True, "issues": [], "rationale": "All requirements, reset, timing and independent checks reviewed."})


def example(name="ChosenAdder", delay=0):
    ports = {
        "left_data": {"direction": "input", "width": "BITS", "signed": False, "description": "unsigned left operand"},
        "right_data": {"direction": "input", "width": "BITS", "signed": False, "description": "unsigned right operand"},
        "sum_data": {"direction": "output", "width": "BITS+1", "signed": False, "description": "full unsigned sum"},
    }
    if delay:
        ports.update(clk={"direction": "input", "width": 1, "signed": False, "description": "rising clock"},
                     reset={"direction": "input", "width": 1, "signed": False, "description": "synchronous active high reset"})
    contract = {"schema_version": 1, "description": "Full width adder with actual arithmetic child; chosen latency.",
        "tops": [{"name": name, "parameters": {"BITS": 8}, "ports": ports,
                  "timing": "Combinational." if not delay else f"Sample every rising edge, output after {delay} registers; sync high reset clears all."}],
        "configurations": [{"top": name, "parameters": {}}, {"top": name, "parameters": {"BITS": 4}}], "chisel_tops": []}
    task = {"id": "sum_design", "workflow": SCHEMA, "target_languages": ["verilog", "systemverilog"],
            "requirements_text": "Design unsigned addition with full carry. Interface and latency are your choices.",
            "dataset_provenance": {"dataset": "requirements-unit", "manifest_sha256": "0"*64, "split": "pilot"}}
    checks = []
    for i in (0, 1):
        drive = f"c{i}_left_data=3; c{i}_right_data=5;"
        if delay:
            drive = f"c{i}_clk=0; c{i}_reset=1; #1; c{i}_clk=1; #1; c{i}_clk=0; c{i}_reset=0; " + drive
            drive += f"repeat({delay}) begin #1; c{i}_clk=1; #1; c{i}_clk=0; end"
        checks.append(drive + f' #1; if(c{i}_sum_data !== 8) $fatal(1,"RTL_CHECK_FAIL: sum");')
    body = 'initial begin\n' + '\n'.join(checks) + '\n$display("RTL_CHECK_PASS"); $finish; end'
    tb = json.dumps({"body": body, "coverage": ["Both widths check full sum"], "oracle_description": "Independent integer addition"})
    declarations = "input wire [BITS-1:0] left_data, right_data, output wire [BITS:0] sum_data"
    child = "module Arithmetic #(parameter BITS=8)(input wire [BITS-1:0] a,b, output wire [BITS:0] y); assign y={1'b0,a}+{1'b0,b}; endmodule\n"
    logic = "Arithmetic #(.BITS(BITS)) leaf(.a(left_data),.b(right_data),.y(sum_data));"
    if delay:
        declarations += ", input wire clk, reset"
        logic = f'''wire [BITS:0] raw;
Arithmetic #(.BITS(BITS)) leaf(.a(left_data),.b(right_data),.y(raw));
reg [BITS:0] stages [0:{delay-1}];
integer i;
always @(posedge clk) begin
  if(reset) for(i=0;i<{delay};i=i+1) stages[i]<=0;
  else begin
    stages[0]<=raw;
    for(i=1;i<{delay};i=i+1) stages[i]<=stages[i-1];
  end
end
assign sum_data=stages[{delay-1}];'''
    rtl = bundle_text({"top.v": f"module {name} #(parameter BITS=8)({declarations});\n{logic}\nendmodule\n", "child.v": child})
    return task, contract, tb, rtl


class ContractTests(TemporaryTestCase):
    def test_all_catalog_cases_share_one_workflow_without_fixed_tb_inputs(self):
        matrix = load_design_matrix(ROOT/'data/requirements.json', None, ['verilog', 'systemverilog', 'chisel'])
        archive = json.loads((ROOT/'data/project-rtl/tasks.json').read_text())
        self.assertEqual({t['id'] for ts in matrix.values() for t in ts}, {t['id'] for t in archive['tasks']})
        expected = {(t['id'], lang) for t in archive['tasks']
                    for lang in t.get('target_languages', ['verilog', 'systemverilog'])}
        self.assertEqual({(t['id'], lang) for lang, ts in matrix.items() for t in ts}, expected)
        for lang, tasks in matrix.items():
            for task in tasks:
                prompt = json.dumps(design_messages(task, lang))
                self.assertNotIn('candidate_testbench_files', prompt)
                self.assertNotIn('expected_ports', prompt)
                self.assertNotIn('contract_text', task)
                self.assertEqual(task['workflow'], SCHEMA)
        with self.assertRaises(ValueError):
            load_design_matrix(ROOT/'data/project-rtl/tasks.json', None, ['verilog'])

    def test_generic_contract_and_expression_rejection(self):
        _, contract, _, _ = example()
        self.assertEqual(validate_contract(contract, 'verilog'), contract)
        self.assertEqual(width('(BITS+1)*2', {'BITS': 8}), 18)
        for expr in (True, '__import__("os")', '2**1000000', 'BITS//0', '-1', '0', 'UNKNOWN'):
            with self.subTest(expr=expr), self.assertRaises(ValueError): width(expr, {'BITS': 8})
        bad = deepcopy(contract); bad['configurations'][0]['parameters'] = {'BITS': 8}
        with self.assertRaises(ValueError): validate_contract(bad, 'verilog')
        bad = deepcopy(contract); bad['tops'][0]['name'] = 'module'
        with self.assertRaises(ValueError): validate_contract(bad, 'verilog')

    def test_testbench_policy_blocks_host_access_and_candidate_peeking(self):
        _, _, tb, _ = example()
        for extra in ('$system("env");', 'force dut0.x=1;', 'initial $display(dut0.secret);', '`include "/tmp/x"', 'module Stub; endmodule'):
            document = json.loads(tb); document['body'] += extra
            with self.subTest(extra=extra), self.assertRaises(ValueError): validate_testbench(document)


@unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
class DesignFlowTests(TemporaryTestCase):
    def run_example(self, responses, task=None, **settings):
        task = task or example()[0]
        provider = SequenceProvider(responses)
        report = run_task(task, provider, {'max_design_repairs': 0, 'max_verification_repairs': 0,
            'max_repairs': 0, 'max_refactors': 0, **settings}, RULES, self.directory)
        return report, provider

    def test_different_interface_names_and_latencies_are_valid_designs(self):
        for name, delay in [('CombinationalSum', 0), ('PipelineSum', 3)]:
            task, contract, tb, rtl = example(name, delay)
            task['id'] += str(delay)
            report, provider = self.run_example([json.dumps(contract), APPROVE, tb, APPROVE, rtl], task)
            self.assertEqual(report['functional_status'], 'passed')
            self.assertEqual(report['schema_version'], 6)
            self.assertEqual(report['provider_calls'], 5)
            self.assertEqual(report['design']['status'], 'frozen')
            self.assertEqual(report['verification_preparation']['status'], 'frozen')
            self.assertEqual(report['attempts'][0]['verification']['contract_sha256'], report['contract_sha256'])
            self.assertNotIn('RTL_CHECK_PASS', json.dumps(provider.messages[4]))
            self.assertNotIn('module Arithmetic', json.dumps(provider.messages[2]))
            self.assertNotIn('上一个', json.dumps(provider.messages[1]))
            self.assertTrue(Path(report['design']['frozen_contract_path']).is_file())

    def test_multitop_and_bidirectional_ports_use_contract_connections(self):
        task, contract, tb, rtl = example()
        contract['tops'].append({'name': 'PadBridge', 'parameters': {}, 'timing': 'Combinational bidirectional pad sensing.',
            'ports': {'pad': {'direction': 'inout', 'width': 1, 'signed': False, 'description': 'externally driven pad'},
                      'sense': {'direction': 'output', 'width': 1, 'signed': False, 'description': 'pad readback'}}})
        contract['configurations'].append({'top': 'PadBridge', 'parameters': {}})
        document = json.loads(tb)
        document['body'] = 'reg external_drive; assign c2_pad=external_drive;\n' + document['body'].replace(
            '$display("RTL_CHECK_PASS")', 'external_drive=0; #1; if(c2_sense !== 0) $fatal(1,"RTL_CHECK_FAIL: pad0"); '
            'external_drive=1; #1; if(c2_sense !== 1) $fatal(1,"RTL_CHECK_FAIL: pad1"); $display("RTL_CHECK_PASS")')
        from rtlflow.project import parse_bundle
        files = parse_bundle(rtl)
        files['pad.v'] = ('module PadBridge(inout wire pad, output wire sense); PadLeaf child(.pad(pad),.sense(sense)); endmodule\n'
                          'module PadLeaf(inout wire pad, output wire sense); assign sense=pad; endmodule\n')
        report, _ = self.run_example([json.dumps(contract), APPROVE, json.dumps(document), APPROVE, bundle_text(files)])
        self.assertEqual(report['functional_status'], 'passed')
        self.assertEqual(len(report['attempts'][0]['verification']['checks']['interface']['actual']), 3)

    def test_chisel_constructor_is_designed_not_loaded_from_old_task(self):
        task, contract, tb, rtl = example()
        task['target_languages'] = ['chisel']
        contract['tops'][0]['parameters'] = {}
        for port in contract['tops'][0]['ports'].values():
            port['width'] = width(port['width'], {'BITS': 8})
        contract['configurations'] = [{'top': 'ChosenAdder', 'parameters': {}}]
        contract['chisel_tops'] = [{'module': 'ChosenAdder', 'class': 'newdesign.CustomAdder', 'args': [8]}]
        document = json.loads(tb)
        document['body'] = document['body'].replace('c1_left_data=3; c1_right_data=5; #1; if(c1_sum_data !== 8) $fatal(1,"RTL_CHECK_FAIL: sum");', '')
        from rtlflow.project import parse_bundle
        def elaborate(files, frozen_task, directory, timeout):
            self.assertEqual(frozen_task['chisel_tops'], contract['chisel_tops'])
            emitted = {name.replace('.v', '.sv'): code for name, code in parse_bundle(rtl).items()}
            emitted['top.sv'] = (emitted['top.sv'].replace(' #(parameter BITS=8)', '')
                                 .replace('[BITS-1:0]', '[7:0]').replace('[BITS:0]', '[8:0]')
                                 .replace('.BITS(BITS)', '.BITS(8)'))
            return {'files': emitted, 'checks': {'elaboration': {'status': 'passed'}}}
        with patch('rtlflow.chisel.elaborate_chisel', side_effect=elaborate):
            report, _ = self.run_example([json.dumps(contract), APPROVE, json.dumps(document), APPROVE,
                bundle_text({'Top.scala': '// Mocked frontend only; no claim of real Chisel build.\nclass CustomAdder\n'})], task, language='chisel')
        self.assertEqual(report['functional_status'], 'passed')
        self.assertTrue(Path(report['final_rtl']).is_dir())

    def test_missing_verification_tools_stops_before_rtl(self):
        _, contract, tb, _ = example()
        with patch('rtlflow.design_verify.shutil.which', return_value=None):
            report, provider = self.run_example([json.dumps(contract), APPROVE, tb])
        self.assertEqual(len(provider.messages), 3)
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['repair_calls'], 0)

    def test_contract_rejection_never_generates_rtl(self):
        task, contract, _, _ = example()
        reject = json.dumps({'accepted': False, 'issues': ['undefined reset'], 'rationale': 'Ambiguous.'})
        report, provider = self.run_example([json.dumps(contract), reject])
        self.assertEqual(len(provider.messages), 2)
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['stop_reason'], 'design_not_frozen')
        self.assertEqual(report['attempts'], [])
        self.assertIsNone(report['final_source'])

    def test_independent_verifier_quality_failure_is_not_rtl_failure(self):
        _, contract, tb, _ = example()
        document = json.loads(tb)
        document['body'] = 'initial begin $display("RTL_CHECK_PASS"); $finish; end // RTL_CHECK_FAIL $fatal'
        report, _ = self.run_example([json.dumps(contract), APPROVE, json.dumps(document)])
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['stop_reason'], 'verification_not_frozen')
        self.assertEqual(report['provider_calls'], 3)

    def test_verifier_review_rejects_before_implementation(self):
        _, contract, tb, _ = example()
        reject = json.dumps({'accepted': False, 'issues': ['insufficient boundaries'], 'rationale': 'Only one value.'})
        report, _ = self.run_example([json.dumps(contract), APPROVE, tb, reject])
        self.assertEqual(report['stop_reason'], 'verification_not_frozen')
        self.assertEqual(report['last_error_code'], 'verification_review_rejected')

    def test_parameter_defaults_and_port_signedness_are_enforced(self):
        for suffix, fault, reason in (
            ('default', lambda s: s.replace('parameter BITS=8', 'parameter BITS=7'), 'frozen_parameter_defaults_mismatch'),
            ('signed', lambda s: s.replace('output wire [BITS:0] sum_data', 'output wire signed [BITS:0] sum_data'), 'public_ports_exact'),
        ):
            task, contract, tb, rtl = example()
            task['id'] += suffix
            report, _ = self.run_example([json.dumps(contract), APPROVE, tb, APPROVE, fault(rtl)], task)
            self.assertEqual(report['functional_status'], 'failed')
            self.assertEqual(report['attempts'][0]['verification']['checks']['interface']['reason'], reason)

    def test_rtl_repairs_keep_frozen_contract_and_tests(self):
        _, contract, tb, rtl = example()
        bad = rtl.replace("{1'b0,a}+{1'b0,b}", "{1'b0,a}-{1'b0,b}")
        report, provider = self.run_example([json.dumps(contract), APPROVE, tb, APPROVE, bad, rtl], max_repairs=1)
        self.assertTrue(report['repair_success'])
        self.assertEqual(report['provider_calls'], 6)
        hashes = {a['verification']['verification_sha256'] for a in report['attempts']}
        self.assertEqual(hashes, {report['verification_sha256']})
        self.assertNotIn('RTL_CHECK_FAIL: sum', json.dumps(provider.messages[-1]))

    def test_design_retry_budget_and_transport_failure(self):
        _, contract, tb, rtl = example()
        report, _ = self.run_example(['not JSON', json.dumps(contract), APPROVE, tb, APPROVE, rtl], max_design_repairs=1)
        self.assertEqual(report['functional_status'], 'passed')
        self.assertEqual(report['design_calls'], 3)
        self.assertEqual(report['generation_error_counts'], {'invalid_design_contract': 1})

    def test_frozen_artifact_tampering_blocks_not_fails_rtl(self):
        _, contract, tb, rtl = example()
        from rtlflow.design_verify import bind_verification as real_bind
        def tamper(task, directory):
            Path(task['frozen_contract_path']).write_text('{}')
            return real_bind(task, directory)
        with patch('rtlflow.design_verify.bind_verification', side_effect=tamper):
            report, _ = self.run_example([json.dumps(contract), APPROVE, tb, APPROVE, rtl], max_repairs=2)
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['repair_calls'], 0)

    def test_group_comparison_reports_all_stages_and_failures(self):
        task, contract, tb, rtl = example()
        summary = run_group_comparison([task], lambda _: SequenceProvider([json.dumps(contract), APPROVE, tb, APPROVE, rtl]),
            {'max_refactors': 0}, RULES, ['Baseline', 'Skill'], self.directory/'groups')
        self.assertEqual(summary['passed'], 2)
        self.assertEqual(summary['provider_calls'], 10)
        self.assertEqual(summary['by_task'][task['id']]['Skill']['functional_status'], 'passed')


class BlockedFlowTests(TemporaryTestCase):
    def test_old_input_rejected_before_provider_and_output(self):
        from helpers import TASKS
        provider = SequenceProvider(['unused'])
        with self.assertRaises(ValueError): run_task(TASKS['and2'], provider, {}, RULES, self.directory)
        self.assertEqual(provider.messages, [])
        self.assertFalse((self.directory/'and2').exists())

    def test_api_failure_is_not_functional_failure(self):
        provider = SequenceProvider([GenerationError('offline')])
        report = run_task(example()[0], provider, {}, RULES, self.directory)
        self.assertEqual(report['functional_status'], 'not_run')
        self.assertEqual(report['provider_calls'], 1)
        self.assertEqual(report['last_error'], 'offline')
