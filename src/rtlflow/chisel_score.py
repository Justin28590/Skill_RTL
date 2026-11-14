"""Dependency-free Scala/Chisel source heuristics; not a parser or a verifier."""
import re

CHISEL_SCORE_VERSION = "static-chisel-heuristic-v1"
LIMITATIONS = (
    "仅为 Scala/Chisel 源码词法启发式，不完整解析类型、参数、模式绑定或插值表达式；"
    "含嵌套引号的复杂插值可能误判。"
    "花括号深度包含类/Bundle/作用域，不等于硬件逻辑深度。"
    "不判断命名含义、注释质量、硬件语义或功能正确性，不能代替 Scala 编译、Lint、"
    "独立功能验证或人工盲评；不评价生成 RTL，不用于跨语言排名。"
)


def _mask_scala(code):
    """Mask comments/literals while preserving offsets, including nested block comments.

    Simple interpolated strings are masked in full; nested quoted expressions
    are not parsed. This is separate from the HDL policy/verification lexers.
    """
    masked = list(code)
    has_comment = False
    index = 0
    while index < len(code):
        start = index
        if code.startswith("//", index):
            end = code.find("\n", index + 2)
            index = len(code) if end < 0 else end
            has_comment |= bool(code[start + 2:index].strip())
        elif code.startswith("/*", index):
            index += 2
            depth = 1
            while index < len(code) and depth:
                if code.startswith("/*", index):
                    depth += 1
                    index += 2
                elif code.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            body = code[start + 2:index - 2] if depth == 0 else code[start + 2:index]
            has_comment |= bool(re.sub(r"/\*|\*/", "", body).strip("* \t\r\n"))
        elif code.startswith('"""', index):
            end = code.find('"""', index + 3)
            index = len(code) if end < 0 else end + 3
        elif code[index] == '"':
            index += 1
            while index < len(code):
                if code[index] == "\\":
                    index = min(len(code), index + 2)
                elif code[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
        elif code[index] == "'" and (char := re.match(r"'(?:\\[^\n]|[^'\\\n])'", code[index:index + 4])):
            index += len(char[0])
        else:
            index += 1
            continue
        masked[start:index] = ['\n' if c == '\n' else ' ' for c in code[start:index]]
    return ''.join(masked), has_comment


def _short_names(clean):
    identifier = r"[A-Za-z_][\w$]*"
    declarations = re.findall(rf"\b(?:val|var|def|class|object|trait)\s+({identifier})", clean)
    # Common Chisel Enum list patterns and simple tuple bindings, not arbitrary Scala patterns.
    for pattern in (rf"\b(?:val|var)\s+((?:{identifier}\s*::\s*)+Nil)\b",
                    rf"\b(?:val|var)\s*\(\s*({identifier}(?:\s*,\s*{identifier})+)\s*\)"):
        for binding in re.findall(pattern, clean):
            declarations.extend(re.findall(identifier, binding))
    return sorted({name for name in declarations if len(name) == 1 and name not in {'i', 'j', 'k', '_'}})


def _structure_and_complexity(clean):
    crowded, nested_mux = set(), set()
    stack = []
    brace_depth = max_depth = mux_depth = for_depth = 0
    previous = ''
    line = 1
    offset = 0
    statement_ends = []
    line_start = 0
    for text in clean.splitlines(keepends=True):
        statement_ends.append(line_start + len(text.rstrip('\r\n').rstrip(' \t\r;})]')))
        line_start += len(text)
    for match in re.finditer(r"[A-Za-z_][\w$]*|[^\s]", clean):
        line += clean.count('\n', offset, match.start())
        offset = match.end()
        token = match[0]
        if token in {'(', '{', '['}:
            is_mux = token == '(' and previous == 'Mux'
            is_for = token in {'(', '{'} and previous == 'for'
            stack.append((token, is_mux, is_for))
            mux_depth += is_mux
            for_depth += is_for
            if is_mux and mux_depth > 1:
                nested_mux.add(line)
            if token == '{':
                brace_depth += 1
                max_depth = max(max_depth, brace_depth)
        elif token in {')', '}', ']'}:
            opener = {')': '(', '}': '{', ']': '['}[token]
            if stack and stack[-1][0] == opener:
                _, is_mux, is_for = stack.pop()
                mux_depth -= is_mux
                for_depth -= is_for
            if token == '}':
                brace_depth = max(0, brace_depth - 1)
        elif token == ';' and not for_depth:
            # A trailing terminator isn't a second statement; for-enumerator separators are exempt.
            if match.end() < statement_ends[line - 1]:
                crowded.add(line)
        previous = token
    structure = [f"第 {number} 行包含分号分隔的多个语句" for number in sorted(crowded)]
    complexity = ([f"花括号嵌套深度为 {max_depth}，超过 3（含类/Bundle 作用域）"] if max_depth > 3 else [])
    complexity += [f"第 {number} 行嵌套 Mux 调用" for number in sorted(nested_mux)]
    return structure, complexity


def score_chisel_readability(code):
    clean, has_comment = _mask_scala(code)
    if not clean.strip():
        return {"status": "not_run", "language": "chisel", "method": CHISEL_SCORE_VERSION,
                "score": None, "reason": "no_scala_code", "limitations": LIMITATIONS}
    dimensions = {}

    def dimension(name, weight, issues, penalty):
        dimensions[name] = {"score": max(0, weight - penalty * len(issues)),
                            "weight": weight, "issues": issues}

    dimension("naming", 25, [f"单字符声明名：{name}" for name in _short_names(clean)], 3)
    structure, complexity = _structure_and_complexity(clean)
    dimension("structure", 25, structure, 3)
    dimension("complexity", 20, complexity, 5)
    dimension("comments", 15, [] if has_comment else ["缺少设计意图注释（仅检查非空注释存在性）"], 10)
    style = []
    for number, line in enumerate(code.splitlines(), 1):
        if '\t' in line:
            style.append(f"第 {number} 行使用制表符")
        if line.rstrip() != line:
            style.append(f"第 {number} 行存在尾随空格")
        if len(line) > 100:
            style.append(f"第 {number} 行超过 100 字符")
    dimension("style", 15, style, 1)
    return {"status": "passed", "language": "chisel", "method": CHISEL_SCORE_VERSION,
            "score": sum(item["score"] for item in dimensions.values()),
            "dimensions": dimensions, "limitations": LIMITATIONS}
