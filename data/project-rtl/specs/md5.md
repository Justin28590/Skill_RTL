# MD5 多块散列外设

128-bit MD5 digest, multi-block chaining, busy/ready and 32-bit register interface. Caller supplies padding. MD5 is included for hardware verification, NOT recommended for security.

## 交付与时序契约

异步低有效复位。调用方完成MD5填充，包括小端消息长度。低地址寄存器承载消息首字，每个总线字直接是MD5小端运算字（字节00,01,02,03写0x03020100），核内不再交换输入字节。INIT初始化并处理首块，NEXT后续块；ready后读128位标准摘要，按摘要字节顺序高字优先。只有NAME/VERSION/STATUS/DIGEST可读。

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
localparam ADDR_BLOCK0      = 8'h20;
localparam ADDR_BLOCK15     = 8'h2f;
localparam ADDR_DIGEST0     = 8'h40;
localparam ADDR_DIGEST3     = 8'h43;
localparam CORE_NAME0       = 32'h6d643520;
localparam CORE_NAME1       = 32'h68617368;
localparam CORE_VERSION     = 32'h302e3130;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module md5(
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

### secworks/md5/README.md

# md5
Hardware implementation of the md5 hash function.

## Status
Completed. Does Work. **Do. Not. Use.** (Unless you know what you do.)


## Introduction
The [hash function md5](https://en.wikipedia.org/wiki/MD5) is a broken
hash function that shouldn't be used. But sometimes one needs the
implementation of a broken hash function anyway...

Do use this to for example break things like password hashes. Do NOT use
it to protect anything - password hashes for example.


## Implementation details.
The core is implemented in Verilog.


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

Register md5 as a library in the workspace
~~~
fusesoc library add md5 /path/to/md5
~~~

...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add md5 https://github.com/secworks/md5
~~~

To run lint
~~~
fusesoc run --target=lint secworks:crypto:md5
~~~

Run tb_md5 testbench
~~~
fusesoc run --target=tb_md5 secworks:crypto:md5
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_md5 --tool=modelsim secworks:crypto:md5
~~~

List all targets
~~~
fusesoc core show secworks:crypto:md5
~~~


### Implementation Results

## Altera FPGAs
* Tool:   Intel Quartus Prime 19.1
* Device: Cyclone V - 5CGXFC7C6U19C7
* ALMs:   673
* Regs:   1385
* Fmax:   85 MHz


## Xilinx FPGAs
* Tool:   Xilinx Vivado
* Device: Artix-7 - xc7a200tsbv484-2
* LUT:    786
* Regs:   1295
* Fmax:   119 MHz

