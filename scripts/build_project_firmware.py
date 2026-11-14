#!/usr/bin/env python3
"""Rebuild the PicoRV32 pilot image from pinned upstream ISA tests (no C demo)."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rtlflow.project_dataset import load_manifest, save_json, sha256
from rtlflow.verify import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new scratch directory; never overwrites dataset")
    args = parser.parse_args()
    data, manifest, _ = load_manifest(ROOT / "data/project-rtl/tasks.json")
    tools = {name: shutil.which(name) for name in ("clang-18", "ld.lld-18", "llvm-objcopy-18")}
    if not all(tools.values()):
        parser.error("requires clang-18, ld.lld-18 and llvm-objcopy-18; tools are not installed automatically")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    upstream = data / "sources/YosysHQ/picorv32/tests"
    tests = sorted(upstream.glob("*.S"))
    if len(tests) != 45:
        raise ValueError("expected the pinned 45 upstream ISA tests")
    objects, checks = [], []
    def run(command, name):
        check = run_command(command, output, name, 30)
        checks.append(check)
        if check["status"] != "passed":
            save_json(output / "build-report.json", {"status": "failed", "checks": checks})
            raise RuntimeError(f"firmware build failed: {name}; see {output}")
    for source in [data / "tests/blackbox/picorv32/start.S", *tests]:
        target = output / (source.stem + ".o")
        command = [tools["clang-18"], "--target=riscv32-unknown-elf", "-march=rv32imc", "-mabi=ilp32",
                   "-mno-relax", "-c", str(source), "-o", str(target)]
        if source.parent == upstream:
            command += ["-DTEST_FUNC_NAME=" + source.stem, '-DTEST_FUNC_TXT="' + source.stem + '"',
                        "-DTEST_FUNC_RET=" + source.stem + "_ret"]
        run(command, "assemble-" + source.stem)
        objects.append(str(target))
    run([tools["ld.lld-18"], "-m", "elf32lriscv", "--no-relax", "-T",
         str(data / "tests/blackbox/picorv32/sections.ld"), "-o", str(output / "firmware.elf"), *objects], "link")
    run([tools["llvm-objcopy-18"], "-O", "binary", str(output / "firmware.elf"), str(output / "firmware.bin")], "objcopy")
    binary = (output / "firmware.bin").read_bytes()
    if len(binary) > 128 * 1024:
        raise ValueError("firmware exceeds 128 KiB test memory")
    binary += bytes(128 * 1024 - len(binary))
    image = output / "firmware.hex"
    image.write_text("".join(f'{int.from_bytes(binary[i:i+4], "little"):08x}\n' for i in range(0, len(binary), 4)))
    matched = sha256(image) == manifest["support_sha256"]["tests/blackbox/picorv32/firmware.hex"]
    save_json(output / "build-report.json", {"status": "passed" if matched else "failed",
              "firmware_sha256": sha256(image), "matches_pinned_image": matched,
              "isa_suite_count": len(tests), "checks": checks})
    print(f"Pinned firmware byte match: {matched}; evidence: {output / 'build-report.json'}")
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
