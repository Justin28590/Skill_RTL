# SipHash 寄存器外设

SipHash compression and finalization, 128-bit key, 64-bit message words, programmable round configuration and digest readback. Message framing/padding follows the upstream API.

## 交付与时序契约

同步低有效复位。KEY0/MI0为最低32位；SipHash消息填充及末尾长度字节由调用方准备。INIT初始化，COMPRESS吸收64位消息字，FINALIZE进行最终压缩；参数c在PARAM[3:0]、d在[7:4]，复位0x42（c=2,d=4，对应标准SipHash-2-4）。CONFIG bit0选择64/128位输出模式；WORD0最低32位依次递增。NAME/VERSION/STATUS/PARAM/WORD可读，其余读0。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 寄存器总线共同约定

clk上升沿采样写入，cs=1且we=1写、cs=1且we=0组合读；地址为32位寄存器编号，不是字节偏移。CTRL写命令产生一个时钟周期的内部启动脉冲；软件仅在ready时发下一命令，保持配置与输入数据直至操作完成。无cs/写周期/未定义地址读值为0，无效写忽略。复位时清除数据/控制寄存器，特例默认值见本契约。NAME/VERSION只读常量如下。除PRINCE和SipHash明确低字优先外，多字对象的低地址为最高32位；字内字节序按各算法说明。ready/valid握手不是固定周期延迟，不能在计算尚未完成时报告ready。

### 公开地址/位位置/标识常量

