# XTEA 加解密寄存器外设

64-bit XTEA block, 128-bit key, iterative encryption/decryption and a 32-bit register interface. Included as a multi-cycle project, not an endorsement of the cipher.

## 交付与时序契约

异步低有效复位。CONFIG bit0 encdec=1加密、0解密；CTRL bit1 NEXT启动。ROUNDS低6位为轮数，复位32。KEY/BLOCK/RESULT按高32位字优先排列。除NAME/VERSION/STATUS/RESULT之外读0。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 寄存器总线共同约定

clk上升沿采样写入，cs=1且we=1写、cs=1且we=0组合读；地址为32位寄存器编号，不是字节偏移。CTRL写命令产生一个时钟周期的内部启动脉冲；软件仅在ready时发下一命令，保持配置与输入数据直至操作完成。无cs/写周期/未定义地址读值为0，无效写忽略。复位时清除数据/控制寄存器，特例默认值见本契约。NAME/VERSION只读常量如下。除PRINCE和SipHash明确低字优先外，多字对象的低地址为最高32位；字内字节序按各算法说明。ready/valid握手不是固定周期延迟，不能在计算尚未完成时报告ready。

### 公开地址/位位置/标识常量

```verilog
localparam ADDR_NAME0        = 8'h00;
localparam ADDR_NAME1        = 8'h01;
localparam ADDR_VERSION      = 8'h02;
localparam ADDR_CTRL         = 8'h08;
localparam CTRL_NEXT_BIT     = 1;
localparam ADDR_STATUS       = 8'h09;
localparam STATUS_READY_BIT  = 0;
localparam ADDR_CONFIG       = 8'h0a;
localparam CONFIG_ENCDEC_BIT = 0;
localparam ADDR_ROUNDS       = 8'h0c;
localparam ADDR_KEY0         = 8'h10;
localparam ADDR_KEY3         = 8'h13;
localparam ADDR_BLOCK0       = 8'h20;
localparam ADDR_BLOCK1       = 8'h21;
localparam ADDR_RESULT0      = 8'h30;
localparam ADDR_RESULT1      = 8'h31;
localparam CORE_NAME0        = 32'h78746561;
localparam CORE_NAME1        = 32'h2d313238;
localparam CORE_VERSION      = 32'h302e3630;
localparam NUM_ROUNDS        = 32;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module xtea(
            
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

### secworks/xtea/README.md

# xtea
Verilog implementation of the xtea block cipher.

## Status
The core is done and is functionally correct.
(As far as I know.)


## Introduction
[Xtea](https://en.wikipedia.org/wiki/XTEA) is a compact, Feistel based
block cipher designed by Wheeler and Needham in 1997. It has a 64 bit
block and 128 bit key. It has a very simple key scheme but many rounds.


## Implementation details
The core is implemented with two cycles for each round (which is two
Feistel rounds.)



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

Register xtea as a library in the workspace
~~~
fusesoc library add xtea /path/to/xtea
~~~

...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add xtea https://github.com/secworks/xtea
~~~

To run lint
~~~
fusesoc run --target=lint secworks:crypto:xtea
~~~

Run tb_xtea testbench
~~~
fusesoc run --target=tb_xtea secworks:crypto:xtea
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_xtea --tool=modelsim secworks:crypto:xtea
~~~

List all targets
~~~
fusesoc core show secworks:crypto:xtea
~~~


### Implementation Results
#### Xilinx Artix-7
Device: xc7a200t

Package: fbg484

Speed: -3


Slice registers: 298

Slice LUTs: 552

Occupied Slices: 181

Clock frequency: 177 MHz

