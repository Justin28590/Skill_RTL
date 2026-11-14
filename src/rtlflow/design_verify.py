"""Independent verification synthesis, frozen before implementation, with negative controls.

This is model-authored verification in an isolated conversation, not a trusted
mathematical oracle or a security sandbox. No reference RTL or old TB is linked.
"""
import json
from pathlib import Path
import re
import shutil

from .design import (canonical, exact, fingerprint, model_call, parse_json, text,
                     validate_contract, width)
from .project_dataset import save_json, unique_object
from .verify import run_command

PASS = "RTL_CHECK_PASS"
FAIL = "RTL_CHECK_FAIL"


def configurations(contract):
    tops = {t["name"]: t for t in contract["tops"]}
    for index, config in enumerate(contract["configurations"]):
        top = tops[config["top"]]
        parameters = {**top["parameters"], **config["parameters"]}
        yield index, top, config["parameters"], {
            name: {**port, "width": width(port["width"], parameters)} for name, port in top["ports"].items()}


def harness(contract, body):
    declarations, instances = [], []
    for i, top, overrides, ports in configurations(contract):
        for name, port in ports.items():
            kind = {"input": "reg", "output": "wire", "inout": "tri"}[port["direction"]]
            signed = "signed " if port["signed"] else ""
            declarations.append(f"{kind} {signed}[{port['width']-1}:0] c{i}_{name};")
        params = " #(" + ",".join(f".{k}({v})" for k, v in overrides.items()) + ")" if overrides else ""
        connections = ",".join(f".{name}(c{i}_{name})" for name in ports)
        instances.append(f"{top['name']}{params} dut{i}({connections});")
    return "`timescale 1ns/1ps\nmodule rtlflow_tb;\n" + '\n'.join(declarations + instances) + '\n' + body + '\nendmodule\n'


def stubs(contract, value):
    """Negative implementations, not a reference implementation; all outputs constant."""
    sources = []
    for top in contract["tops"]:
        parameters = top["parameters"]
        params = " #(" + ",".join(f"parameter {k}={v}" for k, v in parameters.items()) + ")" if parameters else ""
        ports, assignments = [], []
        for name, port in top["ports"].items():
            w = str(port["width"]).replace("//", "/")
            ports.append(f"{port['direction']} wire {'signed ' if port['signed'] else ''}[({w})-1:0] {name}")
            if port["direction"] != "input":
                assignments.append(f"assign {name} = {{({w}){{1'b{value}}}}};")
        sources.append(f"module {top['name']}{params}({','.join(ports)});\n" + '\n'.join(assignments) + '\nendmodule\n')
    return '\n'.join(sources)


def validate_testbench(document):
    from .project import masked
    exact(document, "body coverage oracle_description", "独立测试")
    text(document["body"], "TB body", 1_000_000)
    text(document["oracle_description"], "独立期望值计算依据")
    if not isinstance(document["coverage"], list) or not document["coverage"]:
        raise ValueError("必须列出需求与检查覆盖")
    for item in document["coverage"]: text(item, "覆盖项")
    body = document["body"]
    clean = masked(body)
    forbidden = re.search(r'\b(?:module|endmodule|primitive|interface|program|class|package|import|export|force|release|bind|defparam|config)\b', clean)
    allowed = {"$display", "$fatal", "$finish", "$random", "$urandom", "$urandom_range", "$clog2", "$signed", "$unsigned", "$bits", "$time", "$isunknown", "$countones"}
    systems = set(re.findall(r'\$[A-Za-z_][\w$]*', clean))
    if (forbidden or systems - allowed or '`' in clean or '\\' in clean
            or re.search(r'(?:\b[A-Za-z_]\w*|\])\s*\.\s*[A-Za-z_]\w*', clean)):
        raise ValueError("TB含禁止构造/I/O/层次访问；仅允许宿主连接的cN_port信号")
    if PASS not in body or FAIL not in body or "$fatal" not in clean:
        raise ValueError("TB必须包含成功标记和带失败标记的$fatal断言")
    return document


