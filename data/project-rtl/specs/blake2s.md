# BLAKE2s 散列寄存器外设

BLAKE2s compression and complete-message control; message byte count and final-block handling; G-function datapath and message selection.

## 交付与时序契约

同步低有效复位。32字节BLAKE2s输出，BLOCKLEN为本块有效字节数（7位，0..64）。INIT初始化，UPDATE处理非末块，FINISH处理末块并设置最终块语义；先等ready再给下一命令。BLOCK寄存器高索引排列不改变BLAKE2s标准小端字节解释；低地址字承载消息最前4字节，按大端打包到总线字（例如字节00,01,02,03写0x00010203），核内进行字节序转换。只有NAME/VERSION/STATUS/DIGEST提供读值，其他读为0。

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
localparam CTRL_UPDATE_BIT  = 1;
localparam CTRL_FINISH_BIT  = 2;
localparam ADDR_STATUS      = 8'h09;
localparam STATUS_READY_BIT = 0;
localparam ADDR_BLOCKLEN    = 8'h0a;
localparam ADDR_BLOCK0      = 8'h10;
localparam ADDR_BLOCK15     = 8'h1f;
localparam ADDR_DIGEST0     = 8'h40;
localparam ADDR_DIGEST7     = 8'h47;
localparam CORE_NAME0   = 32'h626c616b;
localparam CORE_NAME1   = 32'h65327320;
localparam CORE_VERSION = 32'h302e3830;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module blake2s(
               input wire           clk,
               input wire           reset_n,

               input wire           cs,
               input wire           we,

               input wire  [7 : 0]  address,
               input wire  [31 : 0] write_data,
               output wire [31 : 0] read_data
              );
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### secworks/blake2s/README.md

[![build-openlane-sky130](https://github.com/secworks/blake2s/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/secworks/blake2s/actions/workflows/ci.yml)

# blake2s
Verilog implementation of the [BLAKE2s](https://blake2.net/) hash function.


## Implementation status
Implementation completed. Functionally correct. Functionally verified in
real hardware.  *Ready for use*.


## Introduction
BLAKE2s is 32-bit,  embedded- and hardware-oriented version of the BLAKE2 hash
function. See the [BLAKE2 paper](https://blake2.net/blake2.pdf) for more
information. Additionally, [RFC
7693](https://tools.ietf.org/html/rfc7693) contains a good description,
a reference model and a test vecrtor.

BLAKE2s operates on 32-bit words and produces digests of up to
32 bytes. This version of BLAKE2s always generates a 32 byte (i.e. 256
bit) digest.

This repository contains a forked version of the BLAKE2s reference model
by  Markku-Juhani O. Saarinen that appears in [RFC 7693](https://www.rfc-editor.org/rfc/rfc7693.html).
The original repository [can be found
here](https://github.com/mjosaarinen/blake2_mjosref). The forked version
contains additional test cases that checks corner cases. The forked
version has also been instrumented to display internal values during
processing. The model has been used to drive the functional
verification of the core.


### Contact information ##
Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Operation
The core API follows the description in the BLAKE2s paper and the RFC,
with separate calls to init(), update() and finish() the
processing. (Note that finish() is called final() in the paper and the
RFC, but final() is a reserved word in Verilog).

One must always perform a init() operation separately, before any
update() or finish() operations. One must also always perform a finish()
operation to get the final digest.

For messages smaller than a single 64 byte block, update() should not be
called. Instead finish() should be called. It is the callers
responsibility to set the blocklength to indicate the number of
bytes. (A possible future improvement is to assume that the block size
is 64 bytes for all blocks processed using the update() operation.)

For messages spanning more than one block, perform as many update()
operations as there are complete blocks and then a single final()
operation.


### FuseSoC
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

Register blake2s as a library in the workspace
~~~
fusesoc library add blake2s /path/to/blake2s
~~~

...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add blake2s https://github.com/secworks/blake2s
~~~

To run lint
~~~
fusesoc run --target=lint secworks:crypto:blake2s
~~~

Run tb_blake2s testbench
~~~
fusesoc run --target=tb_blake2s secworks:crypto:blake2s
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_blake2s --tool=modelsim secworks:crypto:blake2s
~~~

List all targets
~~~
fusesoc core show secworks:crypto:blake2s
~~~


## Performance
A single block is processed in 24 cycles. Of these 20 cycles is for the 10
rounds. The init() operation takes two cycles, and the finish()
operation takes two additional cycles besides 24 cycles for the final
block processing. This means that for long messages, the core will take
0.375 cycles/byte.


## Implementation details
The core is a high speed, big, yet iterative implemenatation. It will
perform 10 rounds in sequence. But the core contains four G_function
instantiations and can perform a round in two cycles.

For more compact implementations, the core can be restructured to use
two or just a single, shared G_function.

The G_function itself is purely combinational logic, with no registers
and no sharing of operations. For higher clock frequency, and/or a more
compact implementation the G_function can be rewored to be pipelined and
to share for example the adders. Note that this will have a big impact
on the number of cycles required to process a block. Also the core
itself will have to be updated to handle G_function latency beyond the
currently expected one cycle latency.

Note that there is no separate ports for key and key length.

It is the callers responsibility to clear the unused bits in block
containing less than 64 bytes. This holds for both the blake2s_core
module and the blake2s top level wrapper. For the latter, this means
writing one or more 32-bit all zero words.

The core calculate message length based on the number of bytes given
with each block. The core will also handle the last block as defined by
the paper and the RFC.

The message block buffer in blake_m_select.v is not mapped into a
specific memory macro, and may be implemented with registers by the
synthesis tool. For an efficient implementation, one would probably want
to to change the implementation to use technology specific memory
blocks.


## Implementation results
Any implementation results provided would be greatly appreciated.


### Xilinx Artix 7 200T-1 ###
- LUTs: 3387
- Regs: 1893
- Fmax: 61 MHz

