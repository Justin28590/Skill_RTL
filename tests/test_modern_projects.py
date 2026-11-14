"""Independent FP oracle and modern IP testbench semantic fault regressions."""
import unittest

from helpers import HAS_ICARUS, ROOT, TemporaryTestCase
from rtlflow.project import expanded_policy, load_projects, verify_project, write_bundle
from scripts.build_fma_vectors import build, fma
from scripts.verify_project_replay import reference_bundle

class ModernProjectTests(TemporaryTestCase):
    def task(self, key):
        return load_projects(ROOT / 'data/project-rtl/tasks.json', [key], 'verilog')[0]

    def verify(self, task, files, label):
        directory = self.directory / label
        write_bundle(files, directory / 'source')
        return verify_project(files, directory / 'source', task, directory / 'checks',
                              {'language': 'verilog', 'tool_timeout_seconds': 30})

    def test_exact_fma_oracle_known_ieee_answers(self):
        for a,b,c,op,mode,result,flags in (
            (0x3f800001,0x3f7ffffe,0xbf800000,0,0,0xa8800000,0),  # fused, not double rounded
            (0x3f800000,0x3f800000,0x33800000,0,0,0x3f800000,1),
            (0x3f800000,0x3f800000,0x33800000,0,4,0x3f800001,1),
            (0x3f800000,0x3f800000,0x33800000,0,6,0x3f800001,1),
            (0x3f800000,0x3f800000,0xbf800000,0,2,0x80000000,0),
            (1,0x3f000000,0,0,0,0,3),
            (1,0x3f000000,0,0,3,1,3),
            (0x00800000,0x3f7fffff,0,0,0,0x00800000,3),  # tininess uses unbounded exponent rounding
            (0x7f7fffff,0x40000000,0,0,0,0x7f800000,5),
            (0x7f7fffff,0x40000000,0,0,1,0x7f7fffff,5),
            (0x7f800000,0,0,0,0,0x7fc00000,16),
            (0x7fc00001,0x3f800000,0,0,0,0x7fc00000,0),
            (0x7f800001,0x3f800000,0,0,0,0x7fc00000,16),
        ):
            with self.subTest(a=a,b=b,c=c,op=op,mode=mode):
                self.assertEqual(fma(a,b,c,op,mode), (result,flags))

    def test_fma_vectors_rebuild_byte_identically(self):
        self.assertEqual(build(), (ROOT / 'data/project-rtl/tests/blackbox/modern/fp32_fma_tb.sv').read_text())

    def test_reference_copy_normalization_does_not_relax_candidate_policy(self):
        files = reference_bundle(self.task('fp32_fma'))
        self.assertFalse(any(name.endswith('.vi') for name in files))
        self.assertIn('HardFloat_localFuncs.vh', files)
        self.assertIn('parameter expWidth = 8, parameter sigWidth = 24', files['mulAddRecFN.v'])
        self.assertNotIn('Bit[ix - 1].countSoFar', files['HardFloat_primitives.v'])
        self.assertEqual(expanded_policy('module top; wire x = tb.expected; endmodule')['status'], 'failed')

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_semantic_faults_rejected_after_successful_compile(self):
        mutations = (
            ('fp32_fma', 'mulAddRecFN.v', '            roundingMode,\n            out,\n            exceptionFlags',
             "            3'b001,\n            out,\n            exceptionFlags", 'ERROR FMA'),
            ('axi_dma_engine', 'axi_dma_wr.v', 'assign m_axi_wstrb  = m_axi_wstrb_reg;',
             "assign m_axi_wstrb  = {AXI_STRB_WIDTH{1'b1}};", 'ERROR DMA write byte/strobe'),
            ('axi_scratchpad', 'axi_dp_ram.v', 'if (ram_a_cmd_wr_strb[i]) begin',
             "if (1'b1) begin", 'ERROR scratchpad read'),
            ('axis_async_bridge', 'axis_async_fifo.v', 's_axis_tlast && DROP_BAD_FRAME && USER_BAD_FRAME_MASK',
             "s_axis_tlast && 1'b0 && USER_BAD_FRAME_MASK", 'ERROR async'),
        )
        for key,filename,old,new,message in mutations:
            with self.subTest(key=key):
                task = self.task(key)
                files = reference_bundle(task)
                self.assertEqual(files[filename].count(old), 1)
                files[filename] = files[filename].replace(old, new)
                result = self.verify(task, files, key)
                self.assertEqual(result['checks']['compile']['status'], 'passed', result['checks'])
                self.assertEqual(result['functional_status'], 'failed')
                self.assertIn(message, result['checks']['simulation']['stdout'])

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_missing_fma_header_is_not_filled_from_reference(self):
        task = self.task('fp32_fma')
        files = reference_bundle(task)
        del files['HardFloat_localFuncs.vh']
        result = self.verify(task, files, 'missing-header')
        self.assertEqual(result['functional_status'], 'failed')
        self.assertEqual(result['checks']['simulation']['status'], 'not_run')