def test_messages(task):
    contract = task["design_contract"]["contract"]
    return [{"role": "system", "content":
        "你是独立硬件验证工程师。只根据高层需求和已冻结设计契约构造自检查SystemVerilog TB。"
        "你看不到候选RTL，不允许复制旧TB或参考实现，不得修改契约。期望值必须来自独立算法/协议scoreboard、"
        "标准已知向量或可解释参考模型，不从DUT输出反推。覆盖所有顶层/配置、正常/边界/随机、复位中断、"
        "握手背压、精确或有界延迟、吞吐及无多余输出；串行/总线/多时钟按契约驱动。"
        '仅返回JSON：{"body":"模块内部SV源码","coverage":["需求->实际检查"],"oracle_description":"独立oracle依据与限制"}。'
        "宿主已经声明c0_端口名、c1_端口名等信号并实例化所有配置，不能重复声明它们或实例化任何模块；"
        "input为reg由你驱动，output为wire只能读取，inout为tri需你声明局部reg并assign驱动/高阻。"
        "body仅含任务/函数/寄存器/initial/always等模块内部语句，不含module、include、宏、层次访问、force/release或文件/网络I/O。"
        "允许$display/$fatal/$finish/$random/$urandom/$urandom_range/$clog2/$signed/$unsigned/$bits/$time/$isunknown/$countones。"
        "所有检查用!==等四态安全比较；不匹配执行$fatal(1,\"RTL_CHECK_FAIL:原因\")。"
        "必须有仿真周期看门狗，超限用上述失败断言退出，不能等宿主超时。所有测试完成后输出RTL_CHECK_PASS并$finish。"
        "不能只测试空闲；全部输出恒0及恒1的两个负控必须都被断言拒绝。有限测试不能宣称完整证明。"},
        {"role": "user", "content": canonical({"requirements": task["requirements_text"], "contract": contract,
            "host_harness": harness(contract, "// INSERT BODY HERE")})}]


def quality_gate(contract, body, directory, settings):
    compiler, simulator = shutil.which("iverilog"), shutil.which("vvp")
    if not compiler or not simulator:
        return {"status": "not_run", "reason": "missing_iverilog_or_vvp"}
    tb = directory / "tb.sv"
    tb.write_text(harness(contract, body))
    checks = []
    timeout = settings.get("tool_timeout_seconds", 30)
    for value in (0, 1):
        stub = directory / f"negative_{value}.sv"
        stub.write_text(stubs(contract, value))
        binary = directory / f"negative_{value}.vvp"
        compile_check = run_command([compiler, "-g2012", "-s", "rtlflow_tb", "-o", binary, tb, stub],
                                    directory, f"negative_{value}_compile", timeout)
        checks.append(compile_check)
        if compile_check["status"] != "passed":
            return {"status": compile_check["status"], "reason": "verification_compile", "checks": checks}
        simulation = run_command([simulator, "-i", "-n", binary], directory, f"negative_{value}_simulation", timeout)
        checks.append(simulation)
        output = Path(simulation["stdout_log"]).read_text(errors="replace") + Path(simulation["stderr_log"]).read_text(errors="replace")
        if simulation["status"] == "not_run":
            return {"status": "not_run", "reason": "verification_tool_unavailable", "checks": checks}
        if (simulation["reason"] == "timeout" or simulation["returncode"] == 0 or FAIL not in output or PASS in output):
            return {"status": "failed", "reason": "negative_control_not_rejected_by_assertion", "checks": checks}
    return {"status": "passed", "reason": "both_constant_output_controls_rejected", "checks": checks}


