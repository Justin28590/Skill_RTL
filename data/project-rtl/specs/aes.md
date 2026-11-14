# AES-128/256 加解密寄存器外设

128-bit blocks; 128/256-bit keys; key expansion; encryption/decryption; 32-bit register API.

## 交付与时序契约

异步低有效复位。keylen=0/1 选择 128/256 位；encdec=1 加密、0 解密。128 位密钥使用 KEY0..3。写 key/config 后 INIT 进行密钥扩展；ready 后写 block，NEXT 启动，ready/valid 后读取 result。CTRL 读回 bits[3:0]={keylen,encdec,next,init}，CONFIG 不提供读回。

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
localparam ADDR_CONFIG      = 8'h0a;
localparam CTRL_ENCDEC_BIT  = 0;
localparam CTRL_KEYLEN_BIT  = 1;
localparam ADDR_KEY0        = 8'h10;
localparam ADDR_KEY7        = 8'h17;
localparam ADDR_BLOCK0      = 8'h20;
localparam ADDR_BLOCK3      = 8'h23;
localparam ADDR_RESULT0     = 8'h30;
localparam ADDR_RESULT3     = 8'h33;
localparam CORE_NAME0       = 32'h61657320;
localparam CORE_NAME1       = 32'h20202020;
localparam CORE_VERSION     = 32'h302e3630;
```

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module aes(
           
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

### secworks/aes/README.md

[![build-openlane-sky130](https://github.com/secworks/aes/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/secworks/aes/actions/workflows/ci.yml)

aes
===

Verilog implementation of the [symmetric block cipher AES (NIST FIPS 197)](http://csrc.nist.gov/publications/fips/fips197/fips-197.pdf).


## Status ##
The core is completed, has been used in several FPGA and ASIC
designs. The core is well tested and mature.


## Introduction ##

This implementation supports 128 and 256 bit keys. The
implementation is iterative and process one 128 block at a time. Blocks
are processed on a word level with 4 S-boxes in the data path. The
S-boxes for encryption are shared with the key expansion and the core
can thus not do key update in parallel with block processing.

The encipher and decipher block processing datapaths are separated and
basically self contained given access to a set of round keys and a
block. This makes it possible to hard wire the core to only encipher or
decipher operation. This allows the synthesis/build tools to optimize
away the other functionality which will reduce the size to about
50%. This has been tested to verify that decryption is removed and the
core still works.

For cipher modes such as CTR, CCM, CMAC, GCM the decryption
functionality in the AES core will never be used and thus the decipher
block processing can be removed.

This is a fairly compact implementation. Further reduction could be
achived by just having a single S-box. Similarly the performane can be
increased by having 8 or even 16 S-boxes which would reduce the number
of cycles to two cycles for each round.


### Contact information ##

Assured provides customer support including customization, integration
and system development related to the core. For more information,
please contact [Assured Security
Consultants](https://www.assured.se/contact).


## Branches ##

There are several branches available that provides different versions of
the core. The branches are not planned to be merged into master. The
branches available that provides versions of the core are:


### on-the-fly-keygen ###

This version of AES implements the key expansion using an on-the-fly
mechanism. This allows the initial key expansion to be removed. This
saves a number of cycles and also remove almost 1800 registers needed to
store the round keys. Note that this version of AES only supports
encryption. On-the-fly key generation does not work with
decryption. Decryption must be handled by the block cipher mode - for
example CTR.


### dual-keys ###

This version of AES supports two separate banks of expanded keys to
allow fast key switching between two keys. This is useful for example in
an AEAD mode with CBC + CMAC implemented using a single AES core.


### cmt-sbox ###

An experimental version of the core in which the S-box is implemented
using circuit minimized logic functions of a ROM table. The specific
table used is
[the 113 gate circuit](http://cs-www.cs.yale.edu/homes/peralta/CircuitStuff/SLP_AES_113.txt) by the [CMT team at Yale](http://cs-www.cs.yale.edu/homes/peralta/CircuitStuff/CMT.html).

Some area and performance results using the cmt_sbox compared to
master:

#### Altera
- Tool: Quartus Prime 19.1.0
- Device: Cyclone V (5CGXFC7C7F23C8)
- master (S-box implemented with a table)
  - ALMs: 2599
  - Regs: 3184
  - Fmax: 93 MHz
  - aes_sbox: 160 ALUTs

- cmt_sbox
  - ALMs: 2759
  - Regs: 3147
  - Fmax: 69 MHz
  - aes_sbox: 363 ALUTs


#### Xilinx
- Tool: Vivado 2019.2
- Device: Kintex-7 (7k70tfbv676-1)
- master:
  - LUTs: 3020
  - FFs: 2992
  - Fmax: 125 MHz

- cmt_sbox:
  - LUTs: 2955
  - FFs: 2992
  - Fmax: 105 MHz


## Core Usage

### Usage sequence:
1. Load the key to be used by writing to the key register words.
2. Set the key length by writing to the config register.
3. Initialize key expansion by writing a one to the init bit in the control register.
4. Wait for the ready bit in the status register to be cleared and then to be set again. This means that the key expansion has been completed.
5. Write the cleartext block to the block registers.
6. Start block processing by writing a one to the next bit in the control register.
7. Wait for the ready bit in the status register to be cleared and then to be set again. This means that the data block has been processed.
8. Read out the ciphertext block from the result registers.


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

Register aes as a library in the workspace
~~~
fusesoc library add aes /path/to/aes
~~~

...if repo is available locally or...
...to get the upstream repo
~~~
fusesoc library add aes https://github.com/secworks/aes
~~~

To run lint
~~~
fusesoc run --target=lint secworks:crypto:aes
~~~

Run tb_aes testbench
~~~
fusesoc run --target=tb_aes secworks:crypto:aes
~~~

Run with modelsim instead of default tool (icarus)
~~~
fusesoc run --target=tb_aes --tool=modelsim secworks:crypto:aes
~~~

List all targets
~~~
fusesoc core show secworks:crypto:aes
~~~


## Implementation results - ASIC ##

The core has been implemented in standard cell ASIC processes.

### TSMC 180 nm ###
Target frequency: 20 MHz
Complete flow from RTL to placed gates. Automatic clock gating and scan
insertion.

- 8 kCells
- Aera: 520 x 520 um
- Good timing margin with no big cells and buffers.


## Implementation results - FPGA ##

The core has been implemented in Altera and Xilinx FPGA devices.

### Altera Cyclone V GX ###
- 2624 ALMs
- 3123 Regs
- 96 MHz
- 46 cycles/block


### Altera Cyclone IV GX ###
- 7426 LEs
- 2994 Regs
- 96 MHz fmax
- 46 cycles/block

This means that we can do more than 2 Mblocks/s or 256 Mbps
performance.

Removing the decipher module yields:
- 5497 LEs
- 2855 Regs
- 106 MHz fmax
- 46 cycles/block


### Microchip IGLOO 2 ###
- Tool: Libero v 12.4
- Device: M2GL090TS-1FG484I
- LUTs: 6335
- SLEs: 1376
- BRAMs: 8
- Fmax: 98.5 MHz


### Xilinx Spartan6LX-3 ###
- 2576 slices
- 3000 regs
- 100 MHz
- 46 cycles/block


### Xilinx Artix 7 200T-3 ###
- 2298 slices
- 2989 regs
- 97 MHz
- 46 cycles/block