```verilog
localparam ADDR_NAME0        = 8'h00;
localparam ADDR_NAME1        = 8'h01;
localparam ADDR_VERSION      = 8'h02;
localparam ADDR_CTRL         = 8'h08;
localparam CTRL_INIT_BIT     = 0;
localparam CTRL_COMPRESS_BIT = 1;
localparam CTRL_FINALIZE_BIT = 2;
localparam ADDR_STATUS       = 8'h09;
localparam STATUS_READY_BIT  = 0;
localparam STATUS_VALID_BIT  = 1;
localparam ADDR_CONFIG       = 8'h0a;
localparam CONFIG_LONG_BIT   = 0;
localparam ADDR_PARAM        = 8'h0b;
localparam SIPHASH_START_C   = 0;
localparam SIPHASH_SIZE_C    = 4;
localparam SIPHASH_DEFAULT_C = 4'h2;
localparam SIPHASH_START_D   = 4;
localparam SIPHASH_SIZE_D    = 4;
localparam SIPHASH_DEFAULT_D = 4'h4;
localparam ADDR_KEY0         = 8'h10;
localparam ADDR_KEY1         = 8'h11;
localparam ADDR_KEY2         = 8'h12;
localparam ADDR_KEY3         = 8'h13;
localparam ADDR_MI0          = 8'h18;
localparam ADDR_MI1          = 8'h19;
localparam ADDR_WORD0        = 8'h20;
localparam ADDR_WORD1        = 8'h21;
localparam ADDR_WORD2        = 8'h22;
localparam ADDR_WORD3        = 8'h23;
localparam CORE_NAME0        = 32'h73697068;
localparam CORE_NAME1        = 32'h61736820;
localparam CORE_VERSION      = 32'h322e3030;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module siphash(
               input wire           clk,
               input wire           reset_n,
               input wire           cs,
               input wire           we,
               input wire [7 : 0]   addr,
               input wire [31 : 0]  write_data,
               output wire [31 : 0] read_data
              );
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### secworks/siphash/README.md

# SipHash #
Verilog implementation of the SipHash has function.

## Status ##
The core is completed, functionally verified and has been tested in
several FPGAs designs.


## Introduction ##
This is a hardware implementation of the [SipHash short-input
PRF](https://131002.net/siphash/siphash.pdf) written in Verilog 2001.

The implementation is designed as a self contained core that performs
the message block processing including initialization, compression and
finalization operations. The core does not implement the functionality
to divide a message into 64 bit message blocks.

The implementation supports user defined number of
compression as well as finalization rounds. The core supports all
combinations from SipHash-1-1 to SipHash-15-15.

The core is suitable as an application specific SipHash coprocessor
offloading compact 8, 16 or 32 bit processors from hashing, PRF
generation and Message Authentication Code (MAC) processing.

The project includes a testbench that verifies that the core generates
the correct response to the testvectors in Appendix A of the SipHash
paper [1]. The project also includes a simple Makefile for compiling the
core using Icarus Verilog [3].

The core has been implemented in Altera and Xilinx FPGA devices. See
Implementation notes below for more information.

This core is released as open source under a BSD license, see
LICENSE.txt for more information.


### Contact information ##
Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Usage ##

The core accepts 64 bit blocks (mi) of a given message to process. Prior
to processing a key dependent initalization. Initalization is done by
setting the key port (k) and assering the (initalize) flag for at least
one cycle and then deassert the flag.

There is default number of SipRounds for compression and
finalization. The default values corresponds to the SipHash-2-4
described in the SipHash paper.

Processing a message block is done by assigning the block to the message
block port (mi) and asserting the (compress) flag.

Note that the core does not know the length of the message and does not
perform final padding. The user of the core is expected to perform
padding including setting length of the message in the final block.

After all blocks in the message has been processed the processing is
completed by asserting the (finalize) flag for one cycle.

The core will assert the (siphash_word_valid) flag when the new SipHash
word for the message is ready.

The core will only accept new commands (initialize, compress, finalize)
when the (ready) flag is asserted.


## Implementation notes ##

The core is implemented using the Verilog 2001 hardware description
language. The core uses synchronous reset for all registers and all
registers are equipped with write enable. The core should integrate and
build cleanly into any standard FPGA project.

The core implements the SipRound function with four 64 bit adders capable
of performing operations in parallel. A single SipRound operation takes
one cycle to perform.

Total latency for processing a message that consists of a single 64 bit
block using SipHash-2-4 is:

 - 1 cycle for initialization
 - 1 + 2 + 1 = 4 cycles for compression
 - 4 + 1 = 5 cycles for finalization
 - 1 + 4 = 5 cycles more for long mode

In total: 10 cycles or 1.25 cycles/Byte.
For long mode 15 cycles or 1.875 cycles/Byte.
For long messages, the latency is asymptotically 0.5 cycles/Byte.


The repo contains both the core itself ([siphash_core.v](https://github.com/secworks/siphash/blob/master/src/rtl/siphash_core.v)) and
a top level wrapper
([siphash.v](https://github.com/secworks/siphash/blob/master/src/rtl/siphash.v)). The
wrapper provides a simple 32-bit interface for the core for easy
integration into a system on chip.


## FuseSoC
This core is supported by the
[FuseSoC](https://github.com/olofk/fusesoc) core package manager and
build system. Some quick  FuseSoC instructions:

install FuseSoC
~~~
pip install fusesoc
~~~

Create and enter a new workspace
~~~
mkdir workspace && cd workspace
~~~

Register siphash as a library in the workspace
~~~
fusesoc library add siphash /path/to/siphash
~~~

...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add siphash https://github.com/secworks/siphash
~~~

To run lint
~~~
fusesoc run --target=lint secworks:crypto:siphash
~~~

Run tb_siphash testbench
~~~
fusesoc run --target=tb_siphash secworks:crypto:siphash
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_siphash --tool=modelsim secworks:crypto:siphash
~~~

List all targets
~~~
fusesoc core show secworks:crypto:siphash
~~~

## Implementation results ##

### Altera FPGAs ###

**Altera Cyclone V**

- Specific device: 5CGXFC7D6F31C7
- ALMs: 657
- Regs: 867
- No memory blocks, DSPs allocated
- 116 MHz max, slow 85c model


**Altera Cyclone IV E**

- Specific device: EP4CE6F17C6
- LEs: 1576
- Regs: 794
- No memory blocks, DSPs allocated
- 101 MHz max, slow 85c model


### Xilinx FPGAs ###

**Spartan-6**
- xc6slx75-3fgg676
- 1235 LUTs
- 345 Slices
- 793 regs
- 114 MHz

**Artix-7**
- xc7a200t-3fbg484
- 998 LUTs
- 432 Slices
- 789 regs
- 173 MHz


## References ##

[1] J-P. Aumasson, D. J. Bernstein. SipHash: a fast short-input PRF.

  - SipHash Project: https://131002.net/siphash/
  - Siphash Paper:


[3] Icarus Verilog

  - http://iverilog.icarus.com/

