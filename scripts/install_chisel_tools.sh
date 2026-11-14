#!/usr/bin/env bash
# Explicit, project-local installation. Linux x86_64 only; no sudo/global edits.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/.tools"
LOCAL="$TOOLS/chisel"
DOWNLOADS="$TOOLS/downloads"

if [[ "$(uname -sm)" != 'Linux x86_64' ]]; then
    echo 'Chisel 安装脚本当前仅支持 Linux x86_64。' >&2
    exit 1
fi
for tool in curl sha256sum tar python3; do
    command -v "$tool" >/dev/null || { echo "缺少工具：$tool" >&2; exit 1; }
done
mkdir -p "$LOCAL" "$DOWNLOADS" "$TOOLS/bin"

fetch() {
    local filename="$1" url="$2" expected="$3"
    local destination="$DOWNLOADS/$filename"
    if [[ -f "$destination" ]] && printf '%s  %s\n' "$expected" "$destination" | sha256sum --check --status -; then
        echo "使用已校验缓存：$filename"
        return
    fi
    curl --fail --location --retry 2 --connect-timeout 20 --max-time 600 \
        --output "$destination.part" "$url"
    printf '%s  %s\n' "$expected" "$destination.part" | sha256sum --check -
    mv -- "$destination.part" "$destination"
}

# SHA-256 published in the official Adoptium release asset metadata.
JDK_ARCHIVE='OpenJDK17U-jdk_x64_linux_hotspot_17.0.21_9.tar.gz'
fetch "$JDK_ARCHIVE" \
    "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.21%2B9/$JDK_ARCHIVE" \
    '8b9b611d917e3dfd8419d3566b5949226f69b052fed7e109c1368add1dfe8711'
mkdir -p "$LOCAL/jdk-17.0.21+9"
tar -xzf "$DOWNLOADS/$JDK_ARCHIVE" --strip-components=1 --no-same-owner -C "$LOCAL/jdk-17.0.21+9"
ln -sfn 'jdk-17.0.21+9' "$LOCAL/jdk"

# SHA-256 pinned after downloading from Maven Central and checking its published
# SHA-1 (865c88898ed1e6a8403f8f62bb06e4d07b03ca28); not a claimed upstream SHA-256.
fetch 'sbt-launch-1.10.7.jar' \
    'https://repo.maven.apache.org/maven2/org/scala-sbt/sbt-launch/1.10.7/sbt-launch-1.10.7.jar' \
    '3cca02818047327a83efde776103a1ef92f76f72c062badbbb062499a3270c07'
cp -- "$DOWNLOADS/sbt-launch-1.10.7.jar" "$LOCAL/sbt-launch-1.10.7.jar"

# Chisel v6.5.0/etc/circt.json specifies firtool-1.62.0. SHA-256 from CIRCT's
# official firrtl-bin-linux-x64.tar.gz.sha256 release asset.
fetch 'firrtl-bin-linux-x64-1.62.0.tar.gz' \
    'https://github.com/llvm/circt/releases/download/firtool-1.62.0/firrtl-bin-linux-x64.tar.gz' \
    '1aee0d13fea52b504b0f689f4d890cfb7c63f7dc832308ceff9ae3f099e8e800'
mkdir -p "$LOCAL/firtool-1.62.0"
tar -xzf "$DOWNLOADS/firrtl-bin-linux-x64-1.62.0.tar.gz" --strip-components=1 --no-same-owner -C "$LOCAL/firtool-1.62.0"
ln -sfn 'firtool-1.62.0' "$LOCAL/firtool"

for name in java javac; do
    ln -sfn "../chisel/jdk/bin/$name" "$TOOLS/bin/$name"
done
ln -sfn '../chisel/firtool/bin/firtool' "$TOOLS/bin/firtool"
ln -sfn '../../scripts/chisel_sbt.sh' "$TOOLS/bin/sbt"
chmod +x "$ROOT/scripts/chisel_sbt.sh"
"$LOCAL/jdk/bin/java" -version
"$LOCAL/firtool/bin/firtool" --version
printf '\n已安装本地 JDK / sbt launcher / firtool。\n'
printf '用户工程首次构建可能从 Maven Central 下载其声明的 Scala/Chisel 依赖到 .tools/chisel/，需另行授权。\n'
printf '项目后端固定 Scala 2.13.12 / Chisel 6.5.0；运行 python3 run.py --language chisel --check-data 检查任务（不构建）。\n'
