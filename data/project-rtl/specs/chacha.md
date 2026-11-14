# ChaCha 流密码寄存器外设

128/256-bit keys; configurable ChaCha rounds; IV and block counter; consecutive keystream blocks through a 32-bit register API.

## 交付与时序契约

同步低有效复位。KEYLEN=0/1 为128/256位，ROUNDS 为偶数轮数2..30（5位），基线覆盖8/12/20。64位IV和64位块计数，初始计数0。INIT初始化并处理第一个块，NEXT处理下一块并递增计数；DATA_IN与密钥流异或得到DATA_OUT。总线低地址承载最前的字节组，字节以大端打包，核内转换为ChaCha小端字；输出字节也按大端打包。STATUS位1为输出valid。KEY/IV/KEYLEN/ROUNDS可读；实际顶层复位KEYLEN=0、ROUNDS=0，软件必须先写有效轮数，不依赖README中的算法默认值。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 寄存器总线共同约定

clk上升沿采样写入，cs=1且we=1写、cs=1且we=0组合读；地址为32位寄存器编号，不是字节偏移。CTRL写命令产生一个时钟周期的内部启动脉冲；软件仅在ready时发下一命令，保持配置与输入数据直至操作完成。无cs/写周期/未定义地址读值为0，无效写忽略。复位时清除数据/控制寄存器，特例默认值见本契约。NAME/VERSION只读常量如下。除PRINCE和SipHash明确低字优先外，多字对象的低地址为最高32位；字内字节序按各算法说明。ready/valid握手不是固定周期延迟，不能在计算尚未完成时报告ready。

### 公开地址/位位置/标识常量

```verilog
localparam ADDR_NAME0       = 8'h00;
localparam ADDR_NAME1       = 8'h01;
localparam ADDR_VERSION     = 8'h02;
localparam ADDR_CTRL        = 8'h08;
localparam CTRL_INIT_BIT    = 0;
localparam CTRL_NEXT_BIT    = 1;
localparam ADDR_STATUS      = 8'h09;
localparam STATUS_READY_BIT = 0;
localparam ADDR_KEYLEN      = 8'h0a;
localparam KEYLEN_BIT       = 0;
localparam ADDR_ROUNDS      = 8'h0b;
localparam ROUNDS_HIGH_BIT  = 4;
localparam ROUNDS_LOW_BIT   = 0;
localparam ADDR_KEY0        = 8'h10;
localparam ADDR_KEY7        = 8'h17;
localparam ADDR_IV0         = 8'h20;
localparam ADDR_IV1         = 8'h21;
localparam ADDR_DATA_IN0    = 8'h40;
localparam ADDR_DATA_IN15   = 8'h4f;
localparam ADDR_DATA_OUT0   = 8'h80;
localparam ADDR_DATA_OUT15  = 8'h8f;
localparam CORE_NAME0       = 32'h63686163;
localparam CORE_NAME1       = 32'h68612020;
localparam CORE_VERSION     = 32'h302e3830;
localparam DEFAULT_CTR_INIT = 64'h0;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module chacha(
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

### secworks/chacha/README.md

[![build-openlane-sky130](https://github.com/secworks/chacha/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/secworks/chacha/actions/workflows/ci.yml)

chacha
========

Verilog 2001 implementation of the ChaCha stream cipher.

## Status ##
The core is completed and has been implemented and used in several FPGA
designs. The core is for example used as the CSPRNG/DRBG part of the
random number generator (RNG) in the [Cryptech
HSM](https://cryptech.is/).


## Introduction ##
This core implements the [ChaCha stream cipher
(pdf)](https://cr.yp.to/chacha/chacha-20080128.pdf) By Daniel
J. Bernstein (DJB).


### Contact information ##

Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Functionality ##
This core implements ChaCha with support for 128 and 256 bit keys. The
number of rounds can be set from two to 32 rounds in steps of two. The
default number of rounds is eight.

The core contains an internal 64-bit block counter that is automatically
updated for each data block.

There is a [reference model in a separate
repository](https://github.com/secworks/chacha_testvectors) used to
generate and document test vectors. There is also a functional model in
this repo under src/model/python.


## Branch for VHDL interoperability ##
There is a branch
[*vhdl_interop*](https://github.com/secworks/chacha/tree/vhdl_interop)
that changes the port name "next" in *chacha_core.v*. Next is a reserved
word in VHDL. If you are instantiating the core in a mixed language
environment use this branch. This branch will not be merged into
*master*, but will track changes to the *master* branch.


## Performance ##
The core has four separate quarterround modules, which means that
one round takes one cycle. The overhead latency cost when using the top
level wrapper is three, which means that with eight rounds the total
latency is 11 cycles. For ChaCha20 the latency is 23 cycles.

## FuseSoC
This core is supported by the
[FuseSoC](https://github.com/olofk/fusesoc) core package manager and
build system. Some quick  FuseSoC instructions:

Install FuseSoC
~~~
pip install fusesoc
~~~

Create and enter a new workspace
~~~
mkdir workspace && cd workspace
~~~

Register chacha as a library in the workspace
~~~
fusesoc library add chacha /path/to/chacha
~~~
...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add chacha https://github.com/secworks/chacha
~~~

Run tb_chacha testbench
~~~
fusesoc run --target=tb_chacha secworks:crypto:chacha
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_chacha --tool=modelsim secworks:crypto:chacha
~~~

List all targets
~~~
fusesoc core show secworks:crypto:chacha
~~~

## Implementation results##

### Intel Cyclone IV E ###
- Tool: Altera Quartus Prime 15.1
- LEs:  4748
- Regs: 1940
- RAM:     0
- Fmax: 55 MHz


### Intel Cyclone V GX ###
- Tool: Altera Quartus Prime 15.1
- ALMs: 1939
- Regs: 1940
- Ram:     0
- Fmax: 60 MHz


### Microchip IGLOO2 ###
- Tool:   Libero v 12.4
- Device: M2GL150TS-FCV484
- LUTs:   4190
- SLEs:   2028
- BRAMs:  2
- Fmax:   88.4 MHz


### Microchip PolarFire ###
- Tool:   Libero v 12.4
- Device: MPF500TS-FCG784I
- LUTs:   4190
- SLEs:   1992
- BRAMs:  3
- Fmax:   94.4 MHz


### Xilinx Spartan-6 ###
- Tool:   Xilinx ISE 14.7
- Device: xc6slx75-3fgg676
- LUTs:   3843
- Slices: 1049
- Regs:   1994
- BRAM:      0
- Fmax:   83 MHz


### Xilinx Artix-7 ###
- Tool:   Xilinx ISE 14.7
- Device: xc7a200t-3fbg484
- LUTs:   3837
- Slices: 1076
- Regs:   1949
- BRAM:      0
- Fmax:   100 MHz

