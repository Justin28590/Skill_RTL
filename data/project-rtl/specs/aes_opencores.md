# OpenCores AES-128 完整加解密项目

Independent AES-128 implementation with encryption and decryption public tops; include both tops, shared key expansion, round constants and forward/inverse S-boxes. One project case, not two tasks.

## 交付与时序契约

同时交付aes_cipher_top和aes_inv_cipher_top及所有依赖。AES-128，clk上升沿；rst为低有效同步复位，ld装载输入/密钥并启动（解密另有kld控制密钥扩展）。128位密钥/文本按AES标准字节排列；done时输出有效，保留上游周期协议，不能仅输出组合算法函数。详细时序图见附录。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module aes_cipher_top(clk, rst, ld, done, key, text_in, text_out );
input		clk, rst;
input		ld;
output		done;
input	[127:0]	key;
input	[127:0]	text_in;
output	[127:0]	text_out;
input	[7:0]	s0,s1,s2,s3;
input [7:0] b;
endmodule

module aes_inv_cipher_top(clk, rst, kld, ld, done, key, text_in, text_out );
input		clk, rst;
input		kld, ld;
output		done;
input	[127:0]	key;
input	[127:0]	text_in;
output	[127:0]	text_out;
input	[7:0]	s0,s1,s2,s3;
input [7:0] b;
input [7:0] b;
input [7:0] b;
input [7:0] b;
input [7:0] b;
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### freecores/aes_core/doc/aes.pdf

Advanced Encryption
 Standard / Rijndael
            IP Core

          Author: Rudolf Usselmann
                     rudi@asics.ws
                      www.asics.ws

                    Rev. 1.1
           November 12, 2002
Revision History

 Rev.     Date         Author                          Description
 1.0     11/9/02     Rudolf      Initial Release
                     Usselmann

 1.1    11/12/2002   RU          Fixed Several Typos
ASICS.ws                                AES Rijndael IP Core                       November 12, 2002




                                                                                              1
                                                                     Introduction
                   Simple AES/Rijndael IP Core. I have tried to create a implementation of this
               standard that would fit in to a low cost FPGA, like the Spartan IIe series from Xil-
               inx, and still would provide reasonably fast performance.

                   This implementation is with a 128 bit key expansion module only. Implementa-
               tions with different key sizes (192 & 256 bits) and performance parameters (such
               as a fully pipelined ultra-high -speed version) are commercially available from
               ASICS.ws (www.asics.ws).

                   This document will describe the interface to the IP core. It will not talk about
               the AES standard itself.




www.asics.ws                                  Rev. 1.1                                         1 of 9
November 12, 2002            AES Rijndael IP Core             ASICS.ws




                    (This page intentionally left blank)




2 of 9                             Rev. 1.1                www.asics.ws
ASICS.ws                                AES Rijndael IP Core                         November 12, 2002




                                                                                                 2
                                                                         Architecture
                  The AES Rijndael core consists of two blocks: 1) The AES Cipher block
               which performs encryption; 2) The AES Inverse Cipher block which performs
               decryption. Both blocks instantiate the same key expansion block.

2.1.   AES Cipher Core
                  Below figure illustrates the overall architecture of the AES Cipher core.

                                  Figure 1: Cipher Core Architecture Overview




                             ld          Control                                          done




                           key          Key
                                        Expansion




                                       Initial           Round         Final              text_out
                        text_in        Permutation       Permutation   Permutation




                   The AES cipher core consists of a key expansion module, an initial permuta-
               tion module, a round permutation module and a final permutation module. The
               round permutation module will loop internally to perform 10 iteration (for 128 bit
               keys).




www.asics.ws                                  Rev. 1.1                                           3 of 9
November 12, 2002                       AES Rijndael IP Core                                ASICS.ws


2.2.     AES Inverse Cipher Core
                   Below figure illustrates the overall architecture of the AES Inverse Cipher
               core.

                            Figure 2: Inverse Cipher Core Architecture Overview



                            kld                                                         kdone
                                         Control
                             ld                                                         done



                           key         Key               Key reverse
                                       Expansion         buffer




                                       Initial           Round         Final            text_out
                        text_in        Permutation       Permutation   Permutation




                   The AES inverse cipher core consists of a key expansion module, a key rever-
               sal buffer, an initial permutation module, a round permutation module and a final
               permutation module.
                   The key reversal buffer first stores keys for all rounds and then presents them in
               reverse order to the inverse cipher rounds.
                   The round permutation module will loop internally to perform 10 iteration (for
               128 bit keys).




