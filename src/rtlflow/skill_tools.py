"""A narrow, read-only Skill tool; never expose the repository filesystem to a model."""

import hashlib
from pathlib import Path

from .languages import language_of, select_rules

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills/rtl-readable"
MAX_DOCUMENT_BYTES = 64 * 1024
DEFAULT_AGENT_TURNS = 6
MAX_AGENT_TURNS = 12


def agent_turn_limit(settings):
    value = settings.get("max_agent_turns", DEFAULT_AGENT_TURNS)
    if type(value) is not int or not 1 <= value <= MAX_AGENT_TURNS:
        raise ValueError(f"max_agent_turns 必须为 1～{MAX_AGENT_TURNS} 的整数")
    return value


def skill_capabilities(language):
    """Runtime capabilities, not a task-specific request to invoke a named Skill."""
    language_of({"language": language})
    return (
        "\n\n可用工具：read_skill，可按用户请求只读加载已注册的 Skill。"
        "Skill 入口为 SKILL.md；使用 Skill 时需按其要求读取 rules.md 和"
        f" references/{language}.md，完成读取后再返回最终源码。"
        "工具只读这些公开 Skill 文档；规则工具只返回通用规则和当前语言分支。"
        "独立验证、评分、修复预算与回退由外层控制器执行；不要自行执行命令、"
        "读取其他文件或声称已经验证。Skill 中面向人工操作的仓库命令/链接不是工具权限。"
    )


class SkillReader:
    """Fresh per generation attempt. Explicit names, not arbitrary file paths."""

    def __init__(self, language):
        self.language = language_of({"language": language})
        self.paths = ("SKILL.md", "rules.md", f"references/{self.language}.md")
        self.documents = {}

    @property
    def available_paths(self):
        # Discovery is progressive: the initial tool schema exposes just the entry point.
        return list(self.paths if "SKILL.md" in self.documents else ("SKILL.md",))

    @property
    def complete(self):
        return all(path in self.documents for path in self.paths)

    def definition(self):
        return {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "只读加载 rtl-readable Skill 文档。先读 SKILL.md，再读规则及目标语言参考；不是任意文件读取器。",
                "parameters": {
                    "type": "object", "properties": {
                        "path": {"type": "string", "enum": self.available_paths},
                    },
                    "required": ["path"], "additionalProperties": False,
                },
            },
        }

    def read(self, path):
        if not isinstance(path, str) or path not in self.available_paths:
            raise ValueError("Skill 文档不在当前允许列表中")
        source = SKILL_ROOT / path
        # Reject symlinks, including symlinked parent directories, before opening.
        try:
            safe = source.resolve() == source.absolute() and source.is_file()
        except RuntimeError:  # A symlink loop must fail like any other forbidden path.
            safe = False
        if not safe:
            raise ValueError("Skill 文档缺失或为符号链接")
        with source.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError("Skill 文档超过读取上限")
        text = raw.decode("utf-8")
        if path == "rules.md":
            text = select_rules(text, self.language)
        evidence = {
            "path": path, "source_sha256": hashlib.sha256(raw).hexdigest(),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "scope": "common_and_target_language" if path == "rules.md" else "full_document",
        }
        self.documents[path] = evidence
        return {**evidence, "content": text}
