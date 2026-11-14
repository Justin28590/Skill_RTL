"""Project generation, bounded repair, whole-project rollback and artifact reporting."""
import csv
import hashlib
import json
from pathlib import Path
import time

from . import __version__
from .languages import LABELS, language_of, select_rules
from .project import bundle_text, parse_bundle, verify_project, write_bundle
from .project_dataset import save_json
from .providers import GenerationError
from .score import score_readability
from .skill_tools import SkillReader, skill_capabilities
from .verify import tool_versions


GROUPS = ("Baseline", "Skill")
DEFAULT_GROUP = "Baseline"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def initial_messages(task, group, rules, language="verilog"):
    if group not in GROUPS:
        raise ValueError("group 必须为 Baseline/Skill；旧 A/B/C/D 策略不再支持")
    if language not in {"verilog", "systemverilog", "chisel"}:
        raise ValueError("未知项目语言")
    if language == "chisel":
        from .chisel import validate_chisel_config
        validate_chisel_config(task.get("chisel_tops"), task["design_tops"])
    system = (
        f"你是 {LABELS[language]} 项目级 RTL 工程师。根据公开设计契约实现整个硬件项目。"
        "必须包含所有公开顶层及完整子模块依赖；每个顶层都应有实际展开的子模块，不得用桩或常量替代功能。"
        "保留外部端口和参数，允许改变内部模块名和架构。最终只返回一个完整 JSON 对象："
        '{"files":[{"path":"rtl/top.v","content":"完整文件内容"},{"path":"rtl/child.v","content":"完整文件内容"}]}。'
        "每轮生成、修复、重构均返回所有文件，不是补丁，未列出的旧文件不会沿用。"
        "文件路径必须为项目内相对路径，不能包含..、绝对路径、反斜杠或隐藏目录；最多128个文件，总源码不超过2MB。"
        "不返回Testbench、构建脚本、依赖配置或解释。"
        "只允许HDL源文件和头文件；include必须是双引号字面量、单独一行，路径相对于项目根目录且该文件必须随响应提供。"
        "可用常规宏/条件编译，但禁止宏拼接、转义标识符、外部include、层次引用、defparam、force/release/bind、VPI/DPI或宿主I/O。"
        "禁止仿真系统任务（包括display/finish/readmem）；只允许$clog2/$signed/$unsigned/$bits。"
        "所有时钟由外部输入提供，不得依赖测试环境内部信号或参考实现。编译器为Icarus。"
    )
    if language == "chisel":
        system = (
            "你是 Chisel 项目级工程师。根据公开契约交付完整多文件硬件项目，所有顶层必须实例化实际子模块。"
            '最终只返回完整 JSON：{"files":[{"path":"rtl/Top.scala","content":"完整源码"}]}。'
            "每次修复或重构必须返回所有文件，不沿用旧快照。只允许.scala，不允许构建文件、依赖配置、TB或RTL黑盒。"
            "路径必须为项目内相对路径，不含..、绝对路径、反斜杠或隐藏目录；最多128文件、总源码2MB。"
            "固定工具链Scala 2.13.12 / Chisel 6.5.0 / firtool 1.62.0，由可信入口进行展开。"
            "禁止自建App/main、emit调用、宿主I/O、反射、进程、线程、网络、printf/assert和外部RTL。"
            "禁止定义RTLFlowMain。仅可导入chisel3、scala.collection、scala.math。"
            "保留指定类名、包名和构造参数，以及生成RTL的顶层名/端口/复位语义；每个顶层保留子模块层次。"
            "Chisel构造参数在展开时固定，不承诺生成可覆写的Verilog参数。"
            "公开构造配置：" + json.dumps(task["chisel_tops"], ensure_ascii=False)
        )
    elif language == "systemverilog":
        system += "目标为Icarus -g2012支持的可综合SystemVerilog；源文件用.sv，头文件用.svh（也允许兼容.v/.vh）。"
    else:
        system += "源文件用.v，头文件用.vh；使用项目指定的Verilog方言，默认2005，wbuart32/PicoRV32兼容2012。"
    if group == "Skill":
        system += skill_capabilities(language)
    user = (("请调用 rtl-readable Skill，" if group == "Skill" else "")
            + f"实现以下完整的 {LABELS[language]} 项目。\n项目：{task['id']}\n"
            + task["contract_text"])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def repair_feedback(attempt):
    parts = ["上一个项目未通过。请修复并返回包含所有源文件的完整 JSON files 对象；保持公开顶层接口和参数。"]
    if attempt.get("format_error"):
        parts.append(attempt["format_error"])
        return '\n'.join(parts)
    checks = attempt["verification"]["checks"]
    for name in ("scala_policy", "source_policy"):
        policy = checks.get(name, {})
        if policy.get("status") == "failed":
            parts.append("源码策略：" + json.dumps(policy, ensure_ascii=False))
    # Only candidate-only preprocessing/elaboration diagnostics are public-safe.
    for name in ("elaboration", "preprocess", "candidate_compile"):
        check = checks.get(name, {})
        if check.get("status") == "failed":
            text = check.get("stderr", "") + ("\n" + check.get("stdout", "") if name == "elaboration" else "")
            for prefix in (attempt.get("source_directory", ""), str(Path(attempt["prompt_path"]).parent / 'checks')):
                if prefix:
                    text = text.replace(prefix, "candidate")
            parts.append(f"{name}失败：{check['reason']}\n" + text[:6000])
    for name, hint in (("compile", "测试环境接口连接失败，核对公开端口、方向、位宽和参数"),
                       ("interface", "实际顶层端口或可覆写参数不匹配公开契约"),
                       ("hierarchy", "每个顶层必须包含完整、实际实例化的子模块"),
                       ("simulation", "独立功能测试失败，请核对公开算法、时序、边界与复位")):
        if checks.get(name, {}).get("status") == "failed":
            parts.append(hint + "（" + checks[name].get("reason", name) + "）。")
    return '\n'.join(parts)


