"""Project bundles and candidate-only HDL validation. Process isolation, NOT a sandbox."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil

from .project_dataset import (elaborated_hierarchy, load_manifest, local_path,
                              output_verdict, sha256, unique_object)
from .providers import GenerationError
from .verify import not_run, run_command

MAX_FILES = 128
MAX_BYTES = 2_000_000
SAFE_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,159}\Z")
SYSTEM_FUNCTIONS = {"$clog2", "$signed", "$unsigned", "$bits"}


def masked(code, strings=True):
    """Lexical masking preserves line/column offsets; comments inside strings aren't comments."""
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"'
    def replace(match):
        text = match[0]
        if text.startswith('"') and not strings:
            return text
        return ''.join('\n' if c == '\n' else ' ' for c in text)
    return re.sub(pattern, replace, code)


def parse_bundle(text, language="verilog"):
    if language not in {"verilog", "systemverilog", "chisel"}:
        raise GenerationError("未知项目语言")
    if not isinstance(text, str):
        raise GenerationError("项目响应必须为JSON文本")
    try:
        response_bytes = len(text.encode())
    except UnicodeError as exc:
        raise GenerationError("项目响应包含无效Unicode") from exc
    if response_bytes > MAX_BYTES * 2:
        raise GenerationError("项目响应过大")
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    try:
        document = json.loads(text, object_pairs_hook=unique_object)
        if not isinstance(document, dict) or set(document) != {"files"}:
            raise ValueError("only files is permitted")
        if not isinstance(document["files"], list) or not 1 <= len(document["files"]) <= MAX_FILES:
            raise ValueError("expected 1..128 files")
        files, size = {}, 0
        suffixes = {"verilog": {".v", ".vh"}, "systemverilog": {".v", ".vh", ".sv", ".svh"},
                    "chisel": {".scala"}}[language]
        for item in document["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "content"}:
                raise ValueError("each file requires path and content only")
            name, code = item["path"], item["content"]
            if (not isinstance(name, str) or not SAFE_PATH.fullmatch(name)
                    or any(not p or p.startswith(".") for p in name.split("/"))
                    or PurePosixPath(name).suffix not in suffixes or name in files
                    or any(name.startswith(p + "/") or p.startswith(name + "/") for p in files)):
                raise ValueError("unsafe, duplicate, conflicting or non-HDL path")
            if not isinstance(code, str) or not code.strip() or "\x00" in code:
                raise ValueError("empty or invalid source")
            code = code if code.endswith("\n") else code + "\n"
            size += len(code.encode())
            if size > MAX_BYTES:
                raise ValueError("source exceeds 2 MB")
            files[name] = code
        if language == "chisel" and any(Path(p).name == "RTLFlowMain.scala" for p in files):
            raise ValueError("reserved harness filename")
        if not any(Path(p).suffix in ({".scala"} if language == "chisel" else {".v", ".sv"}) for p in files):
            raise ValueError("missing compilation unit")
        return dict(sorted(files.items()))
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise GenerationError(f"项目响应必须为完整 JSON files 数组：{exc}") from exc


def bundle_text(files):
    return json.dumps({"files": [{"path": name, "content": code} for name, code in sorted(files.items())]},
                      ensure_ascii=False, indent=2) + "\n"


def write_bundle(files, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for name, code in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code)
    return {name: sha256(directory / name) for name in files}


def include_policy(files):
    """Only candidate-local literal includes; no line remapping, macro includes or escaping IDs."""
    errors = []
    for name, code in files.items():
        clean = masked(code, strings=False)
        # No multiline escaped identifiers/directive splicing or token concatenation/stringification.
        if re.search(r'\\', masked(code)) or '``' in masked(code) or '`"' in clean:
            errors.append(f"{name}: escaped identifiers, splicing and macro token construction are unsupported")
        for match in re.finditer(r'(?m)^\s*`([A-Za-z_]\w*)\b([^\n]*)', clean):
            directive, rest = match.groups()
            if directive == "include":
                include = re.fullmatch(r'\s*"([A-Za-z0-9_][A-Za-z0-9_./-]*)"\s*', rest)
                if not include or include[1] not in files or ".." in include[1].split("/"):
                    errors.append(f"{name}: include must name a supplied file relative to project root")
            elif directive in {"line", "begin_keywords", "end_keywords", "pragma", "uselib", "protect"}:
                errors.append(f"{name}: forbidden directive `{directive}")
        # include can occur after whitespace/tokens too: reject every unreviewed occurrence.
        for match in re.finditer(r'`include\b', masked(code)):
            line_start = clean.rfind('\n', 0, match.start()) + 1
            if clean[line_start:match.start()].strip():
                errors.append(f"{name}: include must be a standalone directive")
        for directive in re.findall(r'`(line|begin_keywords|end_keywords|pragma|uselib|protect)\b', masked(code)):
            errors.append(f"{name}: forbidden directive `{directive}")
    return {"status": "failed" if errors else "passed", "reason": "candidate_local_includes", "issues": errors}


def expanded_policy(code):
    clean = masked(code)
    systems = sorted(set(re.findall(r'\$[A-Za-z_][\w$]*', clean)) - SYSTEM_FUNCTIONS)
    # XMR could inspect/drive TB state; normal named port connections (.port(...)) are unaffected.
    xmr = bool(re.search(r'(?:\b[A-Za-z_]\w*|\])\s*\.\s*[A-Za-z_]\w*', clean))
    # Only harmless directives survive -E. Unknown macro calls/line directives fail closed.
    directives = set(re.findall(r'`([A-Za-z_]\w*)', clean)) - {"timescale", "default_nettype", "resetall"}
    forbidden = sorted(set(re.findall(r'\b(?:force|release|bind|config|defparam|program|interface|class)\b', clean)))
    dpi = bool(re.search(r'\b(?:import|export)\s*"', masked(code, strings=False)))
    if dpi:
        forbidden.append("DPI")
    if systems or xmr or directives or forbidden:
        return {"status": "failed", "reason": "project_source_policy", "forbidden_system_names": systems,
                "hierarchical_reference": xmr, "forbidden_directives": sorted(directives), "forbidden_constructs": forbidden}
    return {"status": "passed", "reason": "preprocessed_candidate_policy"}


def scope_ports(binary, *, parameters=False, parameter_values=False, include_signed=False):
    """Icarus elaborated ports and optional public parameter values."""
    scopes, ports, params, values, current = {}, {}, {}, {}, None
    for line in Path(binary).read_text().splitlines():
        m = re.match(r'(S_\w+) \.scope (\w+), "([^"]+)" "([^"]+)" (.*);', line)
        if m:
            ident, kind, name, module, rest = m.groups()
            parent = re.search(r', (S_\w+)$', rest)
            scopes[ident] = (name, parent[1] if parent else None, kind, module)
            current = ident
            ports[ident] = {}
            params[ident] = []
            values[ident] = {}
        param = re.match(r'P_\w+ \.param/\w+ "([^"]+)" 0 ', line)
        if param and current:
            params[current].append(param[1])
            value = re.search(r'C4<([01]+)>', line)
            if value:
                values[current][param[1]] = int(value[1], 2)
        p = re.match(r'\s*\.port_info \d+ /(INPUT|OUTPUT|INOUT) (\d+) "([^"]+)";', line)
        if p and current:
            ports[current][p[3]] = {"direction": p[1].lower(), "width": int(p[2])}
            if include_signed:
                ports[current][p[3]]["signed"] = False
        net = re.match(r'v\w+ \.(?:net|var)(/(?:2)?s)?(?:/2u)? "([^"]+)"', line)
        if include_signed and net and current and net[2] in ports[current]:
            ports[current][net[2]]["signed"] = bool(net[1])
    def path(ident):
        name, parent, _, _ = scopes[ident]
        return (path(parent) + "." if parent else "") + name
    if parameter_values:
        return {path(i): values[i] for i, s in scopes.items() if s[2] == "module"}
    if parameters:
        return {path(i): sorted(params[i]) for i, s in scopes.items() if s[2] == "module"}
    return {path(i): {"module": s[3], "ports": ports[i]} for i, s in scopes.items() if s[2] == "module"}


def load_projects(path, selected=None, language="verilog"):
    path = Path(path).resolve()
    root, document, _ = load_manifest(path)
    if document.get("generation_ready") is not True or document.get("split") != "pilot":
        raise ValueError("项目清单未就绪或不是当前支持的pilot切分")
    if language not in {"verilog", "systemverilog", "chisel"} or language not in document["languages"]:
        raise ValueError("项目清单不支持请求的目标语言，未调用模型")
    definitions = {task["id"]: task for task in document["tasks"]}
    tasks = []
    for key, definition in definitions.items():
        config = definition.get("generation")
        if not isinstance(config, dict) or set(config) != {"files_sha256", "candidate_testbench_files", "expected_ports",
                           "public_parameters", "testbench_adaptations",
                           "additional_dut_roots", "additional_required_output"}:
            raise ValueError("unknown/missing project generation fields")
        task = {**{k: v for k, v in definition.items() if k != "generation"}, **config}
        task["contract"] = definition["specification"]
        task["dut_roots"] = [*task["dut_roots"], *config["additional_dut_roots"]]
        task["required_output"] = [*task["required_output"], *config["additional_required_output"]]
        for name, expected in config["files_sha256"].items():
            if sha256(local_path(root, name)) != expected:
                raise ValueError(f"project contract/test checksum mismatch: {name}")
        needed = config["candidate_testbench_files"]
        if not set(needed) <= set(config["files_sha256"]):
            raise ValueError("unlocked project generation inputs")
        if set(config["expected_ports"]) != set(task["dut_roots"]):
            raise ValueError("missing elaborated public port contract")
        if set(config["public_parameters"]) != set(task["design_tops"]):
            raise ValueError("missing public parameter contract")
        supported = task.get("target_languages", ["verilog", "systemverilog"])
        if language not in supported:
            if selected and key in selected:
                raise ValueError(f"项目 {key} 不支持目标语言 {language}；支持：{supported}，未调用模型")
            continue
        if language == "chisel":
            from .chisel import validate_chisel_config
            validate_chisel_config(task.get("chisel_tops"), task["design_tops"])
            if any(config["public_parameters"].values()):
                raise ValueError("Chisel 后端使用固定构造参数，不支持 Verilog 参数覆写")
        task.update(project=True, dataset_root=str(root),
                    contract_text=(root / task["specification"]).read_text(),
                    dataset_provenance={"dataset": document["dataset"], "split": "pilot",
                        "manifest_sha256": sha256(path),
                        "source_id": key, "source_language": task.get("language", "verilog"),
                        "target_language": language, "quality_status": "project_pilot"})
        tasks.append(task)
    if selected:
        if set(selected) - set(definitions):
            raise ValueError("未知项目 ID：" + ", ".join(sorted(set(selected) - set(definitions))))
        tasks = [t for t in tasks if t["id"] in selected]
    if not tasks:
        raise ValueError("没有支持该目标语言的项目")
    return tasks


def verify_project(files, directory, task, workdir, settings):
    if task.get("design_contract") and not task.get("verification_bound"):
        from .design_verify import bind_verification
        try:
            bound = bind_verification(task, workdir)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {"functional_status": "not_run", "checks": {"frozen_artifacts": {
                "status": "not_run", "reason": str(exc)}}, "reference_rtl_linked": False}
        result = verify_project(files, directory, bound, workdir, settings)
        result.update(contract_sha256=task["contract_sha256"], verification_sha256=task["verification_sha256"],
                      validation_scope="frozen_independent_model_testbench")
        return result
    directory, workdir = Path(directory).resolve(), Path(workdir).resolve()
    root = Path(task["dataset_root"])
    workdir.mkdir(parents=True, exist_ok=True)
    required = ("source_policy", "preprocess", "candidate_compile", "compile", "interface", "hierarchy", "simulation")
    checks = {name: not_run("earlier_stage_not_passed") for name in required}
    checks.update({name: not_run("project_lint_not_integrated") for name in ("verilator", "verible-verilog-lint")})
    result = {"checks": checks, "functional_status": "not_run", "candidate_files": list(files),
              "reference_rtl_linked": False, "validation_scope": "adapted_top_level_functional_tests"}
    def finish():
        statuses = [checks[name]["status"] for name in required]
        result["functional_status"] = "failed" if "failed" in statuses else "not_run" if "not_run" in statuses else "passed"
        return result
    # Confirm the on-disk snapshot, not just the response strings checked for include safety.
    for name, code in files.items():
        try:
            path = local_path(directory, name)
            if path.read_text() != code:
                raise ValueError("candidate source changed after parsing")
        except (OSError, ValueError):
            checks["source_policy"] = {"status": "failed", "reason": "candidate_snapshot_mismatch"}
            return finish()
    if settings.get("language") == "chisel":
        from .chisel import elaborate_chisel
        frontend = elaborate_chisel(files, task, workdir / "chisel", settings.get("chisel_timeout_seconds", 300))
        result["chisel"] = {k: v for k, v in frontend.items() if k != "files"}
        checks.update(frontend["checks"])
        if frontend["files"] is None:
            states = [c["status"] for c in frontend["checks"].values()]
            result["functional_status"] = "failed" if "failed" in states else "not_run"
            return result
        emitted = workdir / "emitted"
        write_bundle(frontend["files"], emitted)
        rtl = verify_project(frontend["files"], emitted, task, workdir / "rtl", {**settings, "language": "systemverilog"})
        result.update(functional_status=rtl["functional_status"], emitted_directory=str(emitted),
                      emitted_files=rtl["candidate_files"])
        checks.update(rtl["checks"])
        return result
    checks["source_policy"] = include_policy(files)
    if checks["source_policy"]["status"] != "passed":
        return finish()
    compiler, simulator = shutil.which("iverilog"), shutil.which("vvp")
    if not compiler or not simulator:
        checks["preprocess"] = not_run("missing_iverilog_or_vvp")
        return finish()
    language = settings.get("language", "verilog")
    dialect = "2012" if language == "systemverilog" else task["dialect"]
    timeout = settings.get("tool_timeout_seconds", 30)
    units = [directory / name for name in files if Path(name).suffix in {".v", ".sv"}]
    expanded = workdir / "candidate.expanded.v"
    # Candidate preprocessing never searches trusted source, testbench or repository directories.
    checks["preprocess"] = run_command([compiler, "-g" + dialect, "-E", "-I", directory,
        *["-D" + name for name in task["defines"]], "-o", expanded, *units], directory, "preprocess", timeout)
    if checks["preprocess"]["status"] != "passed":
        return finish()
    if not expanded.is_file() or expanded.stat().st_size > MAX_BYTES * 4:
        checks["source_policy"] = {"status": "failed", "reason": "missing_or_oversize_preprocessed_source"}
        return finish()
    checks["source_policy"] = expanded_policy(expanded.read_text())
    if checks["source_policy"]["status"] != "passed":
        return finish()
    # First elaborate only public design tops, so any diagnostics here cannot expose hidden TB.
    tops = [arg for top in task["design_tops"] for arg in ("-s", top)]
    checks["candidate_compile"] = run_command([compiler, "-g" + dialect, *tops,
        "-o", workdir / "candidate-only.vvp", expanded], workdir, "candidate-compile", timeout)
    if checks["candidate_compile"]["status"] != "passed":
        return finish()
    actual_parameters = scope_ports(workdir / "candidate-only.vvp", parameters=True)
    for top, names in task.get("public_parameters", {}).items():
        if not set(names) <= set(actual_parameters.get(top, [])):
            checks["interface"] = {"status": "failed", "reason": "missing_public_parameters",
                                   "top": top, "missing": sorted(set(names) - set(actual_parameters.get(top, [])))}
            return finish()
    if task.get("design_contract"):
        actual_values = scope_ports(workdir / "candidate-only.vvp", parameter_values=True)
        for top in task["design_contract"]["contract"]["tops"]:
            if (actual_values.get(top["name"]) != top["parameters"]
                    or set(actual_parameters.get(top["name"], [])) != set(top["parameters"])):
                checks["interface"] = {"status": "failed", "reason": "frozen_parameter_defaults_mismatch"}
                return finish()
    testbench = [root / name for name in task["candidate_testbench_files"]]
    binary = workdir / "simulation.vvp"
    # The TB uses its original dialect (notably SPI's `int` identifier). Candidate SV was
    # preprocessed separately; begin_keywords scopes keep SV candidates and Verilog TB distinct.
    tb_wrapper = workdir / "trusted-testbench.v"
    keywords = dialect == "2012" and task["dialect"] == "2005"
    tb_wrapper.write_text('`resetall\n' + ('`begin_keywords "1364-2005"\n' if keywords else '')
        + '\n'.join('`include "' + str(path) + '"' for path in testbench)
        + ('\n`end_keywords\n' if keywords else '\n'))
    testbench = [tb_wrapper]
    command = [compiler, "-g" + dialect, "-o", binary]
    for top in task["testbench_tops"]:
        command += ["-s", top]
    for name in task["include_dirs"]:
        command += ["-I", root / name]
    command += ["-D" + name for name in task["defines"]]
    command += [expanded, *testbench]
    checks["compile"] = run_command(command, workdir, "compile", timeout)
    if checks["compile"]["status"] != "passed":
        return finish()
    compile_log = Path(checks["compile"]["stderr_log"]).read_text(errors="replace")
    if re.search(r'warning:.*(?:parameter .*not found|defparam.*not found)', compile_log, re.I):
        checks["interface"] = {"status": "failed", "reason": "public_parameter_override_not_applied"}
        return finish()
    actual = scope_ports(binary, include_signed=bool(task.get("design_contract")))
    interface_ok = all(actual.get(name) == expected for name, expected in task["expected_ports"].items())
    checks["interface"] = {"status": "passed" if interface_ok else "failed", "reason": "public_ports_exact",
                           "actual": {name: actual.get(name) for name in task["dut_roots"]}}
    if not interface_ok:
        return finish()
    try:
        hierarchy = elaborated_hierarchy(binary, task["dut_roots"])
        # TB parameter overrides can activate branches absent from the default-top compile.
        # Every actually elaborated DUT module must still be defined by the candidate.
        declared = set(re.findall(r'\b(?:module|macromodule)\s+(?:(?:automatic|static)\s+)?([A-Za-z_]\w*)',
                                  masked(expanded.read_text())))
        external = sorted(set(hierarchy["module_types"]) - declared)
        if external:
            checks["hierarchy"] = {"status": "failed", "reason": "non_candidate_design_dependency",
                                   "external_modules": external}
            return finish()
        for top in task["dut_roots"]:
            if not any(i["instance"].startswith(top + ".") for i in hierarchy["instances"]):
                raise ValueError("每个公开顶层必须包含实际展开的子模块，不接受单层占位实现")
        checks["hierarchy"] = {"status": "passed", **hierarchy}
    except ValueError as exc:
        checks["hierarchy"] = {"status": "failed", "reason": str(exc)}
        return finish()
    for name, origin in task.get("runtime_files", {}).items():
        destination = workdir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / origin, destination)
    checks["simulation"] = run_command([simulator, "-i", "-n", binary, *task.get("simulation_args", [])],
        workdir, "simulation", max(timeout, task["simulation_timeout_seconds"]))
    simulation = checks["simulation"]
    text = '\n'.join(Path(simulation[name]).read_text(errors="replace") for name in ("stdout_log", "stderr_log"))
    verdict = output_verdict(task, text)
    simulation["verdict"] = verdict
    if simulation["status"] == "passed" and not verdict["passed"]:
        simulation.update(status="failed", reason="functional_test_verdict")
    return finish()
