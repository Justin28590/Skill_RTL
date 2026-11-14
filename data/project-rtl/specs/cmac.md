# AES-CMAC 完整认证外设

AES-CMAC with 128/256-bit keys; subkey derivation; empty, partial, full and multiple message blocks; AES dependency must be implemented, not stubbed.

## 交付与时序契约

异步低有效复位。CONFIG bit0为128/256位密钥选择；INIT进行AES扩展和CMAC子密钥派生。NEXT处理非末块；FINAL处理最终块，FINAL_SIZE为有效位数0..128（不是字节数），部分块数据放在高位，自动执行0x80及零填充。STATUS[1:0]={valid,ready}，RESULT高字先出。特殊兼容语义：ADDR_CTRL读回keylen，ADDR_CONFIG读回0；FINAL_SIZE可读回；KEY/BLOCK为只写。复位ready=1、valid=0、result/final_size/keylen=0。

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
localparam CTRL_NEXT_BIT     = 1;
localparam CTRL_FINAL_BIT    = 2;
localparam ADDR_CONFIG       = 8'h09;
localparam CONFIG_KEYLEN_BIT = 0;
localparam ADDR_STATUS       = 8'h0a;
localparam STATUS_READY_BIT  = 0;
localparam STATUS_VALID_BIT  = 1;
localparam ADDR_FINAL_SIZE   = 8'h0b;
localparam ADDR_KEY0         = 8'h10;
localparam ADDR_KEY7         = 8'h17;
localparam ADDR_BLOCK0       = 8'h20;
localparam ADDR_BLOCK1       = 8'h21;
localparam ADDR_BLOCK2       = 8'h22;
localparam ADDR_BLOCK3       = 8'h23;
localparam ADDR_RESULT0      = 8'h30;
localparam ADDR_RESULT1      = 8'h31;
localparam ADDR_RESULT2      = 8'h32;
localparam ADDR_RESULT3      = 8'h33;
localparam CORE_NAME0        = 32'h636d6163;
localparam CORE_NAME1        = 32'h2d616573;
localparam CORE_VERSION      = 32'h302e3032;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module cmac(
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

### secworks/cmac/README.md

cmac
====
Verilog implementation of the block cipher based keyed hash function
CMAC.


## Status ##
The core has been implemented and verified againt test vectors from IETF
and NIST using testbench for testcases with zero, single and multiple
block messages. Padding has been verified. The CMAC ICV generation works
with 128 or 256 bit keys.

The Core has been implemented in hardware (Altera and Xilinx FPGAs).


## Introduction ##
This is a Verilog implementation of the block cipher based keyed hash function
CMAC as specfied in the NIST document
[SP 800-38 B](http://csrc.nist.gov/publications/nistpubs/800-38B/SP_800-38B.pdf)
and used in [RFC 4493](https://tools.ietf.org/html/rfc4493). Wikipedia has [a good summary of CMAC too.](https://en.wikipedia.org/wiki/One-key_MAC)

This implementation uses the
[AES block cipher](https://github.com/secworks/aes) with support for 128
and 256 bit keys. The ICV generated is 128 bit.


### Contact information ##
Assured provides customer support including customization, integration
and system development related to the core. For more informantion,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Functionality ##
The core accepts a key and a message divided into zero, one or more 128
bit blocks. After processing the core provides a result, the Integrity
Check Vector (ICV) for the message. The ICV can be communicated to a
recipient. By recalculating the ICV for the received message and
comparing to the received ICV, the recipient can verify the message
integrity and that it is from a sender that share the secret key with
the recipient.

Performance wise, the cost of processing a message requires one initial
AES operation (for internal subkey generation) and then one AES
operation for each message block.


## Usage ##
The core is used by first writing the key into the key registers and
then asserting the _init_ control signal. When the core signals _ready_
the cmac has been initialized. Note that _valid_ will be deasserted by
the core, signalling that the ICV result is no longer valid.

The message can then be processed as a sequence of 128 bit blocks. For
each block the _next_ control signal shall be asserted. Note that
_ready_ signal must be set by the core for the core to accept new
blocks.

Note that the core expects information about number of bits in the final
message block [1..128]. The core performs padding and tweak based on
this information. The final block and the lenght shall be written to the
core and then the _finalize_ signal shall be asserted. The core will
process the final block and then raise _ready_ and _valid_ signalling
that the ICV result is ready and valid.

Note that the core does not provide verification of a given ICV. The
caller is expected to perform this comparison after generating the ICV
for a received message.


## Implementation Results ##
### Altera Cyclone V ###
- Device: 5CGXFC7C7F23C8
- Logic utilization (ALMs): 2285
- Registers:                3171
- Clock speed:              91 MHz


### Xilinx Artix-7 ###
- Device: xc7a200t-3fbg484
- Slices:    2721
- Registers: 2996
- Clock speed: 91 MHz


### Xilinx Spartan-6 ###
- Device: xc6slx45-3fgg484
- Slices:    2385
- Registers: 3002
- Clock speed: 100 MHz

