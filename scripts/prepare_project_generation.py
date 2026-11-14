#!/usr/bin/env python3
"""Rebuild candidate test adapters and interface metadata in tasks.json.

specs/ is the single, reviewed source of model requirements. This command never
rewrites specs or upstream sources; it only rebuilds tests/adapted/ and each
entry's generation metadata. Requires Icarus and the fixed Chisel toolchain.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rtlflow.project import masked, scope_ports
from rtlflow.project_dataset import load_manifest, reference_compatibility, save_json, sha256
from rtlflow.chisel import elaborate_chisel, reference_sources


def replace_task(code, name, body):
    expression = rf'\btask\s+{name}\s*;.*?\bendtask\b'
    result, count = re.subn(expression, f'task {name};\n{body}\nendtask', code, flags=re.S)
    if count != 1:
        raise ValueError("upstream task layout changed: " + name)
    return result


def adapt(code, key):
    changes = []
    if key == "cmac":
        code = replace_task(code, "tc1_check_reset", '''    begin
      inc_tc_ctr();
      reset_dut();
      read_word(ADDR_STATUS);
      if (read_data !== 32'h1) begin inc_error_ctr(); $display("ERROR: public reset status"); end
      read_word(ADDR_CTRL);
      if (read_data !== 0) begin inc_error_ctr(); $display("ERROR: public reset key configuration"); end
      read_word(ADDR_FINAL_SIZE);
      if (read_data !== 0) begin inc_error_ctr(); $display("ERROR: public reset final size"); end
      read_result();
      if (result_data !== 0) begin inc_error_ctr(); $display("ERROR: public reset result"); end
    end''')
        code = replace_task(code, "tc2_gen_subkeys", '''    begin
      inc_tc_ctr();
      init_key(256'h2b7e1516_28aed2a6_abf71588_09cf4f3c_00000000_00000000_00000000_00000000, AES_128_BIT_KEY);
      wait_ready();
      write_block(128'h6bc1bee2_2e409f96_e93d7e11_7393172a);
      write_word(ADDR_FINAL_SIZE, AES_BLOCK_SIZE);
      write_word(ADDR_CTRL, (2 ** CTRL_FINAL_BIT));
      wait_ready();
      read_result();
      if (result_data !== 128'h070a16b4_6b4d4144_f79bdd9d_d04a287c)
        begin inc_error_ctr(); $display("ERROR: public K1-dependent full-block MAC"); end
    end''')
        changes += ["CMAC white-box reset checks replaced by public status/config/final-size/result checks",
                    "CMAC internal K1/K2 probes replaced by externally observed K1-dependent MAC; empty/partial MACs still exercise K2"]
    # Only debug output statements: remove NO functional stimulus, branch or expected result.
    clean = masked(code)
    replacements = []
    for m in re.finditer(r'\$display\s*\(', clean):
        depth, end = 1, m.end()
        while depth:
            if clean[end] == '(': depth += 1
            if clean[end] == ')': depth -= 1
            end += 1
        while clean[end].isspace(): end += 1
        if clean[end] != ';': raise ValueError('unexpected display statement')
        end += 1
        if re.search(r'\bdut\.', clean[m.start():end]):
            replacements.append((m.start(), end))
    for start, end in reversed(replacements):
        code = code[:start] + ';' + '\n' * code[start:end].count('\n') + code[end:]
    if replacements:
        changes.append(f"removed {len(replacements)} implementation-dependent debug displays")
    clean = masked(code)
    replacements = [(m.start(), m.end()) for m in re.finditer(r'!=(?!=)', clean)]
    for start, end in reversed(replacements):
        code = code[:start] + '!==' + code[end:]
    if replacements:
        changes.append(f"strengthened {len(replacements)} inequality checks to reject X/Z")
    return code, changes


def prepare_addition(data, task, work):
    build = work / task['id']
    build.mkdir()
    rtl = []
    if task['language'] == 'chisel':
        frontend = elaborate_chisel(reference_sources(data, task), task, build / 'chisel', trusted_reference=True)
        if frontend['files'] is None:
            raise ValueError('reference Chisel elaboration failed: ' + str(frontend['checks']))
        sources = frontend['files']
    else:
        sources = {Path(name).name: reference_compatibility(task, (data / name).read_text()) for name in task['rtl_files']}
    for name, code in sources.items():
        target = build / name
        target.write_text(code)
        rtl.append(str(target))
    binary = build / 'reference.vvp'
    includes = [arg for name in task['include_dirs'] for arg in ('-I', str(data / name))]
    subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(binary), *includes, *rtl,
                    *[str(data / n) for n in task['testbench_files']]], check=True, capture_output=True, timeout=30)
    ports = scope_ports(binary)
    params = scope_ports(binary, parameters=True)
    return {'files_sha256': {n: sha256(data / n) for n in task['testbench_files']},
            'candidate_testbench_files': task['testbench_files'],
            'expected_ports': {n: ports[n] for n in task['dut_roots']},
            'public_parameters': {ports[n]['module']: params[n] for n in task['dut_roots']},
            'testbench_adaptations': {n: {'origin': 'dataset_authored', 'changes': [], 'sha256': sha256(data / n)} for n in task['testbench_files']},
            'additional_dut_roots': [], 'additional_required_output': []}


def prepare_adapted(data, task, work):
    key = task['id']
    target = data / 'tests/adapted' / key
    target.mkdir(parents=True, exist_ok=True)
    adapted, hashes, changes = [], {}, {}
    extra_roots, extra_required = [], []
    for name in task['testbench_files']:
        code, edits = adapt((data / name).read_text(), key if Path(name).name == 'tb_cmac.v' else '')
        if key == 'usb_host_device' and name == task['testbench_files'][0]:
            headers = sorted((data / 'sources/freecores/usbhostslave/RTL/include').glob('*.v'))
            code = ''.join('`include "' + p.name + '"\n' for p in headers) + code
            edits.append('TB imports its own immutable protocol constants; no candidate macro dependence')
        if key == 'picorv32_axi' and Path(name).name == 'testbench.v':
            if code.count('\treg clk = 1;') != 1:
                raise ValueError('CPU testbench injection anchor changed')
            code = code.replace('\treg clk = 1;',
                                '    project_cpu_signature project_signature();\n\treg clk = 1;')
            edits.append('added independent AXI arithmetic/load-store signature oracle; software console is not sufficient')
        output = target / Path(name).name
        output.write_text('// Dataset adaptation; upstream originals remain unchanged. See tasks.json.\n' + code)
        rel = str(output.relative_to(data))
        adapted.append(rel)
        hashes[rel] = sha256(output)
        changes[name] = {'sha256': sha256(data / name), 'adapted': rel, 'changes': edits}
    if key == 'picorv32_axi':
        oracle = 'tests/blackbox/picorv32/signature_tb.sv'
        adapted.append(oracle)
        hashes[oracle] = sha256(data / oracle)
        changes[oracle] = {'origin': 'dataset_authored', 'sha256': hashes[oracle], 'adapted': oracle,
                          'changes': ['independent expected values, 64 arithmetic/load-store signatures, no console oracle']}
        extra_roots.append('testbench.project_signature.dut')
        extra_required.append({'regex': r'PROJECT_RTL_CPU_SIGNATURE_PASS writes=64', 'min_count': 1})
    dut_roots = task['dut_roots'] + extra_roots
    binary = work / (key + '.vvp')
    cmd = ['iverilog', '-g' + task['dialect'], '-o', str(binary)]
    for top in task['testbench_tops']: cmd += ['-s', top]
    for inc in task['include_dirs']: cmd += ['-I', str(data / inc)]
    cmd += ['-D' + v for v in task['defines']]
    cmd += [str(data / p) for p in task['rtl_files'] + adapted]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    ports = scope_ports(binary)
    expected = {name: ports[name] for name in dut_roots}
    parameters = scope_ports(binary, parameters=True)
    public_parameters = {expected[name]['module']: parameters[name] for name in dut_roots}
    for filename in adapted:
        refs = re.findall(r'\bdut\.([A-Za-z_][\w.]*)', masked((data / filename).read_text()))
        allowed = next(iter(expected.values()))['ports']
        if any(ref not in allowed for ref in refs):
            raise ValueError(f'nonpublic DUT dependency remains: {key}: {refs}')
    return {'files_sha256': hashes, 'candidate_testbench_files': adapted, 'expected_ports': expected,
            'public_parameters': public_parameters, 'testbench_adaptations': changes,
            'additional_dut_roots': extra_roots, 'additional_required_output': extra_required}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/project-rtl', help='dataset directory')
    args = parser.parse_args()
    data, catalog, _ = load_manifest(args.output / 'tasks.json')
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for task in catalog['tasks']:
            prepare = prepare_addition if task.get('intake_version') == 2 else prepare_adapted
            task['generation'] = prepare(data, task, work)
            print(task['id'], 'candidate metadata rebuilt; specification unchanged', flush=True)
    catalog['generation_ready'] = True
    save_json(data / 'tasks.json', catalog)


if __name__ == '__main__':
    main()
