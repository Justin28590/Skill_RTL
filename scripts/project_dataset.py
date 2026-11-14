#!/usr/bin/env python3
"""Check/download the pinned project corpus or validate original references only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rtlflow.project_dataset import (download_sources, load_manifest, save_json,
                                     sha256, verify_reference)
from rtlflow.verify import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/project-rtl/tasks.json")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check-data", action="store_true")
    actions.add_argument("--stats", action="store_true", help="JSON native-source language counts and project IDs; no tools or model")
    actions.add_argument("--download", action="store_true", help="explicit network fetch of missing fixed archives")
    actions.add_argument("--verify-reference", action="store_true", help="run reviewed upstream HDL/TBs, NOT a sandbox")
    parser.add_argument("--task", action="append", help="select an ID; default all projects")
    parser.add_argument("--output", type=Path, help="new evidence directory; must not already exist")
    parser.add_argument("--jobs", type=int, default=4, choices=range(1, 5))
    args = parser.parse_args()
    root, document, lock = load_manifest(args.manifest, check_sources=not args.download)
    if args.download:
        download_sources(root, lock)
        root, document, lock = load_manifest(args.manifest)
    counts = {language: sum(t.get('language', 'verilog') == language for t in document['tasks'])
              for language in ('verilog', 'systemverilog', 'chisel')}
    if args.stats:
        import json
        print(json.dumps({'total': document['case_count'], 'native_source_languages': counts,
                          'projects': {lang: [t['id'] for t in document['tasks'] if t.get('language', 'verilog') == lang] for lang in counts}},
                         ensure_ascii=False, indent=2))
        return 0
    if not args.verify_reference:
        print('Native source languages:', counts)
        print(f"PASS: {document['case_count']} project cases, {len(lock)} pinned repositories; file hashes verified")
        return 0
    chosen = set(args.task or [t["id"] for t in document["tasks"]])
    if chosen - {t["id"] for t in document["tasks"]}:
        parser.error("unknown --task ID")
    tasks = [t for t in document["tasks"] if t["id"] in chosen]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = (args.output or ROOT / "artifacts/project-rtl/reference" / timestamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    versions = {}
    for tool in ("iverilog", "vvp"):
        executable = shutil.which(tool)
        versions[tool] = run_command([executable, "-V"], output, tool + "-version", 5) if executable else {"status": "not_run"}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        reports = list(pool.map(lambda task: verify_reference(root, task, output), tasks))
    summary = {"schema_version": 1, "dataset": document["dataset"], "timestamp_utc": timestamp,
               "manifest_sha256": sha256(args.manifest), "model_calls": 0,
               "validator_sha256": {name: sha256(ROOT / name) for name in (
                   "scripts/project_dataset.py", "src/rtlflow/project_dataset.py", "src/rtlflow/project.py", "src/rtlflow/chisel.py", "scripts/chisel_sbt.sh", "src/rtlflow/verify.py")},
               "evidence_path_note": "Command and log paths record the original execution host; report/log hashes permit independent checking after relocation.",
               "reference_rtl_modified": False, "scope": "reference_only_pilot",
               "compatibility_note": "Pinned originals unchanged; pConst build copies use explicit parameter keywords and SPI reset-port spelling fix; Chisel uses documented emitter/guard compatibility edits; systolic uses explicit port/unsigned parameter syntax and continuous boundary interconnects for Icarus, without algorithm/sequential changes.",
               "native_source_languages": counts,
               "task_count": len(tasks), "tool_versions": versions,
               "reference_passed": sum(r["reference_status"] == "passed" for r in reports),
               "negative_controls_passed": sum(r["negative_control_status"] == "passed" for r in reports),
               "tasks": [{"id": r["task_id"], "reference_status": r["reference_status"],
                          "negative_control_status": r["negative_control_status"],
                          "report": f"{r['task_id']}/report.json",
                          "report_sha256": sha256(output / r["task_id"] / "report.json")}
                         for r in reports]}
    save_json(output / "summary.json", summary)
    for report in reports:
        hierarchy = report.get("hierarchy", {})
        print(f"{report['task_id']}: reference={report['reference_status']} "
              f"negative={report['negative_control_status']} modules={hierarchy.get('module_type_count', '?')}")
    print(f"Evidence: {output / 'summary.json'}")
    return 0 if summary["reference_passed"] == summary["negative_controls_passed"] == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