4 of 9                                        Rev. 1.1                                   www.asics.ws
ASICS.ws                                  AES Rijndael IP Core                         November 12, 2002




                                                                                                  3
                                                                                   Operation

3.1.   AES Cipher Core

                   The forward cipher block can perform a complete encrypt sequence in 12 clock
               cycles (10 cycles for the 10 rounds, plus one cycle for initial key expansion, and
               one cycle for the output stage).
                   The forward cipher block accepts a key and the plain text at the beginning of
               each encrypt sequence. The beginning is always indicated by asserting the ‘ld’ pin
               high. When the core completes the encryption sequence it will assert the ‘done’
               signal for one clock cycle to indicate the completion. The user might chose to
               ignore the ‘done’ output and time the completion of the encryption sequence exter-
               nally.


                                  Figure 3: AES cipher core interface timing
                                      0     1   2   3      4   5   6   7   8   9   10 11 12
                            clk

                             ld

                          done

                           key

                        text_in

                       text_out




www.asics.ws                                    Rev. 1.1                                           5 of 9
November 12, 2002                           AES Rijndael IP Core                                   ASICS.ws


3.2.     AES Inverse Cipher Core
                   The inverse cipher block can perform a complete decrypt sequence in 12 cycles
               (10 cycles for the 10 rounds, plus one cycle for initial key loading, and one cycle
               for the output stage).
                   The inverse cipher, however, requires that the key is loaded before decryption
               can be performed. This is because it uses the last expanded key first and the first
               expanded key last. Once the key has been loaded, the expanded versions are gener-
               ated and stored in an internal buffer. The expanded keys can be reused for subse-
               quent decryption sequences for the same key. The key is loaded when the ‘kld’
               signal is asserted high. Once key expansion sequence is completed, the ‘kdone’
               signal will be asserted for one clock cycle.
                   The beginning of the actual decrypt sequence is always indicated by asserting
               the ‘ld’ signal high. When the core completes the decryption sequence it will assert
               the ‘done’ signal for one clock cycle. The user might chose to ignore the ‘done’
               output and time the completion of the decryption sequence externally.
                   The key loading and decryption sequences can not happen in parallel. A key
               must always be loaded before the decryption sequence can be performed.


                                   Figure 4: AES inverse cipher key load timing
                                        0     1   2    3     4   5   6   7   8   9   10 11 12
                            clk

                            kld

                         kdone

                           key




                          Figure 5: AES inverse cipher text block interface timing
                                        0     1   2    3     4   5   6   7   8   9   10 11 12
                            clk

                             ld

                          done

                         text_in

                        text_out




6 of 9                                            Rev. 1.1                                      www.asics.ws
ASICS.ws                                          AES Rijndael IP Core                  November 12, 2002




                                                                                                   4
                                                                                       Core IOs

4.1.   Interface IOs


                                                      Table 1: Core Interfaces
                                   Direction
                           Width




                    Name                                                 Description


                                                      AES Cipher Core Interface
               clk           1         I       core clock
               rst           1         I       active low synchronous reset
               ld            1         I       load
               done          1       O done
               key         128         I       key
               text_in     128         I       input text block
               text_out    128       O output text block
                                                  AES Inverse Cipher Core Interface
               clk           1         I       core clock
               rst           1         I       active low synchronous reset
               kld           1         I       key load
               kdone         1       O key done
               ld            1         I       text load
               done          1       O text done
               key         128         I       key
               text_in     128         I       input text block
               text_out    128       O output text block




www.asics.ws                                               Rev. 1.1                                 7 of 9
November 12, 2002            AES Rijndael IP Core             ASICS.ws




                    (This page intentionally left blank)




8 of 9                             Rev. 1.1                www.asics.ws
ASICS.ws                               AES Rijndael IP Core                      November 12, 2002




                                        Appendix A
                                                                    File Structure
                   This section outlines the hierarchy structure of the AES Rijndael IP Core Ver-
               ilog Source files.

                              Figure 6: AES Cipher Core Hierarchy Structure

                                               Top Level
                                             aes_cipher_top.v




                                 Key Expansion                  SBox
                              aes_key_expand_128.v            aes_sbox.v



                                Rcon         SBox
                              aes_rcon.v   aes_sbox.v



                          Figure 7: AES Inverse Cipher Core Hierarchy Structure

                                               Top Level
                                           aes_inv_cipher_top.v




                                 Key Expansion          Inverse SBox
                              aes_key_expand_128.v       aes_inv_sbox.v



                                Rcon         SBox
                              aes_rcon.v   aes_sbox.v




www.asics.ws                                 Rev. 1.1                                        9 of 9