def run_task(task, provider, settings, rules, output):
    language = language_of(settings)
    # Reject unsupported frontends before directory creation or a paid provider call.
    group = settings.get("group", DEFAULT_GROUP)
    base_messages = initial_messages(task, group, rules, language)
    started = time.monotonic()
    task_dir = Path(output).resolve() / task["id"]
    task_dir.mkdir(parents=True, exist_ok=False)
    # Both arms share the same feedback, budgets, verification and rollback path.
    max_repairs = settings.get("max_repairs", 2)
    max_refactors = settings.get("max_refactors", 1)
    threshold = settings.get("readability_threshold", 90)
    attempts = []

    def generate_and_check(phase, previous=None, feedback=None):
        attempt_dir = task_dir / f"attempt_{len(attempts):02d}_{phase}"
        attempt_dir.mkdir()
        messages = list(base_messages)
        if previous is not None:
            previous_text = Path(previous.get("bundle_path", previous["response_path"])).read_text()
            messages += [{"role": "assistant", "content": previous_text}, {"role": "user", "content": feedback}]
        save_json(attempt_dir / "prompt.json", messages)
        attempt = {"index": len(attempts), "phase": phase, "language": language,
                   "prompt_path": str(attempt_dir / "prompt.json"), "selected_final": False,
                   "repairable": False, "generation_status": "failed"}
        attempts.append(attempt)
        call_start = time.monotonic()
        try:
            response = provider.generate(task["id"], messages, skill=SkillReader(language) if group == "Skill" else None,
                                         trace_dir=attempt_dir)
            attempt.update(usage=response.usage, generation_metadata=response.metadata)
        except GenerationError as exc:
            attempt["error"] = str(exc)
            attempt["generation_metadata"] = exc.metadata
            attempt["usage"] = exc.metadata.get("usage", {})
            return attempt
        finally:
            attempt["generation_seconds"] = round(time.monotonic() - call_start, 4)
            attempt["agent_trace_path"] = attempt.get("generation_metadata", {}).get("agent_trace_path")
        response_path = attempt_dir / "response.txt"
        response_path.write_text(response.text, errors="backslashreplace")
        attempt["response_path"] = str(response_path)
        attempt["repairable"] = True
        try:
            files = parse_bundle(response.text, language)
        except GenerationError as exc:
            attempt["format_error"] = str(exc)
            attempt["verification"] = {"functional_status": "failed", "checks": {
                "bundle": {"status": "failed", "reason": "invalid_project_bundle"}}}
            return attempt
        bundle = bundle_text(files)
        bundle_path = attempt_dir / "project.json"
        bundle_path.write_text(bundle)
        source = attempt_dir / "source"
        hashes = write_bundle(files, source)
        attempt.update(generation_status="passed", bundle_path=str(bundle_path), source_directory=str(source),
                       source_path=str(bundle_path), source_sha256=digest(bundle), files_sha256=hashes,
                       rtl_path=str(source), rtl_sha256=digest(bundle))
        attempt["verification"] = verify_project(files, source, task, attempt_dir / "checks", settings)
        if language == "chisel":
            emitted = attempt["verification"].get("emitted_directory")
            attempt["rtl_path"] = emitted
            attempt["rtl_sha256"] = (digest(bundle_text({p.name: p.read_text() for p in sorted(Path(emitted).glob('*.sv'))}))
                                     if emitted else None)
        # Score candidate source in deterministic path order, never JSON or emitted RTL.
        attempt["readability"] = score_readability('\n'.join(files.values()), language)
        attempt["readability"]["project_file_order"] = list(files)
        return attempt

    def status(attempt):
        return attempt.get("verification", {}).get("functional_status", "not_run")

    current = generate_and_check("initial")
    stop_reason = "generation_error"
    for _ in range(max_repairs):
        if status(current) != "failed" or not current["repairable"]:
            break
        candidate = generate_and_check("repair", current, repair_feedback(current))
        if not candidate["repairable"]:  # transport/tool error: preserve previous complete project
            break
        current = candidate
    if not attempts[-1]["repairable"]:
        stop_reason = "generation_error"
    else:
        stop_reason = {"passed": "functional_pass", "failed": "repair_limit", "not_run": "verification_unavailable"}[status(current)]
    if status(current) == "passed" and stop_reason != "generation_error":
        for _ in range(max_refactors):
            if current["readability"]["score"] is None:
                stop_reason = "readability_unavailable_refactor_skipped"
                break
            if current["readability"]["score"] >= threshold:
                break
            feedback = ("功能通过。仅改善可读性，保持所有顶层接口和逐周期行为；返回完整项目 JSON files。\n"
                        + json.dumps(current["readability"], ensure_ascii=False))
            candidate = generate_and_check("refactor", current, feedback)
            accepted = (status(candidate) == "passed" and candidate.get("readability", {}).get("score", -1)
                        > current["readability"]["score"])
            candidate["refactor_accepted"] = accepted
            if not accepted:
                stop_reason = "refactor_rejected_rolled_back"
                break
            current = candidate
            stop_reason = "refactor_accepted"
    final_source = final_rtl = None
    if current.get("bundle_path"):
        current["selected_final"] = True
        final_source = task_dir / "final"
        files = parse_bundle(Path(current["bundle_path"]).read_text(), language)
        write_bundle(files, final_source)
        (task_dir / "final.project.json").write_text(bundle_text(files))
        final_rtl = final_source
        if language == "chisel":
            final_rtl = None
            if current.get("rtl_path"):
                final_rtl = task_dir / "final-rtl"
                write_bundle({p.name: p.read_text() for p in sorted(Path(current["rtl_path"]).glob('*.sv'))}, final_rtl)
    metadata = current.get("generation_metadata", {})
    documents = metadata.get("skill_documents", {})
    final_status = status(current)
    initial_status = status(attempts[0])
    score = current.get("readability", {}).get("score")
    report = {
        "schema_version": 4, "pipeline_version": __version__, "artifact_kind": "multi_file_project",
        "task_id": task["id"], "group": group, "language": language,
        "provider": provider.name, "model": provider.model, "api_endpoint": getattr(provider, "url", None),
        "demo_only": provider.name == "mock", "pilot_only": True,
        "dataset_provenance": task["dataset_provenance"], "dataset": task["dataset_provenance"]["dataset"], "split": "pilot",
        "skill_version": "tool-v1" if metadata.get("skill_loaded") else None,
        "skill_requested": group == "Skill", "skill_loaded": metadata.get("skill_loaded", False),
        "skill_mode": metadata.get("agent_mode", "offline_replay"), "skill_documents": documents,
        "rules_applied": "rules.md" in documents, "rules_sha256": documents.get("rules.md", {}).get("sha256"),
        "rules_snapshot_sha256": digest(select_rules(rules, language)),
        "public_task": {"id": task["id"], "design_tops": task["design_tops"], "contract": task["contract_text"]},
        "evaluation_files_sha256": task.get("files_sha256", {}),
        "functional_status": final_status, "initial_functional_status": initial_status,
        "readability_score": score, "readability_status": current.get("readability", {}).get("status", "not_run"),
        "readability_method": current.get("readability", {}).get("method"),
        "readability_threshold_met": score is not None and score >= threshold, "stop_reason": stop_reason,
        "final_source": str(final_source) if final_source else None, "final_rtl": str(final_rtl) if final_rtl else None,
        "final_bundle": str(task_dir / "final.project.json") if final_source else None,
        "source_sha256": current.get("source_sha256"), "rtl_sha256": current.get("rtl_sha256"),
        "files_sha256": current.get("files_sha256", {}), "selected_attempt": current["index"] if final_source else None,
        "provider_calls": len(attempts),
        "tool_calls": sum(a.get("generation_metadata", {}).get("tool_calls", 0) for a in attempts),
        "model_calls": sum(a.get("generation_metadata", {}).get("model_calls", 0 if provider.name == "mock" else 1) for a in attempts),
        "model_call_count_estimated": any(a.get("generation_metadata", {}).get("call_count_estimated", False) for a in attempts),
        "repair_calls": sum(a["phase"] == "repair" for a in attempts),
        "refactor_calls": sum(a["phase"] == "refactor" for a in attempts),
        "repair_success": initial_status == "failed" and final_status == "passed",
        "effective_max_repairs": max_repairs, "effective_max_refactors": max_refactors,
        "elapsed_seconds": round(time.monotonic() - started, 4), "attempts": attempts,
    }
    save_json(task_dir / "report.json", report)
    return report


