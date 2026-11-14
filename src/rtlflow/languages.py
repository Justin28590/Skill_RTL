"""Explicit source-language contracts shared by CLI, prompts and artifacts."""

LANGUAGES = ("verilog", "systemverilog", "chisel")
EXTENSIONS = {"verilog": ".v", "systemverilog": ".sv", "chisel": ".scala"}
LABELS = {"verilog": "Verilog", "systemverilog": "SystemVerilog", "chisel": "Chisel"}


def language_of(settings):
    language = settings.get("language", "verilog")
    if language not in LANGUAGES:
        raise ValueError("language 必须为 verilog/systemverilog/chisel")
    return language


def select_rules(rules, language):
    """Send common rules plus only the selected branch; preserve custom rule text."""
    if "## 通用规则" not in rules or "## Verilog 分支" not in rules:
        return rules
    common = rules.split("## 通用规则", 1)[1].split("## Verilog 分支", 1)[0]
    branch = rules.split(f"## {LABELS[language]} 分支", 1)[1].split("\n## ", 1)[0]
    return "## 通用规则" + common + f"## {LABELS[language]} 分支" + branch