def prepare_verification(task, provider, settings, directory):
    directory = Path(directory) / "verification"
    directory.mkdir()
    base = test_messages(task)
    attempts, previous = [], None
    for index in range(1 + settings.get("max_verification_repairs", 1)):
        messages = list(base)
        if previous:
            messages += [{"role": "assistant", "content": previous[0]}, {"role": "user", "content": previous[1]}]
        work = directory / f"attempt_{index:02d}"
        response, attempt = model_call(provider, task["id"], messages, work, "verification_design", settings)
        attempts.append(attempt)
        if response is None: break
        try:
            document = validate_testbench(parse_json(response, audit=attempt))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            attempt.update(status="failed", error_code="invalid_verification_bundle", error=str(exc))
            previous = (response, str(exc))
            continue
        quality = quality_gate(task["design_contract"]["contract"], document["body"], work, settings)
        attempt.update(status=quality["status"], quality=quality)
        save_json(work / "quality.json", quality)
        if quality["status"] == "not_run": break
        if quality["status"] != "passed":
            attempt.update(error_code="verification_quality_failed", error=quality["reason"])
            # No RTL exists yet; these are exclusively verifier/stub diagnostics.
            previous = (response, "独立测试质量门未通过：" + canonical(quality))
            continue
        review_messages = [{"role": "system", "content":
            "独立审查验证环境，不查看RTL。检查TB是否逐项覆盖需求和冻结契约、oracle是否独立且正确、"
            "是否存在恒失败/恒通过、采样竞争、错误延迟、遗漏顶层/配置、只验证空闲或错误的协议假设。"
            '两个常量负控通过不是充分证据。只返回JSON {"accepted":true或false,"issues":["具体问题"],"rationale":"审查依据"}。'
            "有问题必须拒绝，不得修改或放宽契约。"},
            {"role": "user", "content": canonical({"requirements": task["requirements_text"],
                "contract": task["design_contract"]["contract"], "testbench": document})}]
        review_text, review = model_call(provider, task["id"], review_messages,
                                         directory / f"review_{index:02d}", "verification_review", settings)
        attempts.append(review)
        if review_text is None: break
        try:
            decision = parse_json(review_text, audit=review)
            exact(decision, "accepted issues rationale", "验证审查")
            if decision["accepted"] is not True or decision["issues"] != []:
                raise ValueError("验证审查拒绝：" + canonical(decision))
            text(decision["rationale"], "验证审查依据")
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            review.update(status="failed", error_code="verification_review_rejected", error=str(exc))
            previous = (response, str(exc))
            continue
        review["status"] = "passed"
        envelope = {"contract_sha256": task["contract_sha256"], "testbench": document, "review": decision}
        frozen = directory / "frozen_verification.json"
        save_json(frozen, envelope)
        prepared = {**task, "verification_bundle": envelope, "verification_sha256": fingerprint(envelope),
                    "frozen_verification_path": str(frozen)}
        return prepared, {"status": "frozen", "attempts": attempts, "verification_sha256": fingerprint(envelope),
                          "frozen_verification_path": str(frozen), "method": "independent_model_context",
                          "limitations": ["model_authored_oracle_not_formal_proof", "negative_controls_not_sufficient_for_coverage"]}
    return None, {"status": attempts[-1]["status"], "attempts": attempts}


def bind_verification(task, workdir):
    """Fail closed on edits to requirements/contract/TB; never regenerate tests after RTL."""
    for key, hash_key, path_key in (("design_contract", "contract_sha256", "frozen_contract_path"),
                                   ("verification_bundle", "verification_sha256", "frozen_verification_path")):
        on_disk = json.loads(Path(task[path_key]).read_text(), object_pairs_hook=unique_object)
        if fingerprint(task[key]) != task[hash_key] or on_disk != task[key]:
            raise ValueError("frozen_artifact_mismatch")
    envelope = task["design_contract"]
    if (envelope["requirements_sha256"] != fingerprint(task["requirements_text"])
            or task["verification_bundle"]["contract_sha256"] != task["contract_sha256"]):
        raise ValueError("frozen_requirement_or_contract_mismatch")
    contract = validate_contract(envelope["contract"], envelope["language"])
    document = validate_testbench(task["verification_bundle"]["testbench"])
    workdir = Path(workdir).resolve() / "frozen-tests"
    workdir.mkdir(parents=True, exist_ok=False)
    tb = workdir / "testbench.sv"
    tb.write_text(harness(contract, document["body"]))
    expected = {f"rtlflow_tb.dut{i}": {"module": top["name"], "ports": {
        name: {"direction": port["direction"], "width": port["width"], "signed": port["signed"]} for name, port in ports.items()}}
        for i, top, _, ports in configurations(contract)}
    return {**task, "verification_bound": True, "dataset_root": str(workdir), "dialect": "2012",
            "candidate_testbench_files": [tb.name], "design_tops": [top["name"] for top in contract["tops"]],
            "testbench_tops": ["rtlflow_tb"], "dut_roots": list(expected), "expected_ports": expected,
            "public_parameters": {top["name"]: list(top["parameters"]) for top in contract["tops"]},
            "include_dirs": [], "defines": [], "runtime_files": {}, "simulation_args": [],
            "simulation_timeout_seconds": 30, "required_output": [{"regex": "RTL_CHECK_PASS", "min_count": 1}],
            "forbidden_output": [FAIL, "FATAL", "ERROR"]}
