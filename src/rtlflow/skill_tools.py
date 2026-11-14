"""A narrow, read-only Skill tool; never expose the repository filesystem to a model."""

import hashlib
from pathlib import Path

from .languages import language_of, select_rules

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills/rtl-readable"
MAX_DOCUMENT_BYTES = 64 * 1024
DEFAULT_AGENT_TURNS = 6
MAX_AGENT_TURNS = 12
SKILL_RELOAD_REQUEST = (
    "本轮是新的独立Skill会话，上一版响应不代表本轮已读取文档。"
    "请先调用read_skill读取SKILL.md，再读取rules.md和本阶段语言参考；"
    "必须完成本轮三份读取后再处理以下反馈并交付结果，不要直接输出修订正文。\n"
)


def agent_turn_limit(settings):
    value = settings.get("max_agent_turns", DEFAULT_AGENT_TURNS)
    if type(value) is not int or not 1 <= value <= MAX_AGENT_TURNS:
        raise ValueError(f"max_agent_turns 必须为 1～{MAX_AGENT_TURNS} 的整数")
    return value


def skill_capabilities(language, phase="implementation"):
    """Adapt the same portable Skill to each isolated workflow role."""
    language_of({"language": language})
    roles = {
        "design": "当前调用执行需求分析、设计契约或契约修订；运用Skill的设计与自检步骤，"
                  "只交付上面规定的完整设计JSON，不写RTL或TB。设计确认由外层独立审查完成，不等待用户确认。",
        "design_review": "当前调用独立审查需求与设计契约；运用Skill的契约检查规则，"
                         "仅交付上面规定的审查JSON，不改写提案、不写RTL或TB，有问题必须拒绝。",
        "verification_design": "当前调用根据需求与冻结契约设计或修订独立SystemVerilog TB；"
                               "运用Skill的独立期望值、边界、复位、握手和采样检查，"
                               "仅交付上面的body/coverage/oracle_description JSON，不生成候选RTL，不改变冻结契约。",
        "verification_review": "当前调用独立审查SystemVerilog验证环境；运用Skill的验证检查规则，"
                               "只交付上面规定的审查JSON，检查oracle、覆盖、采样与时序，有问题必须拒绝，"
                               "不得修改契约、放宽判据或生成候选RTL。",
        "implementation": "当前调用仅执行已冻结契约的RTL实现/修复/重构，不重新设计或等待用户确认，"
                          "不新建TB；最终严格按上面的完整JSON源码协议交付。",
    }
    if phase not in roles:
        raise ValueError("未知Skill调用阶段")
    return (
        "\n\n" + roles[phase]
        + "可用工具：read_skill，可按用户请求只读加载已注册的 Skill。"
        "入口为 SKILL.md；本次调用必须先读取入口，再读取 rules.md 和"
        f" references/{language}.md，三份读取完成后才提交本阶段结果。"
        "每次调用独立加载；工具只读这三份文档，规则仅返回通用部分和当前语言分支。"
        "只使用本轮显式提供的输入，不继承其他阶段的对话、工具读取记录或私有推理。"
        "阶段推进、冻结、工具验证、评分、修复预算与回退由外层控制器执行，不自行开始额外修复轮次；"
        "不得读取工程/测试或其他文件、执行命令、联网、写文件或声称已验证。"
        "通用Skill中的工程操作建议不扩大当前权限，交付格式以本阶段协议为准。"
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
