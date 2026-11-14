"""Pinned, multi-module project intake and reference-only validation.

This is NOT a candidate/model runner and NOT a sandbox. Only reviewed,
checksum-locked reference HDL/TBs are compiled. No upstream build scripts run.
"""

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import urllib.request

from .verify import run_command

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
TARGET = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+(?:\[\d+\])?\Z")
LITERAL = re.compile(r"\d+'[bh][0-9a-f]+\Z", re.I)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique_object(pairs):
    """Reject duplicate keys in task catalogs, source locks and model bundles."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def local_path(root, name, *, directory=False, exists=True):
    if (not isinstance(name, str) or not name or "\\" in name
            or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts):
        raise ValueError(f"unsafe relative dataset path: {name}")
    path = root / name
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"symlink or escaping dataset path: {name}")
    if exists and not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"missing dataset path: {name}")
    return path


def load_manifest(path, *, check_sources=True):
    path = Path(path).resolve()
    root = path.parent
    document = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if not isinstance(document, dict) or document.get("schema_version") != "project-rtl-v2" or document.get("split") != "pilot":
        raise ValueError("expected project-rtl-v2 pilot task catalog (tasks.json)")
    lock_path = local_path(root, document["sources_lock"])
    if sha256(lock_path) != document["sources_lock_sha256"]:
        raise ValueError("source lock checksum mismatch")
    lock = json.loads(lock_path.read_text(), object_pairs_hook=unique_object)["sources"]
    known_files = {}
    for repo, source in lock.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid repository identifier")
        if (source["repository"] != f"https://github.com/{repo}"
                or not re.fullmatch(r"[a-f0-9]{40}", source["revision"])
                or not re.fullmatch(r"[a-f0-9]{64}", source["archive_sha256"])):
            raise ValueError("unlocked source repository")
        prefix = f"sources/{repo}/"
        for name, expected in source["files"].items():
            source_path = local_path(root, prefix + name, exists=check_sources)
            if not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ValueError("invalid source digest")
            if check_sources and sha256(source_path) != expected:
                raise ValueError(f"upstream checksum mismatch: {prefix + name}")
            known_files[prefix + name] = expected
        if check_sources:
            actual = {str(p.relative_to(root)) for p in (root / prefix).rglob("*") if p.is_file()}
            if actual != {prefix + name for name in source["files"]}:
                raise ValueError(f"source inventory mismatch: {repo}")
    for name, expected in document["support_sha256"].items():
        if sha256(local_path(root, name)) != expected:
            raise ValueError(f"verification support checksum mismatch: {name}")
        known_files[name] = expected
    tasks = document["tasks"]
    if not isinstance(tasks, list) or len(tasks) != document["case_count"] or not tasks:
        raise ValueError("project task count mismatch")
    ids = set()
    for task in tasks:
        key = task["id"]
        if not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or key in ids:
            raise ValueError("duplicate/invalid task ID")
        ids.add(key)
        language = task.get("language", "verilog")
        if language not in {"verilog", "systemverilog", "chisel"}:
            raise ValueError("unknown source language")
        targets = task.get("target_languages", ["verilog", "systemverilog"])
        if not targets or len(set(targets)) != len(targets) or set(targets) - {"verilog", "systemverilog", "chisel"}:
            raise ValueError("invalid target languages")
        if "chisel" in targets:
            from .chisel import validate_chisel_config
            validate_chisel_config(task.get("chisel_tops"), task["design_tops"])
        if task["repository"] not in lock or task["dialect"] not in {"2005", "2012"}:
            raise ValueError("unknown repository or dialect")
        for field in ("design_tops", "testbench_tops"):
            if not task[field] or any(not IDENTIFIER.fullmatch(v) for v in task[field]):
                raise ValueError(f"invalid {field}: {key}")
        for field in ("rtl_files", "testbench_files"):
            if not task[field] or len(set(task[field])) != len(task[field]):
                raise ValueError(f"empty/duplicate {field}: {key}")
            for name in task[field]:
                if name not in known_files:
                    raise ValueError(f"unlocked build input: {name}")
        suffixes = {Path(name).suffix for name in task['rtl_files']}
        allowed = {'verilog': {'.v', '.vh'}, 'systemverilog': {'.v', '.vh', '.sv', '.svh'}, 'chisel': {'.scala'}}[language]
        if not suffixes <= allowed or (language == 'systemverilog' and not suffixes & {'.sv', '.svh'}):
            raise ValueError('native source language does not match design file inventory')
        if set(task["rtl_files"]) & set(task["testbench_files"]):
            raise ValueError("testbench mixed into reference RTL")
        for name in task["include_dirs"]:
            local_path(root, name, directory=True, exists=check_sources)
            if not any(p.startswith(name + "/") for p in known_files):
                raise ValueError("include directory outside source inventory")
        if any(not IDENTIFIER.fullmatch(v) for v in task["defines"]):
            raise ValueError("invalid preprocessor define")
        if not task["dut_roots"] or any(not TARGET.fullmatch(v) for v in task["dut_roots"]):
            raise ValueError("invalid DUT hierarchy root")
        for fault in task["negative_forces"]:
            if not TARGET.fullmatch(fault["target"]) or not LITERAL.fullmatch(fault["value"]):
                raise ValueError("invalid negative-control force")
            if not any(fault["target"].startswith(p + ".") for p in task["dut_roots"]):
                raise ValueError("negative control must target DUT, not TB")
        if not task["required_output"] or not task["forbidden_output"] or not task["negative_forces"]:
            raise ValueError("missing verdict or negative control")
        for requirement in task["required_output"]:
            re.compile(requirement["regex"])
            if type(requirement["min_count"]) is not int or requirement["min_count"] < 1:
                raise ValueError("vacuous positive verdict")
        for expression in task["forbidden_output"]:
            re.compile(expression)
        for name, origin in task.get("runtime_files", {}).items():
            local_path(root, name, exists=False)
            if origin not in known_files:
                raise ValueError("unlocked runtime input")
        if any(not isinstance(arg, str) or not arg.startswith("+") for arg in task.get("simulation_args", [])):
            raise ValueError("only simulation plusargs are allowed")
        for field in ("simulation_timeout_seconds", "negative_timeout_seconds"):
            if type(task[field]) not in {int, float} or not 0 < task[field] <= 600:
                raise ValueError("invalid simulation timeout")
        if sha256(local_path(root, task["specification"])) != task["specification_sha256"]:
            raise ValueError(f"public specification checksum mismatch: {key}")
    return root, document, lock


def download_sources(root, lock):
    """Explicit network action. Exact pinned archives; never execute or overwrite."""
    for repo, source in lock.items():
        target = local_path(root, f"sources/{repo}", directory=True, exists=False)
        if target.exists():
            continue  # load_manifest(check_sources=True) checks the existing bytes.
        request = urllib.request.Request(
            f"https://codeload.github.com/{repo}/tar.gz/{source['revision']}",
            headers={"User-Agent": "Skill-RTL-project-dataset"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            archive = response.read(120_000_001)
        if len(archive) > 120_000_000 or hashlib.sha256(archive).hexdigest() != source["archive_sha256"]:
            raise ValueError(f"archive size/checksum mismatch: {repo}")
        found = {}
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as stream:
            for member in stream:
                name = str(PurePosixPath(*PurePosixPath(member.name).parts[1:]))
                if name not in source["files"]:
                    continue
                local_path(target, name, exists=False)
                if not member.isfile() or member.issym() or member.islnk() or member.size > 15_000_000:
                    raise ValueError("non-regular/oversize archived source")
                content = stream.extractfile(member).read()
                if name in found or hashlib.sha256(content).hexdigest() != source["files"][name]:
                    raise ValueError("duplicate/changed archive entry")
                found[name] = content
        if set(found) != set(source["files"]):
            raise ValueError(f"incomplete archive: {repo}")
        target.mkdir(parents=True, exist_ok=False)
        for name, content in found.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def output_verdict(task, text):
    """Require all positive markers/counts AND absence of failures over full logs."""
    counts = [len(re.findall(p["regex"], text)) for p in task["required_output"]]
    failures = [p for p in task["forbidden_output"] if re.search(p, text)]
    return {"passed": all(n >= p["min_count"] for n, p in zip(counts, task["required_output"])) and not failures,
            "positive_match_counts": counts, "failure_patterns_seen": failures}


def elaborated_hierarchy(binary, roots):
    """Read Icarus's elaborated scope graph, not a regex guess at instantiations."""
    scopes = {}
    for line in Path(binary).read_text().splitlines():
        match = re.match(r'(S_\w+) \.scope (\w+), "([^"]+)" "([^"]+)" (.*);', line)
        if match:
            identifier, kind, name, module, rest = match.groups()
            parent = re.search(r', (S_\w+)$', rest)
            scopes[identifier] = (kind, name, module, parent[1] if parent else None)
    def fullname(identifier):
        _, name, _, parent = scopes[identifier]
        return (fullname(parent) + "." if parent else "") + name
    modules = []
    for identifier, (kind, _, module, _) in scopes.items():
        if kind != "module":
            continue
        path = fullname(identifier)
        if any(path == p or path.startswith(p + ".") for p in roots):
            modules.append({"instance": path, "module": module})
    if any(p not in {m["instance"] for m in modules} for p in roots):
        raise ValueError("declared DUT root absent from elaborated testbench")
    types = sorted({m["module"] for m in modules})
    if len(types) < 2:
        raise ValueError("case does not elaborate a top AND submodule")
    return {"module_types": types, "module_type_count": len(types),
            "instance_count": len(modules), "instances": sorted(modules, key=lambda m: m["instance"])}


