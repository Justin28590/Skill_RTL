import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import uuid

from .design import load_design_matrix
from .languages import LANGUAGES, language_of
from .pipeline import DEFAULT_GROUP, GROUPS, run_batch, run_group_comparison, run_language_matrix
from .providers import GLMProvider, MockProvider
from .skill_tools import agent_turn_limit

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_SETTINGS = {
    "provider", "tasks", "fixture_manifest", "group", "max_repairs", "max_refactors",
    "readability_threshold", "tool_timeout_seconds", "api_timeout_seconds", "temperature",
    "max_tokens", "model", "api_key_env", "base_url_env", "thinking",
    "language", "max_agent_turns", "chisel_timeout_seconds", "api_stream",
    "max_design_repairs", "max_verification_repairs",
}


def load_settings(path):
    path = Path(path).resolve()
    settings = json.loads(path.read_text())
    if not isinstance(settings, dict) or set(settings) - ALLOWED_SETTINGS:
        raise ValueError("配置包含未知字段；密钥只能通过环境变量传入")
    settings["language"] = language_of(settings)
    settings["max_agent_turns"] = agent_turn_limit(settings)
    settings.setdefault("api_stream", True)
    settings.setdefault("api_timeout_seconds", 600)
    if type(settings["api_stream"]) is not bool:
        raise ValueError("api_stream 必须为布尔值")
    if settings.get("provider") not in ("glm", "mock"):
        raise ValueError("provider 仅支持 glm（API）/mock（离线回放）")
    if settings["provider"] == "glm":
        if settings.get("thinking", "high") not in ("low", "high", "max"):
            raise ValueError("GLM thinking 必须为 low/high/max")
    elif "thinking" in settings:
        raise ValueError("thinking 仅用于 GLM provider")
    if settings.get("group", DEFAULT_GROUP) not in GROUPS:
        raise ValueError("group 必须为 Baseline/Skill；旧 A/B/C/D 策略不再支持")
    for key in ("max_repairs", "max_refactors", "max_design_repairs", "max_verification_repairs"):
        value = settings.get(key, 2 if key == "max_repairs" else 1)
        if type(value) is not int or not 0 <= value <= 10:
            raise ValueError(f"{key} 必须为 0～10 的整数")
    for key, default in (("tool_timeout_seconds", 10), ("api_timeout_seconds", 600), ("chisel_timeout_seconds", 300)):
        value = settings.get(key, default)
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 600:
            raise ValueError(f"{key} 必须大于 0 且不超过 600 秒")
    for key, default, maximum in (("readability_threshold", 90, 100), ("temperature", 1.0, 2)):
        value = settings.get(key, default)
        if type(value) not in {int, float} or not 0 <= value <= maximum:
            raise ValueError(f"{key} 必须在 0～{maximum} 之间")
    tokens = settings.get("max_tokens")
    if tokens is not None and (type(tokens) is not int or tokens <= 0):
        raise ValueError("max_tokens 必须为正整数或 null；省略/null 表示使用服务端默认值")
    for key in ("model", "api_key_env", "base_url_env"):
        if key in settings and (not isinstance(settings[key], str) or not settings[key].strip()):
            raise ValueError(f"{key} 必须为非空字符串")
    for key in ("tasks", "fixture_manifest"):
        if key in settings:
            settings[key] = str((path.parent / settings[key]).resolve())
    if "tasks" not in settings or (settings["provider"] == "mock" and "fixture_manifest" not in settings):
        raise ValueError("必须设置 tasks；mock 模式还需要 fixture_manifest")
    return settings


def create_provider(settings):
    if settings["provider"] == "mock":
        return MockProvider(settings["fixture_manifest"])
    return GLMProvider(settings)


def planned_calls(settings, groups, task_count):
    provider_calls = model_calls = 0
    attempts = 1 + settings.get("max_repairs", 2) + settings.get("max_refactors", 1)
    preparation = 2 * (1 + settings.get("max_design_repairs", 1)) + 2 * (1 + settings.get("max_verification_repairs", 1))
    for group in groups:
        if group not in GROUPS:
            raise ValueError("group 必须为 Baseline/Skill")
        provider_calls += preparation + attempts
        model_calls += (preparation + attempts) * (agent_turn_limit(settings) if group == "Skill" else 1)
    return {
        "max_provider_calls": task_count * provider_calls,
        "max_model_calls": task_count * model_calls if settings["provider"] == "glm" else 0,
    }


