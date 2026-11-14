#!/usr/bin/env python3
"""Add pinned floating-point, DMA, scratchpad and CDC IPs; no model/upstream builds.

Use --download for explicit network access, or --archives DIR containing
<owner>/<repo>/archive.tar.gz. Existing tasks and shared-source files are retained.
Then run prepare_project_generation.py and regenerate all verification evidence.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.expand_compute_dataset import ROOT, import_sources, install_additions, save_json

SOURCES = {
    'bsg-external/HardFloat': {
        # Initial upstream Release 1 import, before the fork acquired BSG dependencies.
        'revision': 'bf579553c927092650f5976d8da573af1ac64741',
        'archive_sha256': 'bc85ad4f3c640874738e3ea82b09a90fd35e2bc466c19f4e62f6efcdb034fe68',
        'license': 'BSD-3-Clause', 'license_file': 'COPYING.txt', 'readme': 'README.txt',
        'files': ['README.txt', 'COPYING.txt', 'doc/HardFloat-Verilog.html',
                  'source/mulAddRecFN.v', 'source/HardFloat_rawFN.v', 'source/HardFloat_primitives.v',
                  'source/isSigNaNRecFN.v', 'source/HardFloat_consts.vi', 'source/HardFloat_localFuncs.vi',
                  'source/RISCV/HardFloat_specialize.vi'],
    },
    'alexforencich/verilog-axi': {
        'revision': '516bd5dadc3365b7f9e225d2af8fe0b8d804fe53',
        'archive_sha256': '4aaed32673e91a2174ec8e29ee11cc5ef48e00bf01e959b040615f89839e095d',
        'files': ['README.md', 'COPYING', 'rtl/axi_dma.v', 'rtl/axi_dma_rd.v', 'rtl/axi_dma_wr.v',
                  'rtl/axi_dp_ram.v', 'rtl/axi_ram_wr_rd_if.v', 'rtl/axi_ram_rd_if.v', 'rtl/axi_ram_wr_if.v'],
    },
    'alexforencich/verilog-axis': {
        'revision': '48ff7a7e2ef782cf778d47910cf85835c64b1bce',
        'archive_sha256': '92d714f9a4711491375c3794d5916860cffc776d91fb4b8c548f4cbd4c562aff',
        'files': ['README.md', 'COPYING', 'rtl/axis_async_fifo_adapter.v', 'rtl/axis_async_fifo.v', 'rtl/axis_adapter.v'],
    },
}
ADDITIONS = [
    {
        'id': 'fp32_fma', 'repository': 'bsg-external/HardFloat', 'top': 'mulAddRecFN',
        'files': ['source/mulAddRecFN.v', 'source/HardFloat_rawFN.v', 'source/HardFloat_primitives.v', 'source/isSigNaNRecFN.v'],
        'include_dirs': ['source', 'source/RISCV'],
        'title': 'IEEE binary32 融合乘加与舍入/异常处理核', 'category': 'floating_point_compute',
        'description': '完整FMA：操作数解码、乘加/对齐、消去后的规格化、单次舍入和IEEE异常标志；组合核，无时钟。',
        'interface': '''module mulAddRecFN #(parameter expWidth=8, parameter sigWidth=24)(
  input [0:0] control, input [1:0] op,
  input [expWidth+sigWidth:0] a, b, c,
  input [2:0] roundingMode,
  output [expWidth+sigWidth:0] out, output [4:0] exceptionFlags
);
endmodule''',
        'behavior': '''公开顶层为mulAddRecFN；expWidth为指数位数、sigWidth为含隐藏位的有效位数；本任务默认参数8/24，即binary32。上游3/3占位默认在Icarus独立展开时有非法part-select，参考TB显式覆写为8/24，交付顶层默认也应为8/24。
输入/输出采用HardFloat recFN，不是直接32位IEEE编码。E=expWidth、P=sigWidth；总宽E+P+1，最高位为符号，随后E+1位指数r和P-1位小数f。
对于IEEE正常数，r=IEEE指数+2^(E-1)+1，f不变；对于非零次正规数，把原小数左移n位使隐藏位到bit(P-1)，r=2^(E-1)+2-n，f取移位后低P-1位。
r的最高3位为000表示零、110为无穷、111为NaN；特殊值不用位字段不要求特定值。NaN小数最高位1为quiet、0为signaling，输入只允许合法recFN编码。
结果按(-1)^op[1]*(a*b)+(-1)^op[0]*c计算：00加、01减c、10负乘积加c、11负乘积减c。
**融合**乘加只在最终结果舍入，禁止先把乘积舍入到binary32再相加。
roundingMode：0最近偶数、1向零、2向负无穷、3向正无穷、4最近且中点远离零、6 round-to-odd（非精确结果最低有效位置1），5/7不属于合法配置。
control=0在舍入前检测tininess，1在舍入后检测；基线为1。舍入后tininess依据目标精度、无限指数范围下的舍入结果，不简单等同于最终编码为次正规数。
exceptionFlags[4:0]={invalid,infinite/divide-by-zero,overflow,underflow,inexact}；本核不执行除法，bit3为0。
支持±0、正常数、次正规数、无穷、quiet/signaling NaN。无效包括sNaN、0×无穷和相反符号无穷相加；使用RISC-V特化的正号默认quiet NaN，binary32解码后为0x7fc00000，不传播payload。
精确抵消为零时，向负无穷舍入产生-0，其他模式为+0；同号零相加保留符号。无时钟/复位/ready，输入稳定后组合结果有效。
必须交付真正的乘加/规格化/舍入子模块及本地头文件，不允许调用软件浮点或嵌入测试向量答案。保留公开参数；基线只验证binary32配置。''',
        'coverage': '3432组：15组定向+128组固定种子随机三元组，分别遍历4种op和6种舍入；独立Python Fraction整数/有理数oracle核对binary32结果和5位异常，含融合消去、tie、次正规、上下溢、符号零及NaN/Inf。',
        'limitations': ['Only expWidth=8/sigWidth=24 and tininess-after are tested; no exhaustive IEEE certification or other precision claims.',
                        'Combinational arithmetic block only, not a pipelined vector FPU or full tensor processor.'],
        'required_output': [{'regex': 'MODERN_PASS fp32_fma vectors=3432', 'min_count': 1}],
        'negative_forces': [{'target': 'tb.dut.out', 'value': "33'h0"}],
        'compatibility': '参考原版直接编译，使用锁定的RISC-V特化头。候选回放将三个.vi头及include名称映射为.vh；countLeadingZeros内部generate层次连线等价改写为父作用域wire数组。顶层默认特化为本任务的8/24以支持独立编译；参考配置本身也是8/24。不改变算术，也不放宽候选后缀或跨层引用安全策略。选择未引入外部BSG依赖的Release 1固定导入版本，不声称是最新上游。',
    },
    {
        'id': 'axi_dma_engine', 'repository': 'alexforencich/verilog-axi', 'top': 'axi_dma',
        'files': ['rtl/axi_dma.v', 'rtl/axi_dma_rd.v', 'rtl/axi_dma_wr.v'],
        'title': '双向AXI内存与流式DMA引擎', 'category': 'accelerator_data_movement',
        'description': '描述符驱动的内存→流/流→内存双向DMA，包含突发分割、非对齐处理、字节掩码和完成/错误状态。',
        'behavior': '''clk上升沿，rst同步高有效。读写方向独立；各描述符在valid&&ready时接受，携带字节地址、字节长度和tag；长度大于0。
读方向产生AXI INCR突发，将请求的字节连续打包到AXI-Stream最低字节lane开始，最后一拍tkeep仅低有效字节置1，tlast标记描述符末尾。id/dest/user来自读描述符；完成状态返回tag和错误码。
写方向按描述符地址和最大长度接收stream，tkeep低连续有效字节；在长度耗尽或tlast到达时结束帧，报告实际写入字节数、tag、流id/dest/user及错误。支持长度前的早到tlast；基线使用长度相等的帧。
ENABLE_UNALIGNED=1支持非字对齐地址/长度，0时调用者提供对齐地址；用wstrb保护首/末拍范围外字节。AXI与AXIS总线位宽必须一致，字节数为2的幂。
AXI_MAX_BURST_LEN为1..256；拆分突发且不得跨4KiB边界。各通道在valid&&!ready时保持全部字段稳定，不得忽略背压。
错误状态：0成功、读SLVERR=4/DECERR=5、写SLVERR=6/DECERR=7；状态没有ready输入，valid为完成指示。read_enable/write_enable控制接受描述符，write_abort用于终止在途写；中止细节未纳入本轮测试。
ENABLE_SG必须为0，上游未实现scatter/gather，不能宣称支持。基线AXI/AXIS均32位、地址16位、tag/ID/dest各8位、LEN_WIDTH=16、USER=1，AXI_MAX_BURST_LEN=4，ID/DEST与非对齐开启。
完整实现公开读写引擎及本地依赖，不提供外部RAM模型或预置传输结果。''',
        'coverage': '24读+24写描述符并行运行，长度1..129、全部字节偏移、4KiB边界分割、多突发、AXI与stream独立阻塞；逐字节读流/全64KiB写内存scoreboard，核对首尾strobe、last、ID/dest/user、tag/长度及SLVERR/DECERR状态。',
        'limitations': ['No scatter/gather; abort, early TLAST, zero-length descriptors and mid-transfer reset are not tested.',
                        'Only 32-bit buses/max-burst=4 configuration and one outstanding descriptor per direction in the test driver.'],
        'required_output': [{'regex': 'MODERN_PASS axi_dma_engine read=24 write=24', 'min_count': 1}],
        'negative_forces': [{'target': 'tb.dut.m_axis_read_data_tdata', 'value': "32'h0"}],
        'compatibility': '原版直接编译；候选回放仅去掉静态无效参数诊断，不改DMA数据通路和控制。AXI从设备与期望内存为独立数据集测试模型，不链接上游RAM。',
    },
    {
        'id': 'axi_scratchpad', 'repository': 'alexforencich/verilog-axi', 'top': 'axi_dp_ram',
        'files': ['rtl/axi_dp_ram.v', 'rtl/axi_ram_wr_rd_if.v', 'rtl/axi_ram_rd_if.v', 'rtl/axi_ram_wr_if.v'],
        'title': '双端口AXI片上共享存储与读写仲裁', 'category': 'accelerator_memory',
        'description': '两个独立时钟域的AXI端口共享RAM，含各端口读写协议引擎、仲裁与可选输出流水级；适合作为scratchpad构件。',
        'behavior': '''两个AXI slave端口A/B共享同一字节可寻址RAM，分别使用a_clk/a_rst与b_clk/b_rst，复位均同步高有效。
各端口接受AW/W/B与AR/R通道，保留ID、burst长度/size、WSTRB和RLAST语义，响应OKAY。支持FIXED与INCR；WRAP、exclusive、原子操作不在契约范围。
数据低字节对应低地址，WSTRB按byte lane更新，未使能字节保持不变。同一端口读写需要内部仲裁，A_INTERLEAVE/B_INTERLEAVE控制是否按拍交织；PIPELINE_OUTPUT为0/1控制输出寄存级。
背压时保持响应valid、ID、data、resp、last。接口复位清除事务状态但不清空已写RAM；不要依赖上电未写内存值。
禁止并发访问引起的同地址读写或双写冲突，跨端口同地址的可见性在先前写事务完成后检查；不保证冲突结果，也不是cache-coherent存储。
基线ADDR_WIDTH=12（4KiB）、DATA_WIDTH=32、ID_WIDTH=4、A/B输出流水为1/0、INTERLEAVE均1，时钟周期10/14。
必须交付双端口共享存储和完整协议/仲裁子模块，不能用两个不相干的私有内存替代。''',
        'coverage': '33个16拍写突发，576拍读回；全部字节先通过公开接口初始化，之后全/零/部分WSTRB覆盖；双端口并发、跨端口读回、单端口同时读写非冲突区域、B/R阻塞稳定性、ID/RLAST及接口复位后的数据保留。',
        'limitations': ['Only aligned full-width INCR bursts in 4KiB/32-bit configuration; no narrow/FIXED burst, collision or atomic/coherence verification.',
                        'Digital two-clock simulation is not physical CDC/metastability or SRAM macro sign-off.'],
        'required_output': [{'regex': 'MODERN_PASS axi_scratchpad reads=576 writes=33', 'min_count': 1}],
        'negative_forces': [{'target': 'tb.dut.s_axi_b_rdata', 'value': "32'h0"}],
        'compatibility': '原版直接编译；候选回放仅去掉静态无效参数诊断。测试不窥探内部RAM，只检查公开AXI端口。',
    },
    {
        'id': 'axis_async_bridge', 'repository': 'alexforencich/verilog-axis', 'top': 'axis_async_fifo_adapter',
        'files': ['rtl/axis_async_fifo_adapter.v', 'rtl/axis_async_fifo.v', 'rtl/axis_adapter.v'],
        'title': '异步时钟域流桥接、帧FIFO与位宽转换', 'category': 'clock_domain_streaming',
        'description': '输入/输出位宽转换和异步帧FIFO，包含跨域指针同步、背压与坏帧丢弃；不是把同步FIFO换一个名称。',
        'behavior': '''s_clk/s_rst与m_clk/m_rst分别控制输入/输出时钟域。复位协调施加于两侧，释放后允许同步延迟；复位清空在途数据/未完成帧。独立单侧复位行为未纳入本契约验证。
两侧均为AXI-Stream握手，阻塞时保持所有字段。按低字节lane顺序组包/拆包；保留tkeep/tlast及启用的ID/dest/user。
S/M_DATA_WIDTH均为相同byte lane位宽的整数倍，lane数比例为整数；KEEP关闭时该侧视作单lane。
FRAME_FIFO=1时完整帧提交后才对输出可见，未完成帧不能泄漏。DEPTH按输入byte lane单位计数，RAM侧深度向上取2的幂；正常满状态应背压。
DROP_BAD_FRAME=1按帧末USER_BAD_FRAME_MASK/VALUE标记丢弃整帧，s_status_bad_frame脉冲计数；DROP_OVERSIZE_FRAME处理超深度帧，DROP_WHEN_FULL可选择满时丢弃。上述drop参数约束必须满足原公开声明，不能无条件吞掉正确帧。
PAUSE_ENABLE启用后响应s/m_pause_req并反馈ack，FRAME_PAUSE决定只在帧间暂停；本轮pause关闭。
基线DEPTH=64，8→32位，keep启用，4位ID/dest，1位user，FRAME_FIFO=1、DROP_BAD_FRAME=1、DROP_OVERSIZE_FRAME=1、DROP_WHEN_FULL=0，其他参数默认。
源端在一帧内保持ID/dest，坏帧user只在末拍标记。必须有真正跨时钟域存储/同步逻辑，不允许直接组合连通。''',
        'coverage': '两套时钟半周期3/5与7/4，各48帧、长度1..17，各输出41好帧/丢弃7坏帧；输入快/输出快、长时间阻塞到满、宽度打包和部分末拍、逐字节/ID/dest/last检查、阻塞稳定性、协调复位丢弃未完成帧。',
        'limitations': ['Digital functional CDC simulation only; not a metastability, timing-constraint or formal CDC proof.',
                        'No single-sided reset, oversize/drop-when-full, pause or arbitrary-width configuration coverage.'],
        'dut_roots': ['tb.fast_in.dut', 'tb.fast_out.dut'],
        'required_output': [{'regex': f'MODERN_PASS axis_async_bridge clocks={s}/{m} good=41 bad=7', 'min_count': 1} for s,m in ((3,5),(7,4))],
        'negative_forces': [{'target': 'tb.fast_in.dut.m_axis_tdata', 'value': "32'h0"}],
        'compatibility': '原版直接编译；候选回放仅去掉静态无效参数诊断，不改Gray指针/同步、帧提交或位宽转换逻辑。',
    },
]
for item in ADDITIONS:
    item['language'] = 'verilog'
    item.setdefault('dut_roots', ['tb.dut'])
    item['testbench'] = 'tests/blackbox/modern/' + item['id'] + '_tb.sv'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archives', type=Path)
    group.add_argument('--download', action='store_true')
    args = parser.parse_args()
    data = ROOT / 'data/project-rtl'
    manifest = json.loads((data / 'tasks.json').read_text())
    lock = json.loads((data / 'sources.lock.json').read_text())
    import_sources(data, lock, args.archives, args.download, SOURCES)
    save_json(data / 'sources.lock.json', lock)
    install_additions(data, manifest, ADDITIONS, SOURCES, version=4)


if __name__ == '__main__':
    main()