def reference_compatibility(task, code):
    """Icarus requires repeated parameter keywords for these typed parameter lists."""
    if task['id'] in {'sv_spi', 'sv_uart_printer'}:
        code = re.sub(r'(?m)^(  )(bit\s+(?:\[[^\n]+?\]\s+)?[A-Z][A-Z0-9_]*\s*=)', r'\1parameter \2', code)
        # The first item already follows the header's parameter keyword.
        code = re.sub(r'(module\s+\w+\s*#\(\s*parameter\s*)parameter\s+', r'\1', code)
    if task['id'] == 'sv_spi' and 'module spi_master' in code:
        # Upstream top still uses the pre-v4 edge_detect reset port spelling.
        code = code.replace('.nrst( nrst )', '.anrst( nrst )').replace('.nrst( {2{nrst}} )', '.anrst( {2{nrst}} )')
    if task['id'] == 'systolic_matmul':
        # Icarus lacks these SV port/type spellings and mixed procedural/module
        # drivers on disjoint packed slices. Preserve unsigned 32-bit parameters
        # and express the two combinational boundary wires as continuous assigns.
        code = code.replace('input  var logic', 'input  wire logic').replace('output var logic', 'output logic')
        code = code.replace('int unsigned', 'logic [31:0]')
        code = code.replace('    $error(', '    initial $error(')
        code = code.replace('logic [N-1:0][N:0][7:0] rowInterConnect', 'wire [N-1:0][N:0][7:0] rowInterConnect')
        code = code.replace('logic [N:0][N-1:0][7:0] colInterConnect', 'wire [N:0][N-1:0][7:0] colInterConnect')
        code = code.replace('always_comb\n      rowInterConnect', 'assign rowInterConnect')
        code = code.replace('always_comb\n      colInterConnect', 'assign colInterConnect')
    return code


