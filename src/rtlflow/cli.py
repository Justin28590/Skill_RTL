import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import uuid

from .project import load_projects as load_tasks
from .languages import LANGUAGES, language_of
from .pipeline import DEFAULT_GROUP, GROUPS, run_batch, run_group_comparison
from .providers import GLMProvider, MockProvider
from .skill_tools import agent_turn_limit

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_SETTINGS = {
    "provider", "tasks", "fixture_manifest", "group", "max_repairs", "max_refactors",
    "readability_threshold", "tool_timeout_seconds", "api_timeout_seconds", "temperature",
    "max_tokens", "model", "api_key_env", "base_url_env", "thinking",
    "language", "max_agent_turns", "chisel_timeout_seconds",
}


def load_settings(path):
    path = Path(path).resolve()
    settings = json.loads(path.read_text())
    if not isinstance(settings, dict) or set(settings) - ALLOWED_SETTINGS:
        raise ValueError("配置包含未知字段；密钥只能通过环境变量传入")
    settings["language"] = language_of(settings)
    settings["max_agent_turns"] = agent_turn_limit(settings)
    if settings.get("provider") not in ("glm", "mock"):
        raise ValueError("provider 仅支持 glm（API）/mock（离线回放）")
    if settings["provider"] == "glm":
        if settings.get("thinking", "high") not in ("low", "high", "max"):
            raise ValueError("GLM thinking 必须为 low/high/max")
    elif "thinking" in settings:
        raise ValueError("thinking 仅用于 GLM provider")
    if settings.get("group", DEFAULT_GROUP) not in GROUPS:
        raise ValueError("group 必须为 Baseline/Skill；旧 A/B/C/D 策略不再支持")
    for key in ("max_repairs", "max_refactors"):
        value = settings.get(key, 2 if key == "max_repairs" else 1)
        if type(value) is not int or not 0 <= value <= 10:
            raise ValueError(f"{key} 必须为 0～10 的整数")
    for key, default in (("tool_timeout_seconds", 10), ("api_timeout_seconds", 120), ("chisel_timeout_seconds", 300)):
        value = settings.get(key, default)
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 600:
            raise ValueError(f"{key} 必须大于 0 且不超过 600 秒")
    for key, default, maximum in (("readability_threshold", 90, 100), ("temperature", 1.0, 2)):
        value = settings.get(key, default)
        if type(value) not in {int, float} or not 0 <= value <= maximum:
            raise ValueError(f"{key} 必须在 0～{maximum} 之间")
    tokens = settings.get("max_tokens", 8192)
    if type(tokens) is not int or tokens <= 0:
        raise ValueError("max_tokens 必须为正整数")
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
    for group in groups:
        if group not in GROUPS:
            raise ValueError("group 必须为 Baseline/Skill")
        provider_calls += attempts
        model_calls += attempts * (agent_turn_limit(settings) if group == "Skill" else 1)
    return {
        "max_provider_calls": task_count * provider_calls,
        "max_model_calls": task_count * model_calls if settings["provider"] == "glm" else 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="完整 RTL 项目多文件生成、验证和限轮修复；默认运行等预算 Baseline/Skill 两组")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/glm.json",
                        help="默认 configs/glm.json（按目标语言选择完整项目，GLM-5.3 high）；--check-data 不调用模型")
    parser.add_argument("--task", action="append", help="只运行指定任务，可重复传入")
    strategy = parser.add_mutually_exclusive_group()
    strategy.add_argument("--group", choices=GROUPS, help="只运行指定单组；不指定组别时默认运行两组")
    strategy.add_argument("--groups", nargs="+", choices=GROUPS,
                          help="每个任务独立运行指定组，如 --groups Baseline Skill；不能重复")
    strategy.add_argument("--all-groups", dest="groups", action="store_const", const=list(GROUPS),
                          help="显式选择默认行为：每个任务独立运行 Baseline/Skill 两组")
    parser.add_argument("--output", type=Path, help="新建结果目录；已有目录不会覆盖")
    parser.add_argument("--language", choices=LANGUAGES, help="覆盖配置语言；未指定默认为 verilog")
    parser.add_argument("--check-data", action="store_true", help="只校验数据、语言与哈希；不调用模型或构建器")
    args = parser.parse_args(argv)
    if args.group is None and args.groups is None:
        args.groups = list(GROUPS)
    if args.groups and len(set(args.groups)) != len(args.groups):
        parser.error("--groups 不允许重复组名")
    try:
        settings = load_settings(args.config)
        if args.group:
            settings["group"] = args.group
        if args.language:
            settings["language"] = args.language
        tasks = load_tasks(settings["tasks"], args.task, language=settings["language"])
        groups = args.groups or [settings.get("group", DEFAULT_GROUP)]
        budget = planned_calls(settings, groups, len(tasks))
        if args.check_data:
            print(json.dumps({"language": settings["language"], "total": len(tasks),
                              "groups": groups, "task_group_runs": len(tasks) * len(groups), **budget,
                              "dataset": tasks[0]["dataset_provenance"],
                              "selected_source_languages": {lang: sum(t.get("language", "verilog") == lang for t in tasks) for lang in LANGUAGES},
                              "task_ids": [t["id"] for t in tasks], "model_calls": 0},
                             ensure_ascii=False, indent=2))
            return 0
        print(f"运行计划：{len(tasks)} 案例 × {len(groups)} 组；"
              f"最多 {budget['max_provider_calls']} 次候选生成、"
              f"{budget['max_model_calls']} 次真实 HTTP 请求（Skill 工具轮次计入）。", file=sys.stderr)
        rules = (ROOT / "skills/rtl-readable/rules.md").read_text()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        output = args.output or ROOT / "results" / run_id
        if args.groups:
            summary = run_group_comparison(tasks, create_provider, settings, rules, args.groups, output)
        else:
            summary = run_batch(tasks, create_provider(settings), settings, rules, output)
    except KeyboardInterrupt:
        print("已中断，工具进程组已终止；请检查已落盘产物。", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"配置或运行错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] == summary["total"] else 1
