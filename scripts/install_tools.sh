#!/usr/bin/env bash
# Install pinned lint tools locally. Tested on Ubuntu 22.04, Linux x86_64.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/.tools"
DOWNLOADS="$TOOLS/downloads"

if [[ "$(uname -sm)" != "Linux x86_64" ]]; then
    echo '此安装脚本仅支持 Linux x86_64（已验证 Ubuntu 22.04）。' >&2
    exit 1
fi
for tool in python3 curl sha256sum dpkg-deb tar perl iverilog vvp; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "缺少基础工具：$tool。Ubuntu 可先安装 python3 curl perl iverilog。" >&2
        exit 1
    fi
done
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10+"'
mkdir -p "$DOWNLOADS" "$TOOLS/bin"

fetch() {
    local filename="$1" url="$2" expected="$3"
    local destination="$DOWNLOADS/$filename"
    if [[ -f "$destination" ]] && printf '%s  %s\n' "$expected" "$destination" | sha256sum --check --status -; then
        echo "使用已校验缓存：$filename"
        return
    fi
    curl --fail --location --retry 2 --connect-timeout 20 --max-time 300 \
        --output "$destination.part" "$url"
    printf '%s  %s\n' "$expected" "$destination.part" | sha256sum --check -
    mv -- "$destination.part" "$destination"
}

# SHA-256 from Ubuntu jammy package metadata (verilator 4.038-1 amd64).
VERILATOR_VERSION='4.038-1'
VERILATOR_ARCHIVE="verilator_${VERILATOR_VERSION}_amd64.deb"
fetch "$VERILATOR_ARCHIVE" \
    "https://archive.ubuntu.com/ubuntu/pool/universe/v/verilator/$VERILATOR_ARCHIVE" \
    '3ed130509d5493a3c95e7be97a00cfed7457b2aeb9c11eed96ea3a802c310836'
VERILATOR_DIR="$TOOLS/verilator-$VERILATOR_VERSION"
mkdir -p "$VERILATOR_DIR"
dpkg-deb --extract "$DOWNLOADS/$VERILATOR_ARCHIVE" "$VERILATOR_DIR"
# Relocate the distro package without root or running package install scripts.
for name in verilator_bin verilator_bin_dbg; do
    ln -sfn "../../../bin/$name" "$VERILATOR_DIR/usr/share/verilator/bin/$name"
done
ln -sfn "verilator-$VERILATOR_VERSION" "$TOOLS/verilator"
ln -sfn '../../scripts/verilator.sh' "$TOOLS/bin/verilator"

# SHA-256 from the official chipsalliance/verible GitHub release asset digest.
VERIBLE_VERSION='v0.0-4298-g085eef05'
VERIBLE_ARCHIVE="verible-${VERIBLE_VERSION}-linux-static-x86_64.tar.gz"
fetch "$VERIBLE_ARCHIVE" \
    "https://github.com/chipsalliance/verible/releases/download/$VERIBLE_VERSION/$VERIBLE_ARCHIVE" \
    'ca83778c7c2b73272277bd670d1851c8caf973fd3283688aeb0d36d4b3598a90'
VERIBLE_DIR="$TOOLS/verible-$VERIBLE_VERSION"
mkdir -p "$VERIBLE_DIR"
tar -xzf "$DOWNLOADS/$VERIBLE_ARCHIVE" --strip-components=1 --no-same-owner -C "$VERIBLE_DIR"
ln -sfn "verible-$VERIBLE_VERSION" "$TOOLS/verible"
for executable in "$VERIBLE_DIR"/bin/*; do
    ln -sfn "../verible/bin/$(basename -- "$executable")" "$TOOLS/bin/$(basename -- "$executable")"
done
chmod +x "$ROOT/scripts/verilator.sh"

"$TOOLS/bin/verilator" --version
"$TOOLS/bin/verible-verilog-lint" --version
printf '\n安装完成。当前终端执行：\n  source "%s/scripts/env.sh"\n' "$ROOT"
