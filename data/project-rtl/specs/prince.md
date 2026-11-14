# PRINCE 加解密寄存器外设

64-bit PRINCE blocks with 128-bit keys, encryption/decryption, registered control and 32-bit software interface.

## 交付与时序契约

异步低有效复位。NEXT=CTRL bit0；CONFIG bit0 encdec=1加密、0解密。KEY0与BLOCK0是最低32位，RESULT0也为最低32位（不同于大端地址序的其他Secworks核）。64位PRINCE块、128位密钥，执行原始完整轮数。除NAME/VERSION/STATUS/RESULT之外读取为0。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 寄存器总线共同约定

clk上升沿采样写入，cs=1且we=1写、cs=1且we=0组合读；地址为32位寄存器编号，不是字节偏移。CTRL写命令产生一个时钟周期的内部启动脉冲；软件仅在ready时发下一命令，保持配置与输入数据直至操作完成。无cs/写周期/未定义地址读值为0，无效写忽略。复位时清除数据/控制寄存器，特例默认值见本契约。NAME/VERSION只读常量如下。除PRINCE和SipHash明确低字优先外，多字对象的低地址为最高32位；字内字节序按各算法说明。ready/valid握手不是固定周期延迟，不能在计算尚未完成时报告ready。

### 公开地址/位位置/标识常量

```verilog
localparam ADDR_NAME0        = 8'h00;
localparam ADDR_NAME1        = 8'h01;
localparam ADDR_VERSION      = 8'h02;
localparam ADDR_CTRL         = 8'h08;
localparam CTRL_NEXT_BIT     = 0;
localparam ADDR_STATUS       = 8'h09;
localparam STATUS_READY_BIT  = 0;
localparam ADDR_CONFIG       = 8'h0a;
localparam CONFIG_ENCDEC_BIT = 0;
localparam ADDR_KEY0         = 8'h10;
localparam ADDR_KEY3         = 8'h13;
localparam ADDR_BLOCK0       = 8'h20;
localparam ADDR_BLOCK1       = 8'h21;
localparam ADDR_RESULT0      = 8'h30;
localparam ADDR_RESULT1      = 8'h31;
localparam CORE_NAME0        = 32'h7072696e;
localparam CORE_NAME1        = 32'h63652020;
localparam CORE_VERSION      = 32'h302e3130;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module prince(
              
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

### secworks/prince/README.md

# prince
The Prince lightweight block cipher in Verilog.

## Status
Core is functionally completed. Both core and top level provides correct
results for all test vectors. The core is lint clean. The core has been
implemented in hardware.


## Introduction
[Prince](https://eprint.iacr.org/2012/529.pdf) is a lightweight, low
latency block cipher suitable for Iot and embedded systems. The key is
128 bits and the block size is 64 bits.

### Contact information ##

Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Implementation details
The implementation is currently a pipelined designs with three pipeline
stages. With a cycle to initalize the state and a cycle for latching the
result the latency is five cycles. The design does not use any RAM
blocks nor DSPs.


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

Register prince as a library in the workspace
~~~
fusesoc library add prince /path/to/prince
~~~
...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add prince https://github.com/secworks/prince
~~~

Run tb_prince testbench
~~~
fusesoc run --target=tb_prince secworks:crypto:prince
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_prince --tool=modelsim secworks:crypto:prince
~~~


## Implementation results

### Altera Cyclone V
* Device: 5CGXFC7C7F23C8
* Tool version: Intel Quartus Prime 19.1
* ALMs: 993
* Regs: 716
* Fmax: 102 MHz

### Xilinx Artix-7
* Device: xc7a200tsbv484-2
* Tool version: Vivado 2019.2
* LUTs: 1587
* FFs: 646
* Fmax: 150 MHz