def run_batch(tasks, provider, settings, rules, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", settings)
    (output / "rules.md").write_text(select_rules(rules, language_of(settings)))
    save_json(output / "tools.json", tool_versions(output))
    reports = [run_task(task, provider, settings, rules, output) for task in tasks]
    return write_summary(reports, settings, output)


def write_summary(reports, settings, output, extra=None):
    fields = ["task_id", "language", "dataset", "split", "group", "provider", "model", "demo_only", "functional_status",
              "initial_functional_status", "skill_requested", "skill_loaded", "rules_applied",
              "readability_score", "readability_status", "readability_method", "provider_calls", "model_calls", "tool_calls",
              "repair_calls", "refactor_calls", "effective_max_repairs", "effective_max_refactors",
              "repair_success", "elapsed_seconds", "stop_reason"]
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(reports)
    summary = {
        "language": language_of(settings), "total": len(reports),
        "passed": sum(r["functional_status"] == "passed" for r in reports),
        "failed": sum(r["functional_status"] == "failed" for r in reports),
        "not_run": sum(r["functional_status"] == "not_run" for r in reports),
        "provider_calls": sum(r["provider_calls"] for r in reports), "model_calls": sum(r["model_calls"] for r in reports),
        "tool_calls": sum(r["tool_calls"] for r in reports), "skill_loaded_runs": sum(r["skill_loaded"] for r in reports),
        "model_call_count_estimated": any(r["model_call_count_estimated"] for r in reports),
        "repairs_succeeded": sum(r["repair_success"] for r in reports),
        "demo_only": any(r["demo_only"] for r in reports), "pilot_only": True, "output": str(output),
        "datasets": sorted({r["dataset"] for r in reports}), "splits": sorted({r["split"] for r in reports}),
        "dataset_manifests_sha256": sorted({r["dataset_provenance"]["manifest_sha256"] for r in reports}),
    }
    summary.update(extra or {})
    save_json(output / "summary.json", summary)
    return summary


def run_group_comparison(tasks, provider_factory, settings, rules, groups, output):
    groups = list(groups)
    if not groups or any(g not in GROUPS for g in groups):
        raise ValueError("groups 必须为非空的 Baseline/Skill 组列表；旧 A/B/C/D 策略不再支持")
    if len(set(groups)) != len(groups):
        raise ValueError("groups 不允许重复组名")
    tasks = list(tasks)
    if not tasks:
        raise ValueError("多组对比至少需要一个项目")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = {k: v for k, v in settings.items() if k != "group"}
    save_json(output / "config.json", {**config, "groups": groups, "task_ids": [t["id"] for t in tasks]})
    reports, group_summaries = [], {}
    by_task = {task["id"]: {} for task in tasks}
    fields = ("functional_status", "initial_functional_status", "skill_requested", "skill_loaded", "skill_mode",
              "rules_applied", "readability_score", "readability_status", "readability_method",
              "provider_calls", "model_calls", "tool_calls", "repair_calls",
              "refactor_calls", "effective_max_repairs", "effective_max_refactors", "elapsed_seconds",
              "stop_reason", "final_source", "final_rtl", "final_bundle")
    for group in groups:
        selected = {**settings, "group": group}
        group_summaries[group] = run_batch(tasks, provider_factory(selected), selected, rules, output / group)
        for task in tasks:
            path = output / group / task["id"] / "report.json"
            report = json.loads(path.read_text()); reports.append(report)
            by_task[task["id"]][group] = {**{key: report[key] for key in fields}, "report_path": str(path)}
    order = {task["id"]: index for index, task in enumerate(tasks)}
    reports.sort(key=lambda r: (order[r["task_id"]], groups.index(r["group"])))
    return write_summary(reports, settings, output, {"mode": "group_comparison", "task_count": len(tasks),
                        "groups": groups, "by_group": group_summaries, "by_task": by_task})