def verify_reference(root, task, output):
    output = Path(output).resolve() / task["id"]
    output.mkdir(parents=True, exist_ok=False)
    report = {"task_id": task["id"], "scope": "reference_only", "model_calls": 0,
              "coverage": task["coverage"], "limitations": task["limitations"],
              "reference_status": "not_run", "negative_control_status": "not_run"}
    compiler, simulator = shutil.which("iverilog"), shutil.which("vvp")
    if not compiler or not simulator:
        report["reason"] = "missing_iverilog_or_vvp"
        save_json(output / "report.json", report)
        return report
    rtl_files = [root / name for name in task['rtl_files']]
    if task['id'] in {'sv_spi', 'sv_uart_printer', 'systolic_matmul'}:
        rtl_files = []
        for name in task['rtl_files']:
            dest = output / Path(name).name
            dest.write_text(reference_compatibility(task, (root / name).read_text()))
            rtl_files.append(dest)
        report['reference_compatibility'] = (
            'Icarus copy: explicit net/output port kinds, unsigned 32-bit parameter spelling, initial parameter diagnostic, '
            'continuous boundary interconnect assignments; no algorithm/sequential changes. Original source unchanged.'
            if task['id'] == 'systolic_matmul' else
            'Repeated parameter keywords for Icarus; SPI edge_detect reset port nrst->anrst. Original source unchanged.')
    if task.get('language') == 'chisel':
        from .chisel import elaborate_chisel, reference_sources
        frontend = elaborate_chisel(reference_sources(root, task), task, output / 'chisel', trusted_reference=True)
        report['chisel'] = {k: v for k, v in frontend.items() if k != 'files'}
        if frontend['files'] is None:
            report['reference_status'] = 'failed' if any(c['status'] == 'failed' for c in frontend['checks'].values()) else 'not_run'
            save_json(output / 'report.json', report)
            return report
        rtl_files = []
        for name, code in frontend['files'].items():
            emitted = output / name
            emitted.write_text(code)
            rtl_files.append(emitted)
    command = [compiler, "-g" + task["dialect"]]
    for top in task["testbench_tops"]:
        command += ["-s", top]
    for directory in task["include_dirs"]:
        command += ["-I", str(root / directory)]
    command += ["-D" + value for value in task["defines"]]
    command += [str(p) for p in rtl_files] + [str(root / name) for name in task["testbench_files"]]
    for negative in (False, True):
        phase = "negative" if negative else "reference"
        work = output / phase
        work.mkdir()
        for name, origin in task.get("runtime_files", {}).items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / origin, target)
        binary = work / "simulation.vvp"
        cmd = command + ["-o", str(binary)]
        if negative:
            fault = work / "negative_control.v"
            fault.write_text("module project_negative_control;\ninitial begin\n" + "\n".join(
                f"force {item['target']} = {item['value']};" for item in task["negative_forces"]
            ) + "\nend\nendmodule\n")
            cmd += ["-s", "project_negative_control", str(fault)]
        compile_check = run_command(cmd, work, "compile", 30)
        stage = {"compile": compile_check}
        report[phase] = stage
        if compile_check["status"] != "passed":
            report["negative_control_status" if negative else "reference_status"] = compile_check["status"]
            break  # a non-compiling mutant does not prove test sensitivity
        if not negative:
            report["hierarchy"] = elaborated_hierarchy(binary, task["dut_roots"])
            if not set(task["design_tops"]) <= set(report["hierarchy"]["module_types"]):
                raise ValueError("declared design top not exercised")
        timeout = task["negative_timeout_seconds"] if negative else task["simulation_timeout_seconds"]
        simulation = run_command([simulator, "-i", "-n", str(binary), *task.get("simulation_args", [])], work, "simulation", timeout)
        # Full logs, never just the bounded preview; stderr failure messages count too.
        text = "\n".join(Path(simulation[key]).read_text(errors="replace") for key in ("stdout_log", "stderr_log"))
        verdict = output_verdict(task, text)
        stage.update(simulation=simulation, verdict=verdict)
        accepted = simulation["status"] == "passed" and verdict["passed"]
        if negative:
            explicit_failure = bool(verdict["failure_patterns_seen"]) or (
                simulation["reason"] == "exit_code" and simulation["returncode"] != 0)
            report["negative_control_status"] = ("failed" if accepted else "passed" if explicit_failure else "inconclusive")
            stage["accepted_as_correct"] = accepted
        else:
            report["reference_status"] = "passed" if accepted else "failed"
            if not accepted:
                break
        # Compiled binaries and VCD are reproducible scratch, not validation evidence.
        binary.unlink()
        for waveform in work.glob("*.vcd"):
            waveform.unlink()
    for phase in ("reference", "negative"):
        for check in ("compile", "simulation"):
            item = report.get(phase, {}).get(check)
            if item:
                for key in ("stdout", "stderr"):
                    item.pop(key, None)
                    log = Path(item[key + "_log"])
                    item[key + "_sha256"] = sha256(log)
    save_json(output / "report.json", report)
    return report
