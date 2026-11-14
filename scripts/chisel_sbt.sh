#!/usr/bin/env bash
# Minimal project-local launcher: pass sbt commands, not sbt-extras flags.
set -euo pipefail
SCRIPT="$(readlink -f -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SCRIPT")/.." && pwd)"
LOCAL="$ROOT/.tools/chisel"
if [[ ! -x "$LOCAL/jdk/bin/java" || ! -f "$LOCAL/sbt-launch-1.10.7.jar" || ! -x "$LOCAL/firtool/bin/firtool" ]]; then
    echo 'Chisel 工具缺失；请显式执行 bash scripts/install_chisel_tools.sh。' >&2
    exit 2
fi
export JAVA_HOME="$LOCAL/jdk"
export PATH="$JAVA_HOME/bin:$LOCAL/firtool/bin:$PATH"
export COURSIER_CACHE="$LOCAL/cache/coursier"
export COURSIER_REPOSITORIES='https://repo.maven.apache.org/maven2'
export RTL_CHISEL_FIRTOOL="$LOCAL/firtool/bin/firtool"
export CHISEL_FIRTOOL_PATH="$LOCAL/firtool/bin"
mkdir -p "$LOCAL/cache" "$LOCAL/home"
# Deliberately avoid loading global sbt plugins or inheriting JVM option strings.
# CPU/heap caps limit normal build cost, but are not a security sandbox.
exec "$JAVA_HOME/bin/java" -Xms128m -Xmx2g -XX:ActiveProcessorCount=4 \
    "-Duser.home=$LOCAL/home" \
    "-Dsbt.boot.directory=$LOCAL/cache/boot" \
    "-Dsbt.global.base=$LOCAL/cache/global" \
    "-Dsbt.ivy.home=$LOCAL/cache/ivy" \
    "-Dsbt.repository.config=$ROOT/configs/chisel-repositories" \
    -Dsbt.override.build.repos=true -Dsbt.supershell=false -Dsbt.log.noformat=true \
    -Dsbt.server.autostart=false \
    -jar "$LOCAL/sbt-launch-1.10.7.jar" "$@"
