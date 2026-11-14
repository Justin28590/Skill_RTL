"""Fixed multi-file Chisel frontend. Executes Scala: NOT a security sandbox."""
import hashlib
from pathlib import Path
import re

from .project_dataset import sha256
from .verify import not_run, run_command

ROOT = Path(__file__).resolve().parents[2]
BUILD = '''scalaVersion := "2.13.12"
libraryDependencies += "org.chipsalliance" %% "chisel" % "6.5.0"
addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.5.0" cross CrossVersion.full)
scalacOptions ++= Seq("-language:reflectiveCalls", "-deprecation", "-feature")
'''


def reference_sources(root, task):
    """Explicit replay-only compatibility edits; originals remain checksum locked."""
    files = {Path(name).name: (Path(root) / name).read_text() for name in task['rtl_files']}
    if task['id'] == 'chisel_uart_echo':
        tail = 'object UartMain extends App {\n  emitVerilog(new UartMain(50000000, 115200), Array("--target-dir", "generated"))\n}'
        if files['uart.scala'].count(tail) != 1:
            raise ValueError('upstream legacy emitter changed')
        files['uart.scala'] = files['uart.scala'].replace(tail, '// Legacy CLI emitter omitted; host-owned Chisel 6 emitter is used.')
    if task['id'] == 'chisel_double_buffer_fifo':
        old = 'assert(depth > 0, "Number of buffer elements needs to be larger than 0")'
        if files['Fifo.scala'].count(old) != 1:
            raise ValueError('upstream elaboration guard changed')
        files['Fifo.scala'] = files['Fifo.scala'].replace(old, old.replace('assert(', 'require('))
    return dict(sorted(files.items()))


def validate_chisel_config(config, tops):
    if not isinstance(config, list) or len(config) != len(tops):
        raise ValueError("missing Chisel elaboration contract")
    if {entry.get('module') for entry in config} != set(tops):
        raise ValueError("Chisel tops do not match design tops")
    for entry in config:
        if set(entry) != {'module', 'class', 'args'} or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', entry['class']):
            raise ValueError("invalid Chisel class contract")
        if not re.fullmatch(r'[A-Za-z_]\w*', entry['module']) or not isinstance(entry['args'], list):
            raise ValueError("invalid Chisel module/arguments")
        for arg in entry['args']:
            if type(arg) is int and 0 < arg <= 1_000_000_000:
                continue
            if isinstance(arg, dict) and set(arg) == {'uint_width'} and type(arg['uint_width']) is int and 0 < arg['uint_width'] <= 4096:
                continue
            raise ValueError("Chisel arguments must be bounded integers or UInt widths")


def scala_policy(files):
    # Conservative accident/obvious-I/O filter; arbitrary JVM programs are not sandboxed by regex.
    from .project import masked
    issues = []
    forbidden = r'\b(?:java|javax|sys|System|Runtime|Process|ProcessBuilder|Thread|ClassLoader|reflect|Source|File|Files|Paths|URL|Socket|BlackBox|ExtModule|HasBlackBoxResource|HasBlackBoxInline|HasBlackBoxPath|App|main|ChiselStage|emitVerilog|emitSystemVerilog|RTLFlowMain|printf|println|print|readLine|assert|assume|cover)\b'
    for name, code in files.items():
        clean = masked(code)
        if re.search(forbidden, clean) or re.search(r'\\u[0-9a-fA-F]{4}|`', code):
            issues.append(name + ': forbidden host I/O, external RTL, verification or emitter construct')
        for item in re.findall(r'\bimport\s+([^\n;]+)', clean):
            if not item.strip().startswith(('chisel3.', 'scala.collection.', 'scala.math.')):
                issues.append(name + ': unsupported import')
    return {'status': 'failed' if issues else 'passed', 'reason': 'chisel_source_policy', 'issues': issues}


def elaborate_chisel(files, task, workdir, timeout=300, *, trusted_reference=False):
    """Compile only supplied Scala with a host-owned build and emitter; no upstream sbt scripts."""
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    config = task.get('chisel_tops')
    validate_chisel_config(config, task['design_tops'])
    from .project import bundle_text, parse_bundle
    # Revalidate even for direct API callers, before copying into a build tree.
    files = parse_bundle(bundle_text(files), 'chisel')
    checks = {'scala_policy': {'status': 'passed', 'reason': 'explicit_trusted_reference'} if trusted_reference else scala_policy(files),
              'elaboration': not_run('scala_policy_not_passed')}
    result = {'checks': checks, 'files': None, 'toolchain': {'scala': '2.13.12', 'chisel': '6.5.0', 'sbt': '1.10.7', 'firtool': '1.62.0'}}
    if checks['scala_policy']['status'] != 'passed':
        return result
    local = ROOT / '.tools/chisel'
    if not all(p.exists() for p in (local / 'jdk/bin/java', local / 'sbt-launch-1.10.7.jar', local / 'firtool/bin/firtool')):
        checks['elaboration'] = not_run('missing_chisel_toolchain; run scripts/install_chisel_tools.sh explicitly')
        return result
    result['toolchain_sha256'] = {str(p.relative_to(ROOT)): sha256(p) for p in (
        local / 'jdk/bin/java', local / 'sbt-launch-1.10.7.jar', local / 'firtool/bin/firtool')}
    build = workdir / 'build'
    build.mkdir(exist_ok=False)
    (build / 'build.sbt').write_text(BUILD)
    (build / 'project').mkdir()
    (build / 'project/build.properties').write_text('sbt.version=1.10.7\n')
    source = build / 'src/main/scala'
    source.mkdir(parents=True)
    for name, code in files.items():
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code)
    calls = []
    for index, entry in enumerate(config):
        args = ', '.join(str(a) if type(a) is int else f'UInt({a["uint_width"]}.W)' for a in entry['args'])
        calls.append(f'''  circt.stage.ChiselStage.emitSystemVerilogFile(new {entry['class']}({args}),
    args = Array("--target-dir", "generated/{index}"),
    firtoolOpts = Array("--disable-all-randomization", "--strip-debug-info",
      "--lowering-options=disallowLocalVariables,disallowPackedArrays,disallowPortDeclSharing"))''')
    emitter = 'import chisel3._\nobject RTLFlowMain extends App {\n' + '\n'.join(calls) + '\n}\n'
    (source / 'RTLFlowMain.scala').write_text(emitter)
    checks['elaboration'] = run_command([ROOT / 'scripts/chisel_sbt.sh', 'runMain RTLFlowMain'], build, 'elaboration', timeout,
                                        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    result['harness_sha256'] = {str(p.relative_to(build)): sha256(p) for p in
                                (build / 'build.sbt', build / 'project/build.properties', source / 'RTLFlowMain.scala')}
    if checks['elaboration']['status'] != 'passed':
        return result
    generated = {}
    for path in sorted((build / 'generated').rglob('*.sv')):
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            checks['elaboration'].update(status='failed', reason='unsafe_or_oversize_emitted_rtl')
            return result
        code = path.read_text()
        if path.name in generated and generated[path.name] != code:
            checks['elaboration'].update(status='failed', reason='conflicting_emitted_modules')
            return result
        generated[path.name] = code
    from .providers import GenerationError
    try:
        result['files'] = parse_bundle(bundle_text(generated), 'systemverilog')
    except GenerationError as exc:
        checks['elaboration'].update(status='failed', reason='invalid_emitted_rtl', detail=str(exc))
    result['emitted_files_sha256'] = {name: hashlib.sha256(code.encode()).hexdigest() for name, code in generated.items()}
    return result
