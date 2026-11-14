#!/usr/bin/env bash
# Relocated Ubuntu Verilator wrapper; only this process receives VERILATOR_ROOT.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/.." && pwd)"
export VERILATOR_ROOT="$ROOT/.tools/verilator/usr/share/verilator"
exec "$ROOT/.tools/verilator/usr/bin/verilator" "$@"
