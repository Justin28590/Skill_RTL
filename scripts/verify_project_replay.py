#!/usr/bin/env python3
"""Explicit offline reference-source replay through the SAME candidate validator. No model calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from rtlflow.project import bundle_text, load_projects, masked, parse_bundle, verify_project, write_bundle
from rtlflow.project_dataset import reference_compatibility, save_json, sha256
from rtlflow.chisel import reference_sources
from rtlflow.verify import run_command


def reference_bundle(task):
    """Testing only. This helper is NOT used by run.py or by the model provider."""
    root = Path(task['dataset_root'])
    if task.get('language') == 'chisel':
        return parse_bundle(bundle_text(reference_sources(root, task)), 'chisel')
    paths = [root / name for name in task['rtl_files']]
    files = {}
    while paths:
        source = paths.pop(0)
        code = reference_compatibility(task, source.read_text())
        if source.name in files:
            if files[source.name] != code:
                raise ValueError('reference basename collision: ' + source.name)
            continue
        files[source.name] = code
        for name in re.findall(r'`include\s+"([^"]+)"', masked(code, strings=False)):
            candidates = [source.parent / name, *[root / inc / name for inc in task['include_dirs']]]
            found = next((p for p in candidates if p.is_file()), None)
            if found is None:
                raise ValueError('unresolved reference include: ' + name)
            if '/' in name:
                raise ValueError('reference replay needs explicit include path mapping')
            paths.append(found)
    # Original USB RTL contains two nonsynthesizable diagnostic prints. Candidate policy
    # remains strict. Only the offline COPY loses these prints, never the pinned original.
    if task['id'] == 'usb_host_device':
        code, count = re.subn(r'\$display\s*\("Invalid (?:Handshake|DATA) PID detected in ProcessRXByte\\n"\);',
                              ';', files['processRxByte.v'])
        if count != 2:
            raise ValueError('USB diagnostic normalization no longer matches pinned source')
        files['processRxByte.v'] = code
    if task['id'] == 'fp32_fma':
        # Keep candidate extension policy unchanged: map the three legacy header
        # suffixes and their include strings in the offline copy only.
        headers = {name: str(Path(name).with_suffix('.vh')) for name in files if name.endswith('.vi')}
        normalized = {}
        for name, code in files.items():
            for old, new in headers.items():
                code = code.replace('`include "' + old + '"', '`include "' + new + '"')
            normalized[headers.get(name, name)] = code
        files = normalized
        old = '''    genvar ix;
    generate
        for (ix = 0; ix <= inWidth; ix = ix + 1) begin :Bit
            wire [(countWidth - 1):0] countSoFar;
            if (ix == 0) begin
                assign countSoFar = 0;
            end else begin
                assign countSoFar =
                    Bit[ix - 1].countSoFar | (oneLeastReverseIn[ix] ? ix : 0);
                if (ix == inWidth) assign count = countSoFar;'''
        new = '''    wire [(countWidth - 1):0] countSoFar [0:inWidth];
    genvar ix;
    generate
        for (ix = 0; ix <= inWidth; ix = ix + 1) begin :Bit
            if (ix == 0) begin
                assign countSoFar[ix] = 0;
            end else begin
                assign countSoFar[ix] =
                    countSoFar[ix - 1] | (oneLeastReverseIn[ix] ? ix : 0);
                if (ix == inWidth) assign count = countSoFar[ix];'''
        if files['HardFloat_primitives.v'].count(old) != 1:
            raise ValueError('HardFloat internal-wire normalization no longer matches pinned source')
        files['HardFloat_primitives.v'] = files['HardFloat_primitives.v'].replace(old, new)
        old_top = 'mulAddRecFN#(parameter expWidth = 3, parameter sigWidth = 3)'
        if files['mulAddRecFN.v'].count(old_top) != 1:
            raise ValueError('HardFloat top default normalization no longer matches pinned source')
        files['mulAddRecFN.v'] = files['mulAddRecFN.v'].replace(
            old_top, 'mulAddRecFN#(parameter expWidth = 8, parameter sigWidth = 24)')
    if task['id'] in {'axis_fifo_adapter', 'axis_packet_switch', 'systolic_matmul',
                      'axi_dma_engine', 'axi_scratchpad', 'axis_async_bridge'}:
        for name in files:
            # Only reviewed static configuration diagnostics, never datapath logic.
            files[name] = re.sub(r'\$error\([^;]+\);|\$finish;', ';', files[name])
            if task['id'] == 'axis_packet_switch':
                files[name] = re.sub(r'\$display\([^;]+\);', ';', files[name])
            if task['id'] == 'systolic_matmul':
                files[name] = files[name].replace('initial ;', 'initial begin end')
    language = task.get('dataset_provenance', {}).get('target_language', task.get('language', 'verilog'))
    return parse_bundle(bundle_text(files), language)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--task', action='append')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--language', choices=['verilog', 'systemverilog', 'chisel'], default='verilog')
    parser.add_argument('--negative-controls', action='store_true', help='inject bad DUT outputs from a trusted test-only fault module')
    parser.add_argument('--compact', action='store_true', help='discard reproducible binaries/waveforms, retain sources and logs')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be between 1 and 16')
    manifest = ROOT / 'data/project-rtl/tasks.json'
    tasks = load_projects(manifest, args.task, args.language)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    versions = {name: run_command([shutil.which(name), '-V'], output, 'version-' + name, 5)
                if shutil.which(name) else {'status': 'not_run'} for name in ('iverilog', 'vvp')}
    def check(task):
        work = output / task['id']
        work.mkdir()
        files = reference_bundle(task)
        (work / 'bundle.json').write_text(bundle_text(files))
        hashes = write_bundle(files, work / 'source')
        result = verify_project(files, work / 'source', task, work / 'checks',
                                {'language': args.language, 'tool_timeout_seconds': 30})
        result.update(task_id=task['id'], offline_reference_replay=True, model_calls=0, source_sha256=hashes,
                      replay_normalizations={
                          'usb_host_device': ['USB copy: removed two diagnostic $display statements; no datapath/control edits'],
                          'axis_fifo_adapter': ['Copy: omitted static invalid-parameter $error/$finish diagnostics; tested parameters are valid.'],
                          'axis_packet_switch': ['Copy: omitted static configuration $display/$error/$finish diagnostics; routing and arbitration unchanged.'],
                          'systolic_matmul': ['Icarus: explicit port kinds and unsigned 32-bit parameter spelling; packed boundary interconnects use continuous assignments; omitted invalid-N diagnostic. No algorithm/sequential changes.'],
                          'fp32_fma': ['Offline copy only: .vi headers/includes renamed to .vh; countLeadingZeros internal generate-scope wire chain expressed as an equivalent parent-scope wire array. Top defaults explicitly specialized to binary32 (8/24) for standalone compilation; tested reference uses the same overrides. Arithmetic and candidate XMR policy unchanged.'],
                          'axi_dma_engine': ['Copy: omitted static invalid-parameter $error/$finish diagnostics; DMA datapath/control unchanged.'],
                          'axi_scratchpad': ['Copy: omitted static invalid-parameter $error/$finish diagnostics; RAM/control unchanged.'],
                          'axis_async_bridge': ['Copy: omitted static invalid-parameter $error/$finish diagnostics; CDC/frame logic unchanged.'],
                          'sv_spi': ['Icarus repeated parameter keywords; edge_detect reset port spelling nrst->anrst.'],
                          'sv_uart_printer': ['Icarus repeated parameter keywords.'],
                          'chisel_uart_echo': ['Omitted unused legacy Chisel 3 CLI emitter; Chisel 6 host emitter used.'],
                          'chisel_double_buffer_fifo': ['Scala depth>0 elaboration assert changed to require; no hardware change.'],
                      }.get(task['id'], []))
        negative_status = 'not_run'
        if args.negative_controls and result['functional_status'] == 'passed':
            negative_dir = work / 'negative'
            negative_dir.mkdir()
            fault = negative_dir / 'fault.v'
            fault.write_text('module project_negative_control;\ninitial begin\n' + '\n'.join(
                'force ' + item['target'] + ' = ' + item['value'] + ';' for item in task['negative_forces']
            ) + '\nend\nendmodule\n')
            # Trusted fault injection is test-only, not part of a model bundle or CLI task.
            negative_task = {**task, 'candidate_testbench_files': [*task['candidate_testbench_files'], str(fault)],
                             'testbench_tops': [*task['testbench_tops'], 'project_negative_control'],
                             'simulation_timeout_seconds': task['negative_timeout_seconds']}
            write_bundle(files, negative_dir / 'source')
            negative = verify_project(files, negative_dir / 'source', negative_task, negative_dir / 'checks',
                                      {'language': args.language, 'tool_timeout_seconds': 5})
            sim = negative['checks']['simulation']
            explicit = bool(sim.get('verdict', {}).get('failure_patterns_seen')) or (
                sim.get('reason') == 'exit_code' and sim.get('returncode') not in (0, None))
            compile_ok = negative['checks']['compile']['status'] == 'passed'
            negative_status = 'passed' if compile_ok and explicit and negative['functional_status'] == 'failed' else 'failed'
            result['negative_control'] = negative
            result['fault_sha256'] = sha256(fault)
        result['negative_control_status'] = negative_status
        result['logs_sha256'] = {str(p.relative_to(work)): sha256(p) for p in sorted(work.rglob('*.log'))}
        if args.compact:
            for pattern in ('*.vvp', '*.vcd', 'firmware.hex'):
                for p in work.rglob(pattern):
                    p.unlink()
            for target in work.rglob('target'):
                if target.is_dir():
                    shutil.rmtree(target)
            result['pruned_artifacts'] = ['compiled .vvp', 'waveforms .vcd', 'copied firmware.hex', 'sbt target/ caches']
        save_json(work / 'report.json', result)
        print(task['id'], result['functional_status'], 'negative=' + negative_status,
              ', '.join(k for k,v in result['checks'].items() if v['status']=='failed'), flush=True)
        return {'id': task['id'], 'status': result['functional_status'], 'negative_control_status': negative_status,
                'report': task['id'] + '/report.json', 'report_sha256': sha256(work / 'report.json')}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        reports = list(pool.map(check, tasks))
    summary = {'model_calls': 0, 'offline_reference_replay': True, 'language': args.language,
               'tool_versions': versions,
               'manifest_sha256': sha256(manifest), 'total': len(reports),
               'passed': sum(r['status']=='passed' for r in reports),
               'negative_controls_passed': sum(r['negative_control_status']=='passed' for r in reports),
               'negative_controls_requested': args.negative_controls,
               'validator_sha256': {name: sha256(ROOT / name) for name in (
                   'scripts/verify_project_replay.py', 'src/rtlflow/project.py', 'src/rtlflow/chisel.py',
                   'src/rtlflow/project_dataset.py', 'scripts/chisel_sbt.sh', 'src/rtlflow/verify.py')},
               'tasks': reports}
    save_json(output / 'summary.json', summary)
    return 0 if summary['passed'] == summary['total'] and (
        not args.negative_controls or summary['negative_controls_passed'] == summary['total']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
