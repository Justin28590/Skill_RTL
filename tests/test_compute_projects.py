"""Compute/packet testbenches must reject semantic faults, not just compile RTL."""
import unittest

from helpers import HAS_ICARUS, ROOT, TemporaryTestCase
from rtlflow.project import load_projects, verify_project, write_bundle
from scripts.verify_project_replay import reference_bundle


class ComputeProjectTests(TemporaryTestCase):
    def task(self, key):
        return load_projects(ROOT / 'data/project-rtl/tasks.json', [key], 'systemverilog')[0]

    def verify(self, task, files, name):
        source = self.directory / name / 'source'
        write_bundle(files, source)
        return verify_project(files, source, task, self.directory / name / 'checks',
                              {'language': 'systemverilog', 'tool_timeout_seconds': 30})

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_systolic_wrong_signedness_or_transpose_is_rejected(self):
        task = self.task('systolic_matmul')
        for label, filename, old, new in (
            ('signed', 'pe.sv', 'mult = i_a*i_b;', 'mult = $signed(i_a)*$signed(i_b);'),
            ('transpose', 'topSystolicArray.sv', 'i_b[N-j-1][i]', 'i_b[i][N-j-1]'),
        ):
            with self.subTest(label=label):
                files = reference_bundle(task)
                self.assertEqual(files[filename].count(old), 1)
                files[filename] = files[filename].replace(old, new)
                result = self.verify(task, files, label)
                self.assertEqual(result['checks']['compile']['status'], 'passed')
                self.assertEqual(result['functional_status'], 'failed')
                self.assertIn('ERROR matrix product', result['checks']['simulation']['stdout'])

    @unittest.skipUnless(HAS_ICARUS, 'requires Icarus/vvp')
    def test_switch_scoreboard_rejects_lost_keep_and_id_sidebands(self):
        task = self.task('axis_packet_switch')
        for label, old, new in (
            ('keep', 'int_s_axis_tkeep[grant_encoded*KEEP_WIDTH +: KEEP_WIDTH]', "{KEEP_WIDTH{1'b1}}"),
            ('id', 'm_axis_tid_mux[M_ID_WIDTH-1:M_ID_WIDTH-CL_S_COUNT] = grant_encoded;',
             'm_axis_tid_mux[M_ID_WIDTH-1:M_ID_WIDTH-CL_S_COUNT] = 0;'),
        ):
            with self.subTest(label=label):
                files = reference_bundle(task)
                self.assertEqual(files['axis_switch.v'].count(old), 1)
                files['axis_switch.v'] = files['axis_switch.v'].replace(old, new)
                result = self.verify(task, files, label)
                self.assertEqual(result['checks']['compile']['status'], 'passed')
                self.assertEqual(result['functional_status'], 'failed')
                self.assertIn('ERROR packet scoreboard', result['checks']['simulation']['stdout'])
