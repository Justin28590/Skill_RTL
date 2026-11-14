#!/usr/bin/env bash
# Source this file in Bash; do not execute it as a child process.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo '请使用 source scripts/env.sh 激活当前终端的工具路径。' >&2
    exit 1
fi
_RTL_TOOLS_BIN="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/.tools/bin"
if [[ ! -x "$_RTL_TOOLS_BIN/verilator" && ! -x "$_RTL_TOOLS_BIN/verible-verilog-lint" && ! -x "$_RTL_TOOLS_BIN/java" && ! -x "$_RTL_TOOLS_BIN/firtool" ]]; then
    echo '本地工具尚未就绪；按需执行 bash scripts/install_tools.sh 或 bash scripts/install_chisel_tools.sh。' >&2
    unset _RTL_TOOLS_BIN
    return 1
fi
case ":${PATH:-}:" in
    *":$_RTL_TOOLS_BIN:"*) ;;
    *) export PATH="$_RTL_TOOLS_BIN:${PATH:-}" ;;
esac
unset _RTL_TOOLS_BIN
