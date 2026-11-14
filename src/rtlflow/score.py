"""Transparent smoke-test heuristics, not semantic readability evaluation."""

import re

from .verify import strip_comments

SCORE_VERSION = "static-heuristic-v1"


def score_readability(code, language="verilog"):
    from .languages import language_of

    language_of({"language": language})
    if language == "chisel":
        from .chisel_score import score_chisel_readability
        return score_chisel_readability(code)
    lines = code.splitlines()
    clean = strip_comments(code)
    dimensions = {}

    def dimension(name, weight, issues, penalty):
        dimensions[name] = {
            "score": max(0, weight - penalty * len(issues)),
            "weight": weight,
            "issues": issues,
        }

    types = "wire|reg|integer" + ("|logic|bit|int" if language == "systemverilog" else "")
    declarations = re.findall(
        rf"\b(?:input|output|inout|localparam|parameter|{types})\s+"
        rf"(?:(?:{types}|signed|unsigned)\s+)*(?:\[[^\]]+\]\s*)?([A-Za-z_]\w*)",
        clean,
    )
    short_names = sorted({name for name in declarations if len(name) == 1 and name not in {"i", "j", "k"}})
    dimension("naming", 25, [f"单字符声明名：{name}" for name in short_names], 3)
    crowded = [f"第 {i} 行包含多个语句" for i, line in enumerate(clean.splitlines(), 1)
               if line.count(";") > 1 and not re.search(r"\bfor\s*\(", line)]
    dimension("structure", 25, crowded, 3)
    depth = max_depth = 0
    for token in re.findall(r"\b(?:begin|end)\b", clean):
        depth = depth + 1 if token == "begin" else max(0, depth - 1)
        max_depth = max(depth, max_depth)
    complexity = ([f"begin/end 嵌套深度为 {max_depth}，超过 3"] if max_depth > 3 else [])
    complexity += [f"第 {i} 行嵌套三元表达式" for i, line in enumerate(clean.splitlines(), 1)
                   if line.count("?") > 1]
    dimension("complexity", 20, complexity, 5)
    has_comment = bool(re.search(r"//[^\n]+|/\*.+?\*/", code, re.DOTALL))
    dimension("comments", 15, [] if has_comment else ["缺少设计意图注释（仅检查存在性）"], 10)
    style = []
    for i, line in enumerate(lines, 1):
        if "\t" in line:
            style.append(f"第 {i} 行使用制表符")
        if line.rstrip() != line:
            style.append(f"第 {i} 行存在尾随空格")
        if len(line) > 100:
            style.append(f"第 {i} 行超过 100 字符")
    dimension("style", 15, style, 1)
    return {
        "status": "passed", "language": language,
        "method": "static-sv-heuristic-v1" if language == "systemverilog" else SCORE_VERSION,
        "score": sum(item["score"] for item in dimensions.values()),
        "dimensions": dimensions,
        "limitations": "仅为正则启发式，不判断命名含义、注释质量、锁存器或功能正确性；不能代替 Lint、独立模型评分和人工盲评；不完整解析枚举/struct/数组，不用于跨语言排名。",
    }
