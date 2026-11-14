# 三级流水 Triple-DES 完整加解密器

Performance-optimized Triple-DES: three DES stages with aligned keys and encrypt/decrypt direction; full round, key-selection and S-box hierarchy. Preserve the documented pipeline latency.

## 交付与时序契约

无复位、无ready；每拍可以采样新块及三把56位密钥（已剔除每字节奇偶校验位）。decrypt=0执行E(K1)-D(K2)-E(K3)，decrypt=1反向D(K3)-E(K2)-D(K1)。方向在一批流水传输期间保持稳定。总共51级时钟寄存延迟：在上升沿n采样的输入在上升沿n+50之后输出；启动填充期间输出无效，不能要求初态为0。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module des3(desOut, desIn, key1, key2, key3, decrypt, clk);
output	[63:0]	desOut;
input	[63:0]	desIn;
input	[55:0]	key1;
input	[55:0]	key2;
input	[55:0]	key3;
input		decrypt;
input		clk;
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### freecores/des/doc/README.txt

/////////////////////////////////////////////////////////////////////
////                                                             ////
////  DES CORE                                                   ////
////                                                             ////
////  Author: Rudolf Usselmann                                   ////
////          rudi@asics.ws                                      ////
////                                                             ////
/////////////////////////////////////////////////////////////////////
////                                                             ////
//// Copyright (C) 2001 Rudolf Usselmann                         ////
////                    rudi@asics.ws                            ////
////                                                             ////
//// This source file may be used and distributed without        ////
//// restriction provided that this copyright statement is not   ////
//// removed from the file and that any derivative work contains ////
//// the original copyright notice and the associated disclaimer.////
////                                                             ////
////     THIS SOFTWARE IS PROVIDED ``AS IS'' AND WITHOUT ANY     ////
//// EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED   ////
//// TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS   ////
//// FOR A PARTICULAR PURPOSE. IN NO EVENT SHALL THE AUTHOR      ////
//// OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,         ////
//// INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES    ////
//// (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE   ////
//// GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR        ////
//// BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF  ////
//// LIABILITY, WHETHER IN  CONTRACT, STRICT LIABILITY, OR TORT  ////
//// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT  ////
//// OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE         ////
//// POSSIBILITY OF SUCH DAMAGE.                                 ////
////                                                             ////
/////////////////////////////////////////////////////////////////////



Triple DES Core
===============
Attached is a Triple DES core implementation in verilog. It takes
three standard 56 bit keys and 64 bits of data as input and generates
a 64 bit encrypted/decrypted result. Two implementations are provided:

1) Area Optimized (CBC Mode)
   This is a sequential implementation and needs 48 cycles to complete
   a full encryption/decryption cycle.


2) Performance Optimized (EBC Mode)
   This is a pipelined implementation that has a 48 cycle pipeline
   (plus 1 input and 1 output register). It can perform a complete
   encryption/decryption every cycle.

Performance
===========
1) Area Optimized (CBC Mode)
   0.18u UMC ASIC process: 5.5K gates, > 160 Mhz
   Spartan IIe 100-6 : 1450 LUTs (about 60%), 88MHz

2) Performance Optimized (EBC Mode)
   0.18u UMC ASIC process: 55K Gates, 300MHz (19.2 Gbits/sec)
   Virtex-II-1500-6: 79% utilization, 166Mhz (10.6 Gbits/sec)



DES Core
========
Attached is a DES core implementation in verilog. It takes a standard
56 bit key and 64 bits of data as input and generates a 64 bit 
encrypted/decrypted result. Two implementations are provided:

1) Area Optimized (CBC Mode)
   This is a sequential implementation and needs 16 cycles to complete
   a full encryption/decryption cycle.


2) Performance Optimized (EBC Mode)
   This is a pipelined implementation that has a 16 cycle pipeline
   (plus 1 input and 1 output register). It can perform a complete
   encryption/decryption every cycle.


Performance
===========
1) Area Optimized (CBC Mode)
   0.18u UMC ASIC process: >155Mhz 3K Gates
   Altera APEX 20KE-1: 1106 lcells >27MHz
   Altera FLEX 10K50E-1: 1283 lcells >43MHz

2) Performance Optimized (EBC Mode)
   0.18u UMC ASIC process: >290Mhz 28K Gates
   Altera APEX 20KE-1: 6688 lcells >53MHz
   Altera FLEX 10K130E-1: 6485 lcells >76 Mhz



Status
======
31-Oct-2002	Added Triple DES
05-Oct-2001	Added decrypt input (Thanks to Mark Cynar for
                providing the code)
		Reorganized directory structure
		Added Makefile
		Cleaned up test benches
03-Feb-2001	Initial Release

 
Directory Structure
===================
[core_root]
 |
 +-doc                        Documentation
 |
 +-bench--+                   Test Bench
 |        +- verilog          Verilog Sources
 |        +-vhdl              VHDL Sources
 |
 +-rtl----+                   Core RTL Sources
 |        +-verilog           Verilog Sources
 |        +-vhdl              VHDL Sources
 |
 +-sim----+
 |        +-rtl_sim---+       Functional verification Directory
 |        |           +-bin   Makefiles/Run Scripts
 |        |           +-run   Working Directory
 |        |
 |        +-gate_sim--+       Functional & Timing Gate Level
 |                    |       Verification Directory
 |                    +-bin   Makefiles/Run Scripts
 |                    +-run   Working Directory
 |
 +-lint--+                    Lint Directory Tree
 |       +-bin                Makefiles/Run Scripts
 |       +-run                Working Directory
 |       +-log                Linter log & result files
 |
 +-syn---+                    Synthesis Directory Tree
 |       +-bin                Synthesis Scripts
 |       +-run                Working Directory
 |       +-log                Synthesis log files
 |       +-out                Synthesis Output


About the Author
================
To find out more about me (Rudolf Usselmann), please visit:
http://www.asics.ws

