#!/usr/bin/env python3
"""Import two pinned compute/interconnect IPs, preserving the existing corpus.

Explicit --download fetches fixed archives. --archives DIR uses local
<owner>/<repo>/archive.tar.gz files. No upstream build scripts are executed.
Run prepare_project_generation.py afterwards, then re-run validation evidence.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from rtlflow.project import masked
from rtlflow.project_dataset import local_path, reference_compatibility, save_json, sha256

SOURCES = {
    'tms4517/2D-Systolic-Array-Multiplier': {
        'revision': 'd2eac0638b61c5f8bf4062bc636e774c61a38d8c',
        'archive_sha256': 'c841fd997086ec25e1f835d1f18e5eb5829bfd522111728026718c45be8231e0',
        'files': ['README.md', 'LICENSE', 'rtl/topSystolicArray.sv', 'rtl/systolicArray.sv', 'rtl/pe.sv'],
    },
    'alexforencich/verilog-axis': {
        'revision': '48ff7a7e2ef782cf778d47910cf85835c64b1bce',
        'archive_sha256': '92d714f9a4711491375c3794d5916860cffc776d91fb4b8c548f4cbd4c562aff',
        'files': ['README.md', 'COPYING', 'rtl/axis_switch.v', 'rtl/arbiter.v', 'rtl/priority_encoder.v', 'rtl/axis_register.v'],
    },
}
ADDITIONS = [
    {
        'id': 'systolic_matmul', 'repository': 'tms4517/2D-Systolic-Array-Multiplier',
        'language': 'systemverilog', 'top': 'topSystolicArray',
        'files': ['rtl/topSystolicArray.sv', 'rtl/systolicArray.sv', 'rtl/pe.sv'],
        'title': '参数化二维脉动阵列矩阵乘法引擎', 'category': 'ai_accelerator',
        'description': '完整输入错位/移位调度、N×N PE网格、8位无符号乘法与32位累加、完成控制。不是完整TPU/NPU。',
        'behavior': '''参数N默认4，合法范围3..256。输入元素是**无符号UINT8**，不是有符号INT8或浮点。
计算C[i][j]=sum(A[i][k]*B[k][j], k=0..N-1)，输出无符号32位。
所有矩阵为packed数组；元素[i][j]对应扁平总线的(N*i+j)*元素位宽处，低位是[0][0]。
i_arst异步高有效，清除结果、完成标志与在途操作。i_clk上升沿采样。
i_validInput在空闲时拉高一拍，锁存两输入矩阵，之后输入可任意变化。
若接受输入的上升沿为t，o_validResult在t+(3*N-2)上升沿之后拉高且仅保持一拍；此时o_c有效。
在其他周期不保证o_c保留结果。没有ready/背压接口；调用方在一次接受后至少等3*N+3拍再提交下一组矩阵，禁止重叠请求。
实现完整调度和实际PE子模块网格，不得用常量表/行为桩代替。内部命名不要求与上游相同。''',
        'coverage': 'N=3/4/8各40组独立整数矩阵乘法scoreboard：零、单位、置换、全255、非对称及固定种子随机矩阵；输入采样隔离、精确完成延迟/单拍脉冲、连续独立事务、异步复位取消在途任务。共120组矩阵、3560个输出元素。',
        'limitations': ['Only N=3,4,8 exercised; other legal dimensions are not exhaustively verified.',
                        'Unsigned integer matrix engine only; no signed INT8, floating point, quantization, DMA, software stack or full NPU claims.'],
        'dut_roots': ['tb.case3.dut', 'tb.case4.dut', 'tb.case8.dut'],
        'required_output': [{'regex': f'COMPUTE_PASS systolic_matmul N={n} matrices=40', 'min_count': 1} for n in (3,4,8)],
        'negative_forces': [{'target': 'tb.case4.dut.o_c', 'value': "512'h0"}],
        'compatibility': 'Icarus构建副本将var端口改为显式net/output类型，int unsigned改为等宽无符号logic [31:0]；参数诊断置于initial中；两个网格边界连接改为wire+连续赋值，避免packed切片混合驱动限制。不改变算法、时序或原始文件。候选回放仅另删除无效N的诊断。',
    },
    {
        'id': 'axis_packet_switch', 'repository': 'alexforencich/verilog-axis',
        'language': 'verilog', 'top': 'axis_switch',
        'files': ['rtl/axis_switch.v', 'rtl/arbiter.v', 'rtl/priority_encoder.v', 'rtl/axis_register.v'],
        'title': '多端口AXI-Stream分组交换与仲裁互连', 'category': 'accelerator_interconnect',
        'description': '可参数化多输入/多输出流交换，目的路由、逐输出仲裁、整帧锁定和skid缓冲；用于加速器流互连，不是完整NoC。',
        'behavior': '''clk上升沿；rst同步高有效，清空缓冲和路由/仲裁状态。
各接口均为标准ready/valid握手，valid=1且ready=0时必须保持数据和所有边带稳定。
端口i对应各扁平总线的低位起第i个切片。保留tdata/tkeep/tlast/tid/tdest/tuser语义。
每个输入在帧首选择输出，直到tlast握手完成前保持整帧路由；同一输出不能混入另一输入的帧。
M_BASE=0时使用输入tdest的最高$clog2(M_COUNT)位选输出，M_COUNT=1时忽略路由位；
否则M_TOP=0表示逐输出精确匹配M_BASE，否则使用包含端点的[M_BASE,M_TOP]范围。
M_CONNECT中第m*S_COUNT+s位决定输入s能否到输出m；无匹配或禁止连接的帧被接收并丢弃。
UPDATE_TID启用时，输出ID高$clog2(S_COUNT)位标记输入端口，低位保留输入ID；tdest截取到M_DEST_WIDTH。
KEEP/ID/USER禁用时分别输出全1/0/0。S_REG_TYPE/M_REG_TYPE为0旁路、1简单缓冲、2 skid缓冲。
仲裁按整帧执行，ARB_TYPE_ROUND_ROBIN=1轮询否则固定优先级；ARB_LSB_HIGH_PRIORITY选择优先方向。
保留全部公开参数及合法配置行为、实际仲裁器/缓冲子模块。时延可随握手和缓冲变化，不要求固定拍数。
验证配置为4入2出、32位data、4位keep、4/6位输入/输出ID、2位dest、1位user，ID更新开启，双侧skid及轮询仲裁。''',
        'coverage': '4入2出，两个复位分隔epoch共192帧，1..7拍/帧；四输入竞争同一输出、多输出并行路由、输入气泡、长输出阻塞及独立背压；核对每拍数据/keep/last/ID/dest/user、帧内不交织、输出阻塞稳定性、无丢失/重复及复位清空在途缓冲。',
        'limitations': ['Only the documented 4x2 round-robin/skid-buffer configuration is tested; fixed priority, custom address ranges and disconnected-route dropping are not covered.',
                        'Packet stream switch only, not a mesh NoC, virtual-channel router or cache-coherent fabric.'],
        'dut_roots': ['tb.dut'],
        'required_output': [{'regex': 'COMPUTE_PASS axis_packet_switch packets=192', 'min_count': 1}],
        'negative_forces': [{'target': 'tb.dut.m_axis_tdata', 'value': "64'h0"}],
        'compatibility': '原版可直接编译。候选回放副本仅删除静态配置打印/无效参数诊断，不修改路由、仲裁或数据通路；正常模型候选的安全策略不放宽。',
    },
]


def import_sources(data, lock, archives, download, sources=None):
    # Validate all archives and existing files before changing the lock/inventory.
    sources = SOURCES if sources is None else sources
    staged = {}
    for repo, config in sources.items():
        prior = lock['sources'].get(repo, {})
        if prior and any(prior[k] != config[k] for k in ('revision', 'archive_sha256')):
            raise ValueError('refusing changed source revision: ' + repo)
        if download:
            url = f"https://codeload.github.com/{repo}/tar.gz/{config['revision']}"
            with urllib.request.urlopen(url, timeout=90) as stream:
                archive = stream.read(120_000_001)
        else:
            archive = (archives / repo / 'archive.tar.gz').read_bytes()
        if len(archive) > 120_000_000 or hashlib.sha256(archive).hexdigest() != config['archive_sha256']:
            raise ValueError('archive size/checksum mismatch: ' + repo)
        found = {}
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as stream:
            for member in stream:
                name = str(PurePosixPath(*PurePosixPath(member.name).parts[1:]))
                if name not in config['files']:
                    continue
                if not member.isfile() or member.issym() or member.islnk() or member.size > 15_000_000 or name in found:
                    raise ValueError('unsafe archive entry')
                content = stream.extractfile(member).read()
                target = local_path(data, f'sources/{repo}/{name}', exists=False)
                if target.exists() and target.read_bytes() != content:
                    raise ValueError('refusing changed original: ' + str(target))
                found[name] = content
        if set(found) != set(config['files']):
            raise ValueError('incomplete archive: ' + repo)
        staged[repo] = found
    for repo, found in staged.items():
        target = data / 'sources' / repo
        prior = lock['sources'].get(repo, {})
        for name, content in found.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        lock['sources'][repo] = {
            'repository': 'https://github.com/' + repo, 'revision': sources[repo]['revision'],
            'archive_sha256': sources[repo]['archive_sha256'], 'license': sources[repo].get('license', 'MIT'),
            'files': {**prior.get('files', {}), **{n: sha256(target / n) for n in sorted(found)}},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archives', type=Path)
    group.add_argument('--download', action='store_true')
    args = parser.parse_args()
    data = ROOT / 'data/project-rtl'
    manifest = json.loads((data / 'tasks.json').read_text())
    lock = json.loads((data / 'sources.lock.json').read_text())
    import_sources(data, lock, args.archives, args.download)
    save_json(data / 'sources.lock.json', lock)
    install_additions(data, manifest, ADDITIONS, SOURCES, version=3)


def install_additions(data, manifest, additions, sources, *, version):
    """Build public contracts and catalog entries without changing prior tasks."""
    ids = {a['id'] for a in additions}
    tasks = [t for t in manifest['tasks'] if t['id'] not in ids]
    for item in additions:
        key, repo = item['id'], item['repository']
        prefix = f'sources/{repo}/'
        task = {k: item[k] for k in ('id', 'repository', 'language', 'title', 'description', 'category',
                                    'coverage', 'limitations', 'dut_roots', 'required_output', 'negative_forces')}
        task.update(family=repo, scope='complete_portable_ip_design', intake_version=2,
                    target_languages=['verilog', 'systemverilog'] if item['language'] == 'verilog' else ['systemverilog'],
                    design_tops=[item['top']], top_files=[prefix + item['files'][0]],
                    rtl_files=[prefix + n for n in item['files']],
                    testbench_files=[item.get('testbench', f'tests/blackbox/compute/{key}_tb.sv')], testbench_tops=['tb'],
                    include_dirs=[prefix + n for n in item.get('include_dirs', [])], defines=[], dialect='2012',
                    forbidden_output=['(?i)error|fatal|failed'], simulation_timeout_seconds=60, negative_timeout_seconds=10,
                    documentation=[prefix + sources[repo].get('readme', 'README.md')], verification_origin='dataset_authored_black_box',
                    reference_sources_visible_to_model=False,
                    rtl_file_count=len(item['files']),
                    rtl_source_lines=sum(len((data / (prefix+n)).read_text().splitlines()) for n in item['files']))
        code = reference_compatibility(task, (data / task['top_files'][0]).read_text())
        clean = masked(code)
        start = re.search(r'\bmodule\s+' + item['top'] + r'\b', clean).start()
        end = clean.index(');', start) + 2
        # axis_switch also exposes derived parameters after its port declaration.
        params = re.findall(r'(?m)^parameter\s+[^;]+;', code[end:])
        interface = item.get('interface', code[start:end] + '\n' + '\n'.join(params) + '\nendmodule')
        license_name = sources[repo].get('license', 'MIT')
        license_file = sources[repo].get('license_file', 'LICENSE' if repo.startswith('tms4517/') else 'COPYING')
        text = (f"# {item['title']}\n\n{item['description']}\n\n## 行为与时序契约\n\n{item['behavior']}\n\n"
                '## 编译配置\n\nSystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。\n\n'
                f"## 顶层接口\n\n```systemverilog\n{interface}\n```\n\n"
                f"## 验证边界\n\n{item['coverage']}\n\n" + '\n'.join('- ' + s for s in item['limitations']) + '\n\n'
                f"## 来源与兼容性\n\nhttps://github.com/{repo}/tree/{sources[repo]['revision']}\n\n"
                f"{item['compatibility']}\n\n{license_name}许可；版权及许可原文保留于{prefix}"
                + license_file
                + '，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。\n')
        (data / 'specs').mkdir(exist_ok=True)
        task['specification'] = f'specs/{key}.md'
        (data / task['specification']).write_text(text)
        task['specification_sha256'] = sha256(data / task['specification'])
        for name in task['testbench_files']:
            manifest['support_sha256'][name] = sha256(data / name)
        tasks.append(task)
        print(key, task['category'])
    version = max(version, int(manifest['dataset'].rsplit('-v', 1)[1]))
    manifest.update(dataset=f'project-rtl-{len(tasks)}-v{version}', case_count=len(tasks), tasks=tasks,
                    sources_lock_sha256=sha256(data / 'sources.lock.json'), generation_ready=False,
                    selection_policy='Distinct complete portable multi-module IPs, including matrix compute and packet interconnect. Shared repositories/families must remain together in future splits.')
    save_json(data / 'tasks.json', manifest)


if __name__ == '__main__':
    main()
