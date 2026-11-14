#!/usr/bin/env python3
"""Rebuild the six reviewed additions from fixed archives (no upstream build scripts).

Use --archives DIR for already downloaded <owner>/<repo>/archive.tar.gz, or
--download to explicitly fetch the fixed revisions. Original 20 tasks are retained.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from scripts.expand_compute_dataset import import_sources
from rtlflow.chisel import elaborate_chisel, reference_sources
from rtlflow.project import masked, scope_ports
from rtlflow.project_dataset import reference_compatibility, save_json, sha256

SOURCES = {
 'alexforencich/verilog-uart': ('1b867e53af738e4a8bc7c839ca2f1c07f40382dc', ['README.md','COPYING','rtl/uart.v','rtl/uart_rx.v','rtl/uart_tx.v']),
 'alexforencich/verilog-axis': ('48ff7a7e2ef782cf778d47910cf85835c64b1bce', ['README.md','COPYING','rtl/axis_fifo_adapter.v','rtl/axis_fifo.v','rtl/axis_adapter.v']),
 'pConst/basic_verilog': ('2654273b2c4e556a98e806f3a19b52c9b3c74614', ['README.md','spi_master.sv','edge_detect.sv','reverse_vector.sv','uart_debug_printer.sv','uart_tx.sv']),
 'schoeberl/chisel-examples': ('4440f6ca77f6b64ed903bd1892f7870c42896e11', ['README.md','LICENSE','build.sbt','src/main/scala/uart/uart.scala','src/main/scala/fifo/Fifo.scala','src/main/scala/fifo/DoubleBufferFifo.scala']),
}
ARCHIVE_SHA256 = {
 'alexforencich/verilog-uart': 'a8d3432f4a921cf204bbc8a034c1fb00faf173ad56047568995b39d1b50f5727',
 'alexforencich/verilog-axis': '92d714f9a4711491375c3794d5916860cffc776d91fb4b8c548f4cbd4c562aff',
 'pConst/basic_verilog': '63cb468458e21ab3f46b89dd7a3c22e78b939076d63d6e7d87e428f34016e28d',
 'schoeberl/chisel-examples': '4e6633941ca016f55c692768c06b4c6e76b84b9b13b6eb9d32eb4171e031e2e3',
}
# IDs denote distinct IPs, not language translations or extra parameter configurations.
ADDITIONS = [
 ('uart_axis','alexforencich/verilog-uart','verilog','uart',['rtl/uart.v','rtl/uart_rx.v','rtl/uart_tx.v'],
  'AXI-Stream 全双工 UART', '同步高有效复位rst。8位默认数据宽度，8N1、LSB先传。prescale为位周期的1/8，调用方保持稳定且非零。TX/RX独立ready/valid接口，发送方持有数据直到握手。RX只有有限缓冲，消费端应及时接收；报告溢出和停止位错误。完整实现公开参数及收发模块。测试prescale=2、16个双向字节及停止位；未穷举错误帧。', 'txd', "1'b1", None),
 ('axis_fifo_adapter','alexforencich/verilog-axis','verilog','axis_fifo_adapter',['rtl/axis_fifo_adapter.v','rtl/axis_fifo.v','rtl/axis_adapter.v'],
  'AXI-Stream 位宽转换缓冲项目', '同步高有效复位。实现带FIFO的AXI-Stream宽度转换，低有效字节先打包，保留tkeep/tlast/tid/tdest/tuser及ready/valid背压；阻塞时输出稳定。实现公开参数、帧控制和状态接口。基线DEPTH=64、8→32位、ID/DEST启用、其他默认，覆盖256字节/16帧、输入空隙及输出背压；不代表所有参数组合验证。', 'm_axis_tdata', "32'h0", None),
 ('sv_spi','pConst/basic_verilog','systemverilog','spi_master',['spi_master.sv','edge_detect.sv','reverse_vector.sv'],
  'SystemVerilog SPI 命令/读写控制器', '同步低有效nrst。spi_clk是同步分频输入，每半周期至少2个系统周期。命令上升沿锁存mosi_data；写命令只发送，读命令先发送命令字再采样MISO。默认8位MSB先行、CPOL=0；CPOL=1反转时钟。ncs低有效，oe在发送阶段为1。数据在SPI下降沿更新、上升沿采样。支持公开参数，不在busy时发新命令。基线测试mode0两次写、全0/全1读；未穷举其他模式和宽度。', 'mosi_pin', "1'b0", None),
 ('sv_uart_printer','pConst/basic_verilog','systemverilog','uart_debug_printer',['uart_debug_printer.sv','uart_tx.sv'],
  'SystemVerilog UART 调试记录打印项目', 'anrst异步低有效。empty=0时读取一条记录；r_rnw为1输出R否则W，地址与数据各32位高半字优先，格式为R/W、空格、四位大写十六进制、下划线、四位十六进制、空格、同格式数据、CR，共22字符。输入记录保持到r_req脉冲，之后可更新下一条。8N1串口。原件自行定义SIMULATION，仿真位周期固定10系统周期；综合时使用CLK_HZ/BAUD。基线验证两条完整记录及确认脉冲；不验证中途复位时内置TX行为。', 'uart_txd', "1'b1", None),
 ('chisel_uart_echo','schoeberl/chisel-examples','chisel','Echo',['src/main/scala/uart/uart.scala'],
  'Chisel UART 接收/缓冲/回送项目', '包uart，类Echo(frequency: Int, baudRate: Int)，固定构造Echo(800,100)。生成顶层Echo，clock及同步高有效reset，io_rxd/io_txd各1位。接收8位LSB先行串口，经单字节缓冲回送，TX采用1起始、8数据、2停止位，每位8个系统周期。RX有两级同步；不得直接组合连通RX/TX。调用方为有限缓冲留足间隔。基线16个独立字节及停止位检查；不是通用高吞吐UART性能测试。', 'io_txd', "1'b1", [{'module':'Echo','class':'uart.Echo','args':[800,100]}]),
 ('chisel_double_buffer_fifo','schoeberl/chisel-examples','chisel','DoubleBufferFifo',['src/main/scala/fifo/Fifo.scala','src/main/scala/fifo/DoubleBufferFifo.scala'],
  'Chisel 分级双缓冲流 FIFO 项目', '包fifo，类DoubleBufferFifo[T <: Data](gen: T, depth: Int)，固定UInt(8.W)、depth=8。顶层DoubleBufferFifo，clock及同步高有效reset；io_enq/io_deq均ready/valid/bits接口，bits宽8。四级双缓冲，容量8，支持每周期一字，保持FIFO顺序，阻塞输出保持valid及数据；复位清空。不要求内部类名相同，但保留实际子模块层次。基线填满、1000周期背压、排空与复位；不验证其他宽度/深度。', 'io_deq_bits', "8'hff", [{'module':'DoubleBufferFifo','class':'fifo.DoubleBufferFifo','args':[{'uint_width':8},8]}]),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archives',type=Path)
    group.add_argument('--download',action='store_true')
    args=parser.parse_args()
    data=ROOT/'data/project-rtl'
    manifest=json.loads((data/'tasks.json').read_text())
    lock=json.loads((data/'sources.lock.json').read_text())
    sources={repo: {
        'revision': rev, 'archive_sha256': ARCHIVE_SHA256[repo], 'files': names,
        'license': ('CC-BY-SA-4.0 (README declaration)' if repo.startswith('pConst/')
                    else 'BSD-2-Clause' if repo.startswith('schoeberl/') else 'MIT'),
    } for repo,(rev,names) in SOURCES.items()}
    import_sources(data, lock, args.archives, args.download, sources)
    save_json(data/'sources.lock.json',lock)
    originals=[t for t in manifest['tasks'] if t['id'] not in {a[0] for a in ADDITIONS}]
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp)
        for key,repo,language,top,files,title,note,fault,value,chisel in ADDITIONS:
            prefix='sources/'+repo+'/'
            task={'id':key,'repository':repo,'language':language,'title':title,'description':note,
                'family':repo,'category':'stream' if 'fifo' in key else 'peripheral','scope':'complete_portable_ip_design',
                'target_languages': ['verilog','systemverilog'] if language=='verilog' else [language],
                'design_tops':[top],'rtl_files':[prefix+f for f in files],'top_files':[prefix+files[0]],
                'testbench_files':[f'tests/blackbox/expansion/{key}_tb.sv'],'testbench_tops':['tb'], 'dut_roots':['tb.dut'],
                'include_dirs':[],'defines':[],'dialect':'2012','intake_version':2,
                'required_output':[{'regex':'EXPANSION_PASS '+key,'min_count':1}], 'forbidden_output':['(?i)error|fatal|failed'],
                'negative_forces':[{'target':'tb.dut.'+fault,'value':value}],
                'simulation_timeout_seconds':10,'negative_timeout_seconds':3,
                'documentation':[prefix+'README.md'],'verification_origin':'dataset_authored_black_box',
                'coverage':note,'limitations':['Finite directed/scoreboard tests, not exhaustive or formal proof.'],
                'reference_sources_visible_to_model':False,
                'rtl_source_lines':sum(len((data/(prefix+f)).read_text().splitlines()) for f in files), 'rtl_file_count':len(files)}
            if chisel: task['chisel_tops']=chisel
            rtl=[data/n for n in task['rtl_files']]
            if language == 'systemverilog':
                rtl=[]
                (work/key).mkdir()
                for name in task['rtl_files']:
                    p=work/key/Path(name).name
                    p.write_text(reference_compatibility(task,(data/name).read_text()));rtl.append(p)
            if chisel:
                frontend=elaborate_chisel(reference_sources(data,task),task,work/key,trusted_reference=True)
                if frontend['files'] is None: raise ValueError(json.dumps(frontend,indent=2))
                rtl=[]
                for name,code in frontend['files'].items():
                    p=work/key/name;p.write_text(code);rtl.append(p)
            binary=work/(key+'.vvp')
            proc=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),*[str(p) for p in rtl],str(data/task['testbench_files'][0])],capture_output=True,text=True)
            if proc.returncode: raise ValueError(proc.stderr)
            ports=scope_ports(binary)['tb.dut']['ports']
            if chisel:
                interface='module '+top+'(\n'+',\n'.join('  '+v['direction']+' '+(f'[{v["width"]-1}:0] ' if v['width']>1 else '')+k for k,v in ports.items())+'\n);\nendmodule'
            else:
                code=reference_compatibility(task,(data/task['top_files'][0]).read_text());clean=masked(code)
                start=re.search(r'\bmodule\s+'+top+r'\b',clean).start();end=clean.index(');',start)+2
                interface=code[start:end]+'\nendmodule'
            text=f'# {title}\n\n{note}\n\n## 编译配置\n\n原生语言：{language}。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。\n'
            if chisel: text+='固定Scala 2.13.12、Chisel 6.5.0；可信构造配置：`'+json.dumps(chisel)+'`。不要提供App/main、构建脚本或外部RTL。\n'
            text+='\n## 顶层接口\n\n```systemverilog\n'+interface+'\n```\n\n## 项目公开文档\n\n来源：https://github.com/'+repo+'/tree/'+SOURCES[repo][0]+'\n\n参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。\n'
            if repo.startswith('pConst/'):
                text+='\n接口摘录作者 Konstantin Pavlov；原件及本派生接口摘录依 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。构建副本显式补齐parameter关键字；SPI将edge_detect复位端口旧名nrst映射为anrst，不改变顶层端口或数据通路。\n'
            else:
                text+='\n许可：'+lock['sources'][repo]['license']+'，保留原始版权及许可，见数据集LICENSES.md和锁定源码中的LICENSE/COPYING。\n'
            (data/'specs').mkdir(exist_ok=True)
            task['specification']=f'specs/{key}.md'
            (data/task['specification']).write_text(text)
            task['specification_sha256']=sha256(data/task['specification'])
            manifest['support_sha256'][task['testbench_files'][0]]=sha256(data/task['testbench_files'][0])
            originals.append(task)
            print(key,language,len(ports),'ports',flush=True)
    version = 'v' + str(max(int(manifest['dataset'].rsplit('-v', 1)[1]),
                            3 if any(t.get('category') == 'ai_accelerator' for t in originals) else 2))
    manifest.update(dataset=f'project-rtl-{len(originals)}-{version}',case_count=len(originals),tasks=originals,
        sources_lock_sha256=sha256(data/'sources.lock.json'),generation_ready=False,
        generation_blockers=['Pilot set has no frozen dev/test split.'],
        selection_policy='Distinct complete portable multi-module IPs; retain later additions. Shared repositories/families must remain together in future splits.',
        limitations=['Finite reference/candidate tests are not exhaustive proofs.', 'Native source language is distinct from generation target language.', 'Chisel pilot fixes constructor configurations; arbitrary Verilog parameter overrides are not supported.'])
    save_json(data/'tasks.json',manifest)


if __name__=='__main__':main()
