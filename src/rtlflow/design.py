"""Task-independent requirements -> design -> independent review -> freeze protocol."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from .project_dataset import save_json, unique_object
from .providers import GenerationError
from .skill_tools import SKILL_RELOAD_REQUEST, SkillReader, skill_capabilities

SCHEMA = "hardware-design-v1"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
RESERVED = set("module endmodule input output inout wire reg logic integer parameter localparam begin end always initial assign generate endgenerate if else for case endcase function endfunction task endtask posedge negedge signed unsigned real time bit int automatic static default do while return interface program package class import export clocking property sequence typedef struct union enum genvar force release bind config design cell instance use liblist library include event wait repeat forever fork join disable deassign supply0 supply1 tri wor wand macromodule primitive endprimitive table endtable specify endspecify buf not and nand or nor xor xnor tran rtran cmos rcmos nmos pmos rnmos rpmos pulldown pullup".split())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value):
    if (not isinstance(value, str) or not IDENTIFIER.fullmatch(value)
            or value in RESERVED or value.startswith("rtlflow")):
        raise ValueError("名称必须为非保留 HDL 标识符（最多64字符，rtlflow前缀保留）")
    return value


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError(label + " 字段必须为：" + keys)


def text(value, label, maximum=16000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + " 必须为非空且有界的文本")


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} 必须为 {low}..{high} 的整数")


def width(value, parameters):
    """Bounded arithmetic, not eval or executable model code."""
    if type(value) is int:
        integer(value, 1, 1_000_000, "端口位宽")
        return value
    text(value, "位宽表达式", 128)
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            result = node.value
        elif isinstance(node, ast.Name) and node.id in parameters:
            result = parameters[node.id]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): result = a + b
            elif isinstance(node.op, ast.Sub): result = a - b
            elif isinstance(node.op, ast.Mult): result = a * b
            else:
                if b <= 0: raise ValueError("位宽表达式除数必须为正")
                result = a // b
        else:
            raise ValueError("位宽仅允许参数、整数、括号、+ - * //")
        if abs(result) > 10_000_000:
            raise ValueError("位宽表达式超出上限")
        return result
    try:
        result = visit(ast.parse(value, mode="eval").body)
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("无效位宽表达式") from exc
    integer(result, 1, 1_000_000, "端口位宽")
    return result


def load_design_matrix(path, selected, languages):
    path = Path(path).resolve()
    document = json.loads(path.read_text(), object_pairs_hook=unique_object)
    exact(document, "schema_version dataset split tasks", "需求清单")
    if document["schema_version"] != SCHEMA or document["split"] != "pilot":
        raise ValueError("主流程需要 hardware-design-v1 pilot 高层需求清单；不接受旧固定接口任务")
    text(document["dataset"], "dataset")
    if not isinstance(document["tasks"], list) or not document["tasks"]:
        raise ValueError("需求任务不能为空")
    tasks = {}
    for item in document["tasks"]:
        exact(item, "id requirements_text target_languages", "需求任务")
        key = identifier(item["id"])
        if key in tasks:
            raise ValueError("重复任务")
        text(item["requirements_text"], "高层需求")
        targets = item["target_languages"]
        if (not isinstance(targets, list) or not targets or any(not isinstance(v, str) for v in targets)
                or len(set(targets)) != len(targets) or set(targets) - {"verilog", "systemverilog", "chisel"}):
            raise ValueError("无效 target_languages")
        tasks[key] = {**item, "workflow": SCHEMA, "project": True,
                      "dataset_provenance": {"dataset": document["dataset"], "split": "pilot",
                          "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "source_id": key, "quality_status": "requirements_pilot"}}
    wanted = selected or list(tasks)
    if set(wanted) - set(tasks):
        raise ValueError("未知需求任务 ID：" + ", ".join(sorted(set(wanted) - set(tasks))))
    if not languages or set(languages) - {"verilog", "systemverilog", "chisel"}:
        raise ValueError("未知或空目标语言")
    matrix = {lang: [{**tasks[k]} for k in wanted if lang in tasks[k]["target_languages"]] for lang in languages}
    matrix = {lang: items for lang, items in matrix.items() if items}
    covered = {t["id"] for items in matrix.values() for t in items}
    if selected and set(wanted) - covered:
        raise ValueError("需求任务不支持所选目标语言：" + ", ".join(sorted(set(wanted) - covered)))
    if not matrix:
        raise ValueError("没有支持所选目标语言的需求任务")
    return matrix


def validate_contract(contract, language):
    exact(contract, "schema_version description tops configurations chisel_tops", "设计契约")
    if type(contract["schema_version"]) is not int or contract["schema_version"] != 1:
        raise ValueError("schema_version 必须为1")
    text(contract["description"], "设计说明")
    tops = contract["tops"]
    if not isinstance(tops, list) or not 1 <= len(tops) <= 16:
        raise ValueError("需要1..16个顶层")
    names = set()
    for top in tops:
        exact(top, "name parameters ports timing", "顶层")
        name = identifier(top["name"])
        if name in names: raise ValueError("重复顶层")
        names.add(name)
        text(top["timing"], "时钟/复位/握手/延迟/吞吐/边界时序说明")
        parameters = top["parameters"]
        if not isinstance(parameters, dict) or len(parameters) > 128:
            raise ValueError("参数必须为有界对象")
        for key, value in parameters.items():
            identifier(key)
            integer(value, 0, 2**32-1, "参数默认值")
        ports = top["ports"]
        if not isinstance(ports, dict) or not 1 <= len(ports) <= 512:
            raise ValueError("需要1..512个端口")
        for key, port in ports.items():
            identifier(key)
            exact(port, "direction width signed description", "端口")
            if key in parameters or port["direction"] not in ("input", "output", "inout") or type(port["signed"]) is not bool:
                raise ValueError("无效端口方向/符号性/名称冲突")
            width(port["width"], parameters)
            text(port["description"], "端口语义")
        if not any(p["direction"] in ("output", "inout") for p in ports.values()):
            raise ValueError("顶层缺少可观测输出")
    configs = contract["configurations"]
    if not isinstance(configs, list) or not 1 <= len(configs) <= 32:
        raise ValueError("需要1..32个验证配置，每个顶层必须包括默认配置")
    defaults = set()
    total_bits = 0
    issues = []
    if language != "chisel" and contract["chisel_tops"] != []:
        issues.append(f"目标语言为{language}，chisel_tops必须为[]；不得使用Scala构造配置")
    by_name = {top["name"]: top for top in tops}
    for index, config in enumerate(configs):
        exact(config, "top parameters", "验证配置")
        if not isinstance(config["top"], str) or config["top"] not in names or not isinstance(config["parameters"], dict):
            raise ValueError("未知验证顶层/参数")
        top = by_name[config["top"]]
        unknown = set(config["parameters"]) - set(top["parameters"])
        if unknown:
            issues.append(f"configurations[{index}] ({top['name']}) 包含未知参数 {sorted(unknown)}；"
                          f"该顶层parameters仅声明 {sorted(top['parameters'])}。"
                          "覆写参数必须先在对应顶层声明整数默认值，不得删除需求要求的代表配置")
            continue
        for value in config["parameters"].values(): integer(value, 0, 2**32-1, "配置参数")
        if not config["parameters"]: defaults.add(top["name"])
        total_bits += sum(width(port["width"], {**top["parameters"], **config["parameters"]})
                          for port in top["ports"].values())
        if total_bits > 8_000_000:
            raise ValueError("验证配置端口总位宽超出资源上限")
    if defaults != names:
        issues.append(f"每个顶层需要不覆写参数的默认配置：缺少 {sorted(names - defaults)} 的parameters={{}}配置")
    if language == "chisel":
        from .chisel import validate_chisel_config
        if not isinstance(contract["chisel_tops"], list) or any(not isinstance(t, dict) for t in contract["chisel_tops"]):
            raise ValueError("无效Chisel构造配置")
        validate_chisel_config(contract["chisel_tops"], list(names))
        if any(top["parameters"] for top in tops) or any(c["parameters"] for c in configs):
            issues.append("Chisel 使用固定构造配置，不覆写生成RTL参数")
    if issues:
        raise ValueError("设计契约不一致：\n- " + "\n- ".join(issues))
    return contract


def parse_json(text_value, *, audit=None):
    """Decode one complete JSON object; unwrap only a whole-response JSON fence.

    Never extract a JSON substring, repair fields, or accept partial output. Raw
    responses remain on disk; callers record envelope normalization separately.
    """
    if not isinstance(text_value, str):
        raise ValueError("响应必须为JSON文本")
    if len(text_value.encode()) > 2_000_000:
        raise ValueError("响应过大")
    value = text_value.strip()
    fenced = re.fullmatch(r"```json[ \t]*\r?\n(.*?)\r?\n```", value, flags=re.DOTALL)
    if audit is not None:
        audit["json_wrapper_removed"] = fenced is not None
    if fenced:
        value = fenced[1]
    def reject_constant(value):
        raise ValueError("JSON不允许NaN或Infinity")
    try:
        document = json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"无效JSON（第{exc.lineno}行第{exc.colno}列）：仅返回一个完整JSON对象，"
                         "不要附加解释、多个代码块或省略内容") from exc
    if not isinstance(document, dict):
        raise ValueError("响应必须为一个JSON对象")
    return document


def design_messages(task, language):
    example = {"schema_version": 1, "description": "架构、子模块职责、算法、实现权衡",
        "tops": [{"name": "Compute", "parameters": {"WIDTH": 8}, "ports": {
            "data_in": {"direction": "input", "width": "WIDTH", "signed": False, "description": "输入语义"},
            "data_out": {"direction": "output", "width": "WIDTH", "signed": False, "description": "输出语义"}},
            "timing": "明确每个时钟域采样沿、复位极性/同步性/值/取消行为、输入接受条件、输出有效/保持、延迟和吞吐、非法输入处理；组合模块明确无时钟"}],
        "configurations": [{"top": "Compute", "parameters": {}}], "chisel_tops": []}
    if language == "chisel":
        example["tops"][0]["parameters"] = {}
        for port in example["tops"][0]["ports"].values():
            port["width"] = 8
        example["chisel_tops"] = [{"module": "Compute", "class": "example.Compute", "args": [8]}]
        language_rules = (
            "Chisel固定Scala2.13.12/Chisel6.5.0/firtool1.62.0。"
            "chisel_tops每项为module（生成顶层）、class（全限定类名）、args（正整数或{uint_width:位宽}数组）。"
            "所有tops.parameters和configurations.parameters必须为{}，端口使用实际展开RTL名称和具体位宽。"
            "需要多个代表尺寸时，以不同顶层名和构造配置展开，并逐一列入tops/configurations；不覆写生成RTL参数。")
    else:
        if language not in {"verilog", "systemverilog"}:
            raise ValueError("未知目标语言")
        example["configurations"].append({"top": "Compute", "parameters": {"WIDTH": 4}})
        language_rules = (
            f"本任务仅使用{language}，chisel_tops必须为[]，不要给出Scala类或构造配置。"
            "tops[].parameters声明参数名及0..2^32-1整数默认值。"
            "configurations[].parameters只能覆写对应顶层已经声明的参数；参数名必须完全一致。"
            "无参数顶层的所有配置只能使用parameters={}。有参数设计必须保留需求要求的代表配置。")
    return [{"role": "system", "content":
        f"你是{language}硬件设计工程师。先从高层需求完成设计说明与接口/时序契约，不写RTL或TB。"
        "接口名称、参数、架构、握手和延迟由你设计，不复制旧实现。不得删减算法、外部标准或需求。"
        "契约必须无歧义、可实现、可独立验证；每个顶层需要实际子模块。"
        "tops仅列对外公开的独立入口，不是所有模块的清单；内部子模块的职责写入description，不为内部叶子模块另建tops/configurations。"
        "仅返回一个完整JSON对象，不要Markdown代码围栏、前后解释或省略内容。结构示例不是固定设计：\n"
        + canonical(example) + "\nports支持input/output/inout及packed位宽；位宽仅允许整数或参数、+ - * //括号表达式。"
        "每个顶层必须有parameters={}的默认验证配置。" + language_rules},
        {"role": "user", "content": "目标语言：" + language + "\n项目：" + task["id"]
            + "\n高层需求：\n" + task["requirements_text"]
            + "\n交付前自检：目标语言一致、参数先声明再覆写、代表配置齐全；只返回完整JSON对象。"}]


def model_call(provider, task_id, messages, directory, phase, settings):
    group = settings.get("group", "Baseline")
    if group not in {"Baseline", "Skill"}:
        raise ValueError("group 必须为 Baseline/Skill")
    # TBs are SystemVerilog even when the DUT is Verilog or Chisel. Each role
    # gets its own reader and conversation; only public Skill documents recur.
    skill_language = ("systemverilog" if phase in {"verification_design", "verification_review"}
                      else settings.get("language", "verilog"))
    reader = None
    if group == "Skill":
        messages = [dict(message) for message in messages]
        messages[0]["content"] += skill_capabilities(skill_language, phase)
        messages[1]["content"] = "请调用 rtl-readable Skill，完成本阶段任务。\n" + messages[1]["content"]
        if len(messages) > 2 and messages[-1]["role"] == "user":
            messages[-1]["content"] = SKILL_RELOAD_REQUEST + messages[-1]["content"]
        reader = SkillReader(skill_language)
    directory.mkdir()
    save_json(directory / "prompt.json", messages)
    attempt = {"phase": phase, "prompt_path": str(directory / "prompt.json"), "status": "not_run",
               "skill_requested": group == "Skill", "skill_language": skill_language if reader else None}
    start = time.monotonic()
    print(f"[{task_id}] {phase}：生成/审查（{group}）", file=sys.stderr, flush=True)
    try:
        response = provider.generate(task_id, messages, skill=reader, trace_dir=directory)
        attempt.update(usage=response.usage, generation_metadata=response.metadata)
        (directory / "response.txt").write_text(response.text, errors="backslashreplace")
        attempt["response_path"] = str(directory / "response.txt")
        return response.text, attempt
    except GenerationError as exc:
        attempt.update(error=str(exc), error_code=exc.code, generation_metadata=exc.metadata,
                       usage=exc.metadata.get("usage", {}))
        return None, attempt
    finally:
        attempt["generation_seconds"] = round(time.monotonic() - start, 4)


def run_design(task, provider, settings, directory):
    """Fresh review context sees requirements + proposal only, never design dialogue/RTL/TB."""
    language = settings.get("language", "verilog")
    directory = Path(directory) / "design"
    directory.mkdir()
    base = design_messages(task, language)
    attempts, previous = [], None
    for index in range(1 + settings.get("max_design_repairs", 1)):
        messages = list(base)
        if previous:
            messages += [{"role": "assistant", "content": previous[0]},
                         {"role": "user", "content": f"契约未冻结，目标语言仍为{language}。"
                          "请一次修正以下问题并自检全部字段；不要仅修格式、删减需求或代表配置。"
                          "返回完整设计JSON对象，不带Markdown或解释：\n" + previous[1]}]
        response, attempt = model_call(provider, task["id"], messages, directory / f"proposal_{index:02d}", "design", settings)
        attempts.append(attempt)
        if response is None: break
        try:
            contract = validate_contract(parse_json(response, audit=attempt), language)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            attempt.update(status="failed", error=str(exc), error_code="invalid_design_contract")
            previous = (response, str(exc))
            continue
        attempt["status"] = "passed"
        review_messages = [{"role": "system", "content":
            "独立审查硬件设计契约，不编写RTL。逐项核对需求是否完整、算法/边界语义、接口参数、跨时钟域、复位、"
            "延迟/吞吐与握手是否明确且自洽、可实现和可独立验证。不能为降低测试难度删需求。"
            '仅返回JSON：{"accepted":true或false,"issues":["具体问题"],"rationale":"逐项审查依据"}。'
            "有歧义或遗漏必须拒绝；accepted=true要求issues为空。"},
            {"role": "user", "content": canonical({"requirements": task["requirements_text"], "language": language,
                                                       "proposal": contract})}]
        review_text, review = model_call(provider, task["id"], review_messages, directory / f"review_{index:02d}", "design_review", settings)
        attempts.append(review)
        if review_text is None: break
        try:
            decision = parse_json(review_text, audit=review)
            exact(decision, "accepted issues rationale", "独立审查")
            if type(decision["accepted"]) is not bool or not isinstance(decision["issues"], list):
                raise ValueError("无效审查决定")
            for issue in decision["issues"]: text(issue, "审查问题")
            text(decision["rationale"], "审查依据")
            if not decision["accepted"] or decision["issues"]:
                raise ValueError("独立审查未通过：" + canonical(decision))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            review.update(status="failed", error=str(exc), error_code="design_review_rejected")
            previous = (response, str(exc))
            continue
        review["status"] = "passed"
        envelope = {"schema_version": 1, "requirements_sha256": fingerprint(task["requirements_text"]),
                    "language": language, "contract": contract, "review": decision}
        frozen = directory / "frozen_contract.json"
        save_json(frozen, envelope)
        (directory / "design.md").write_text(contract["description"] + "\n")
        prepared = {**task, "design_tops": [t["name"] for t in contract["tops"]],
                    "chisel_tops": contract["chisel_tops"], "design_contract": envelope,
                    "frozen_contract_path": str(frozen), "contract_sha256": fingerprint(envelope),
                    "contract_text": task["requirements_text"] + "\n已审查冻结的设计契约（修复不得改变）：\n" + canonical(contract)}
        return prepared, {"status": "frozen", "attempts": attempts, "contract_sha256": fingerprint(envelope),
                          "frozen_contract_path": str(frozen), "review_method": "independent_model_context",
                          "human_approved": False}
    return None, {"status": attempts[-1]["status"], "attempts": attempts, "contract_sha256": None,
                  "frozen_contract_path": None}
