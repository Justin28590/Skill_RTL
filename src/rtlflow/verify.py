"""Run local EDA tools with bounded wall time and explicit check states.

This is process isolation for reliability, NOT a security sandbox.
Project verification lives in project.py; this module only manages processes.
"""

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

LOG_PREVIEW = 16000


def not_run(reason):
    return {"status": "not_run", "reason": reason}


def run_command(command, workdir, name, timeout, *, env=None):
    workdir = Path(workdir).resolve()
    stdout_path = workdir / f"{name}.stdout.log"
    stderr_path = workdir / f"{name}.stderr.log"
    started = time.monotonic()
    result = {
        "command": [str(part) for part in command],
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "returncode": None,
    }
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        try:
            process = subprocess.Popen(
                result["command"], cwd=workdir, stdout=stdout, stderr=stderr,
                start_new_session=True, env=env,
            )
        except OSError as exc:
            result.update(status="not_run", reason=f"tool_start_error: {exc}")
        else:
            try:
                process.wait(timeout=timeout)
                result.update(
                    status="passed" if process.returncode == 0 else "failed",
                    reason="exit_code",
                )
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                if isinstance(exc, KeyboardInterrupt):
                    raise
                result.update(status="failed", reason="timeout")
            result["returncode"] = process.returncode
    result["elapsed_seconds"] = round(time.monotonic() - started, 4)
    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        with path.open(errors="replace") as stream:
            result[label] = stream.read(LOG_PREVIEW)
        result[f"{label}_truncated"] = path.stat().st_size > LOG_PREVIEW
    return result


def strip_comments(code):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", code, flags=re.DOTALL)


def tool_versions(workdir):
    versions = {}
    for name, flag in (("iverilog", "-V"), ("vvp", "-V"),
                       ("verilator", "--version"), ("verible-verilog-lint", "--version")):
        executable = shutil.which(name)
        versions[name] = (
            run_command([executable, flag], workdir, f"version-{name}", 5)
            if executable else not_run("missing_tool")
        )
    return versions
