# SHA-1 多块散列外设

160-bit SHA-1 digest; 512-bit block input; initialization and continuation; 32-bit register API. Caller supplies padding.

## 交付与时序契约

异步低有效复位。调用方完成SHA-1消息填充；16个32位大端字组成512位块。INIT启动首块并载入标准IV，NEXT延续中间散列状态。STATUS[1:0]={digest_valid,ready}。BLOCK可读回，CTRL返回{next,init}，DIGEST按高字到低字输出。

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
localparam STATUS_VALID_BIT = 1;
localparam ADDR_BLOCK0    = 8'h10;
localparam ADDR_BLOCK15   = 8'h1f;
localparam ADDR_DIGEST0   = 8'h20;
localparam ADDR_DIGEST4   = 8'h24;
localparam CORE_NAME0     = 32'h73686131;
localparam CORE_NAME1     = 32'h20202020;
localparam CORE_VERSION   = 32'h302e3630;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module sha1(
            
            input wire           clk,
            input wire           reset_n,

            
            input wire           cs,
            input wire           we,

            
            input wire  [7 : 0]  address,
            input wire  [31 : 0] write_data,
            output wire [31 : 0] read_data,
            output wire          error
           );
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### secworks/sha1/README.md

sha1
====
Verilog implementation of the SHA-1 cryptgraphic hash function.

## Implementation status ##
The core has been completed and been used in several designs. It is
considered mature and ready to use.. Minor changes are non-functional
cleanups of code.


## Introduction ##
Verilog implementation of the SHA-1 cryptgraphic hash function. The
functionality follows the specification in NIST FIPS 180-4.

The implementation is iterative with one cycle/round. The initialization
takes one cycle. The W memory is based around a sliding window of 16
32-bit registers that are updated in sync with the round processing. The
total latency/message block is 82 cycles.

There are top level wrappers that provides interface for easy
integration into a System on Chip (SoC). This interface contains mesage
block and digest registers to allow a host to load the next block while
the current block is being processed.

The implementation also includes a functional model written in Python.


### Contact information ##
Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Implementation details ##

The sha1 design is divided into the following sections.
- src/rtl - RTL source files
- src/tb  - Testbenches for the RTL files
- src/model/python - Functional model written in python
- doc - documentation (currently not done.)
- toolruns - Where tools are supposed to be run. Includes a Makefile for
building and simulating the design using [Icarus Verilog](http://iverilog.icarus.com/)

The actual core consists of the following files:
- sha1_core.v - The core itself with wide interfaces.
- sha1_w_mem.v - W message block memort and expansion logic.

The top level entity is called sha1_core. This entity has wide
interfaces (512 bit block input, 160 bit digest). In order to make it
usable you probably want to wrap the core with a bus interface.

Unless you want to provide your own interface you therefore also need to
use a top level wrapper. There is one wrapper provided:
- sha1.v - A wrapper with a 32-bit memory like interface.

The core (sha1_core) will sample all data inputs when given the init
or next signal. the wrappers provided contains additional data
registers. This allows you to load a new block while the core is
processing the previous block.


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

Register sha1 as a library in the workspace
~~~
fusesoc library add sha1 /path/to/sha1
~~~
...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add sha1 https://github.com/secworks/sha1
~~~

Run tb_sha1 testbench
~~~
fusesoc run --target=tb_sha1 secworks:crypto:sha1
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_sha1 --tool=modelsim secworks:crypto:sha1
~~~

## FPGA-results ##

### Altera Cyclone FPGAs ###
Implementation results using Altera Quartus-II 13.1.

**Altera Cyclone IV E**
- EP4CE6F17C6
- 2913 LEs
- 1527 regs
- 107 MHz

**Altera Cyclone IV GX**
- EP4CGX22CF19C6
- 2814 LEs
- 1527 regs
- 105 MHz

**Altera Cyclone V**
- 5CGXFC7C7F23C8
- 1124 ALMs
- 1527 regs
- 104 MHz


### Xilinx FPGAs ###
Implementation results using ISE 14.7.

**Xilinx Spartan-6**
- xc6slx45-3csg324
- 1589 LUTs
- 564 Slices
- 1592 regs
- 100 MHz

