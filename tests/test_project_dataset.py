"""Project dataset guards, verdicts and real reference smoke tests; no model calls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from helpers import HAS_ICARUS, ROOT
from rtlflow.project import load_projects
from rtlflow.project_dataset import (elaborated_hierarchy, load_manifest, local_path,
                                     output_verdict, save_json, sha256, verify_reference)

DATA = ROOT / "data/project-rtl"


class ProjectDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / "sources/example/design"
        source.mkdir(parents=True)
        (source / "top.v").write_text("module child(input a, output b); assign b=a; endmodule\n"
                                     "module top(output q); child c(1'b1,q); endmodule\n")
        (source / "tb.v").write_text("module tb; wire q; top dut(q); initial begin #1; "
                                    "if(q!==1'b1) $fatal(1, \"BROKEN\"); "
                                    "$display(\"GOOD\"); $finish; end endmodule\n")
        (self.root / "public.md").write_text("Complete top and child. Output is one.")
        save_json(self.root / "sources.lock.json", {"sources": {"example/design": {
            "repository": "https://github.com/example/design", "revision": "a" * 40,
            "archive_sha256": "b" * 64,
            "files": {p.name: sha256(p) for p in source.iterdir()}}}})
        self.task = {"id": "fixture", "repository": "example/design", "dialect": "2012",
                     "design_tops": ["top"], "testbench_tops": ["tb"], "dut_roots": ["tb.dut"],
                     "rtl_files": ["sources/example/design/top.v"],
                     "testbench_files": ["sources/example/design/tb.v"], "include_dirs": [], "defines": [],
                     "negative_forces": [{"target": "tb.dut.q", "value": "1'b0"}],
                     "required_output": [{"regex": "GOOD", "min_count": 1}], "forbidden_output": ["BROKEN"],
                     "simulation_timeout_seconds": 5, "negative_timeout_seconds": 2,
                     "specification": "public.md", "specification_sha256": sha256(self.root / "public.md"),
                     "coverage": "One fixture assertion", "limitations": []}
        self.document = {"schema_version": "project-rtl-v2", "split": "pilot", "case_count": 1,
                         "sources_lock": "sources.lock.json", "sources_lock_sha256": sha256(self.root / "sources.lock.json"),
                         "support_sha256": {}, "tasks": [self.task]}
        self.path = self.root / "tasks.json"
        save_json(self.path, self.document)

    def test_actual_32_projects_and_native_language_counts_are_locked(self):
        root, manifest, sources = load_manifest(DATA / "tasks.json")
        self.assertEqual(root, DATA)
        self.assertEqual(len(manifest["tasks"]), 32)
        self.assertEqual(len(sources), 27)
        self.assertTrue(manifest["generation_ready"])
        self.assertEqual({lang: sum(t['language'] == lang for t in manifest['tasks'])
                          for lang in ('verilog', 'systemverilog', 'chisel')},
                         {'verilog': 27, 'systemverilog': 3, 'chisel': 2})
        self.assertTrue(all(t["scope"] == "complete_portable_ip_design" for t in manifest["tasks"]))
        cmac = next(t for t in manifest["tasks"] if t["id"] == "cmac")
        self.assertTrue(any("secworks/aes/" in p for p in cmac["rtl_files"]))

    @unittest.skipUnless(os.environ.get("RTL_VALIDATE_EVIDENCE") == "1",
                         "local evidence check: set RTL_VALIDATE_EVIDENCE=1 (see docs/验收.md)")
    def test_published_reference_evidence_is_complete_and_unchanged(self):
        evidence = ROOT / "artifacts/project-rtl/reference"
        summary = json.loads((evidence / "summary.json").read_text())
        self.assertEqual(summary["manifest_sha256"], sha256(DATA / "tasks.json"))
        self.assertEqual(summary["reference_passed"], 32)
        self.assertEqual(summary["negative_controls_passed"], 32)
        self.assertEqual(summary["model_calls"], 0)
        for name, expected in summary["validator_sha256"].items():
            self.assertEqual(sha256(ROOT / name), expected)
        for item in summary["tasks"]:
            report_path = evidence / item["report"]
            self.assertEqual(sha256(report_path), item["report_sha256"])
            report = json.loads(report_path.read_text())
            self.assertGreaterEqual(report["hierarchy"]["module_type_count"], 2)
            for phase in ("reference", "negative"):
                for check in ("compile", "simulation"):
                    record = report[phase][check]
                    for stream in ("stdout", "stderr"):
                        log = report_path.parent / phase / Path(record[stream + "_log"]).name
                        self.assertEqual(sha256(log), record[stream + "_sha256"])

    def test_tampered_reference_or_spec_rejected(self):
        target = self.root / self.task["rtl_files"][0]
        target.write_text(target.read_text() + "// changed\n")
        with self.assertRaisesRegex(ValueError, "upstream checksum"):
            load_manifest(self.path)
        with self.assertRaisesRegex(ValueError, "public specification"):
            (self.root / "public.md").write_text("changed")
            load_manifest(self.path, check_sources=False)

    def test_unlisted_source_rejected(self):
        (self.root / "sources/example/design/unlisted.v").write_text("module stub; endmodule")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            load_manifest(self.path)

    def test_unsafe_paths_and_symlinks_rejected(self):
        for path in ("../escape", "/tmp/escape", "sources/../../escape", "a\\b"):
            with self.assertRaises(ValueError):
                local_path(self.root, path, exists=False)
        (self.root / "link").symlink_to(self.root / "public.md")
        with self.assertRaisesRegex(ValueError, "symlink"):
            local_path(self.root, "link")

    def test_unknown_input_duplicate_id_and_vacuous_verdict_rejected(self):
        for mutate in (
            lambda m: m["tasks"][0]["rtl_files"].append("unlocked.v"),
            lambda m: m["tasks"][0]["required_output"][0].update(min_count=0),
            lambda m: m["tasks"][0]["negative_forces"][0].update(target="tb.expected"),
            lambda m: m.update(tasks=m["tasks"] * 2, case_count=2),
        ):
            document = copy.deepcopy(self.document)
            mutate(document)
            save_json(self.path, document)
            with self.assertRaises(ValueError):
                load_manifest(self.path)

    def generation_fixture(self):
        """One catalog and one spec, with a separately locked candidate test adapter."""
        candidate = self.root / "candidate_tb.v"
        candidate.write_text((self.root / self.task["testbench_files"][0]).read_text())
        self.task["generation"] = {
            "files_sha256": {candidate.name: sha256(candidate)},
            "candidate_testbench_files": [candidate.name],
            "expected_ports": {"tb.dut": {"module": "top", "ports": {
                "q": {"direction": "output", "width": 1}}}},
            "public_parameters": {"top": []}, "testbench_adaptations": {},
            "additional_dut_roots": [], "additional_required_output": [],
        }
        self.document.update(dataset="unit-only", generation_ready=True, languages=["verilog"])
        save_json(self.path, self.document)

    def test_single_catalog_serves_reference_and_generation_with_one_spec(self):
        self.generation_fixture()
        _, catalog, _ = load_manifest(self.path)
        task = load_projects(self.path)[0]
        self.assertEqual(task["id"], catalog["tasks"][0]["id"])
        self.assertEqual(task["contract"], self.task["specification"])
        self.assertEqual(task["contract_text"], (self.root / "public.md").read_text())
        self.assertNotIn("generation", task)  # only flatten the selected task's metadata
        self.assertEqual(task["dataset_provenance"]["manifest_sha256"], sha256(self.path))
        (self.root / "public.md").write_text("tampered single specification")
        with self.assertRaisesRegex(ValueError, "public specification"):
            load_projects(self.path)

    def test_candidate_adapter_hash_and_metadata_remain_required(self):
        self.generation_fixture()
        candidate = self.root / "candidate_tb.v"
        candidate.write_text(candidate.read_text() + "// changed\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            load_projects(self.path)
        self.task["generation"]["files_sha256"] = {}
        save_json(self.path, self.document)
        with self.assertRaisesRegex(ValueError, "unlocked project generation inputs"):
            load_projects(self.path)
        del self.task["generation"]
        save_json(self.path, self.document)
        with self.assertRaisesRegex(ValueError, "generation fields"):
            load_projects(self.path)

    def test_duplicate_catalog_keys_and_unprepared_generation_rejected(self):
        self.path.write_text('{"schema_version":"project-rtl-v2","schema_version":"project-rtl-v2"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            load_manifest(self.path)
        self.generation_fixture()
        self.document["generation_ready"] = False
        save_json(self.path, self.document)
        with self.assertRaisesRegex(ValueError, "未就绪"):
            load_projects(self.path)

    @unittest.skipUnless(HAS_ICARUS, "iverilog required")
    def test_metadata_preparation_does_not_rewrite_specification(self):
        from scripts.prepare_project_generation import prepare_addition
        self.task["language"] = "verilog"
        expected = (self.root / "public.md").read_bytes()
        result = prepare_addition(self.root, self.task, self.root)
        self.assertEqual((self.root / "public.md").read_bytes(), expected)
        self.assertNotIn("contract", result)
        self.assertEqual(result["candidate_testbench_files"], self.task["testbench_files"])
        self.assertEqual(result["expected_ports"]["tb.dut"]["module"], "top")

    def test_failure_wins_even_after_success_and_marker_counts_required(self):
        self.assertTrue(output_verdict(self.task, "GOOD")["passed"])
        self.assertFalse(output_verdict(self.task, "")["passed"])
        self.assertFalse(output_verdict(self.task, "BROKEN\nGOOD")["passed"])
        task = copy.deepcopy(self.task)
        task["required_output"][0]["min_count"] = 2
        self.assertFalse(output_verdict(task, "GOOD")["passed"])

    def test_missing_tools_not_run(self):
        with patch("rtlflow.project_dataset.shutil.which", return_value=None):
            result = verify_reference(self.root, self.task, self.root / "out")
        self.assertEqual(result["reference_status"], "not_run")
        self.assertEqual(result["negative_control_status"], "not_run")

    @unittest.skipUnless(HAS_ICARUS, "iverilog/vvp required")
    def test_hierarchy_and_negative_control_actually_execute(self):
        load_manifest(self.path)
        result = verify_reference(self.root, self.task, self.root / "out")
        self.assertEqual(result["reference_status"], "passed")
        self.assertEqual(result["negative_control_status"], "passed")
        self.assertEqual(result["hierarchy"]["module_types"], ["child", "top"])
        self.assertEqual(result["hierarchy"]["instance_count"], 2)
        self.assertFalse(result["negative"]["accepted_as_correct"])

    @unittest.skipUnless(HAS_ICARUS, "iverilog/vvp required")
    def test_noncompiling_fault_is_not_evidence_of_rejection(self):
        self.task["negative_forces"][0]["target"] = "tb.dut.nonexistent"
        result = verify_reference(self.root, self.task, self.root / "out")
        self.assertEqual(result["reference_status"], "passed")
        self.assertEqual(result["negative_control_status"], "failed")

    @unittest.skipUnless(HAS_ICARUS, "iverilog/vvp required")
    def test_real_uart_whole_project_smoke(self):
        root, manifest, _ = load_manifest(DATA / "tasks.json")
        task = next(t for t in manifest["tasks"] if t["id"] == "wbuart32")
        result = verify_reference(root, task, self.root / "uart")
        self.assertEqual(result["reference_status"], "passed")
        self.assertEqual(result["negative_control_status"], "passed")
        self.assertEqual(result["hierarchy"]["module_type_count"], 4)


if __name__ == "__main__":
    unittest.main()