def data_plan(task_matrix, settings, groups):
    by_language = {}
    for language, tasks in task_matrix.items():
        by_language[language] = {
            "language": language, "total": len(tasks), "groups": groups,
            "task_group_runs": len(tasks) * len(groups),
            **planned_calls(settings, groups, len(tasks)),
            "dataset": tasks[0]["dataset_provenance"],
            "workflow": "hardware-design-v1",
            "task_ids": [t["id"] for t in tasks], "model_calls": 0,
        }
    if len(by_language) == 1:
        return next(iter(by_language.values()))
    total = sum(item["total"] for item in by_language.values())
    task_ids = list(dict.fromkeys(t["id"] for tasks in task_matrix.values() for t in tasks))
    return {
        "languages": list(task_matrix), "total": total, "task_count": len(task_ids),
        "task_ids": task_ids, "groups": groups, "task_group_runs": total * len(groups),
        **planned_calls(settings, groups, total), "by_language": by_language, "model_calls": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="高层需求→设计/审查/冻结→独立验证准备→RTL与限轮修复；默认全部任务和两组，目标语言按清单 target_languages 选择，并非每个任务都支持三种语言",
        allow_abbrev=False,
    )
    parser.add_argument("--task", nargs="+", action="extend", metavar="ID", help="任务 ID（默认全部）")
    parser.add_argument("--group", nargs="+", action="extend", choices=GROUPS, metavar="GROUP",
                        help="组别：Baseline / Skill（默认全部）")
    parser.add_argument("--language", nargs="+", action="extend", choices=LANGUAGES, metavar="LANG",
                        help="目标语言：verilog / systemverilog / chisel（默认各任务已支持的全部语言）")
    parser.add_argument("--output", type=Path, metavar="DIR", help="结果目录（默认自动新建；不覆盖）")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/glm.json", metavar="FILE",
                        help="模型与预算配置（默认 configs/glm.json）")
    parser.add_argument("--check-data", action="store_true", help="仅检查数据和运行计划，不调用模型或构建器")
    args = parser.parse_args(argv)
    for option in ("task", "group", "language"):
        values = getattr(args, option)
        if values and len(set(values)) != len(values):
            parser.error(f"--{option} 不允许重复值")
    groups = args.group or list(GROUPS)
    languages = args.language or list(LANGUAGES)
    try:
        settings = load_settings(args.config)
        task_matrix = load_design_matrix(settings["tasks"], args.task, languages)
        plan = data_plan(task_matrix, settings, groups)
        if args.check_data:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        counts = ", ".join(f"{lang}: {len(tasks)}" for lang, tasks in task_matrix.items())
        print(f"运行计划：{plan['total']} 个任务/目标语言组合（{counts}）× {len(groups)} 组；"
              f"最多 {plan['max_provider_calls']} 次阶段生成/审查、"
              f"{plan['max_model_calls']} 次真实 HTTP 请求（Skill 工具轮次计入）。", file=sys.stderr)
        rules = (ROOT / "skills/rtl-readable/rules.md").read_text()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        output = args.output or ROOT / "results" / run_id
        print(f"结果目录：{output.resolve()}", file=sys.stderr, flush=True)
        if len(task_matrix) > 1:
            summary = run_language_matrix(task_matrix, create_provider, settings, rules, groups, output)
        else:
            language, tasks = next(iter(task_matrix.items()))
            settings = {**settings, "language": language}
            if len(groups) > 1:
                summary = run_group_comparison(tasks, create_provider, settings, rules, groups, output)
            else:
                settings["group"] = groups[0]
                summary = run_batch(tasks, create_provider(settings), settings, rules, output)
    except KeyboardInterrupt:
        print("已中断，工具进程组已终止；请检查已落盘产物。", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"配置或运行错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] == summary["total"] else 1
