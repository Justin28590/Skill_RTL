# Wishbone 可配置 SPI 主控制器

Complete SPI master with Wishbone registers, clock divider and shift engine; 1-128 bit transfers, programmable sample/launch edges, bit order, interrupt and automatic slave select.

## 交付与时序契约

Wishbone SPI完整外设，wb_rst_i高有效。spi_defines公开配置为32位数据总线、128位最大传输、8个片选。寄存器地址是Wishbone字节地址，保留低地址选择约定。CHAR_LEN=0表示128位；支持LSB/MSB先行、独立RX/TX边沿、时钟分频、GO_BUSY、IRQ和自动/手动片选。具体寄存器布局见附录。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 编译配置

方言：2005；预定义宏：（若为空则无）。SystemVerilog目标使用2012。

## 顶层接口

```verilog
module spi_top
(
  
  wb_clk_i, wb_rst_i, wb_adr_i, wb_dat_i, wb_dat_o, wb_sel_i,
  wb_we_i, wb_stb_i, wb_cyc_i, wb_ack_o, wb_err_o, wb_int_o,

  
  ss_pad_o, sclk_pad_o, mosi_pad_o, miso_pad_i
);
parameter Tp = 1;
input                            wb_clk_i;
input                            wb_rst_i;
input                      [4:0] wb_adr_i;
input                   [32-1:0] wb_dat_i;
output                  [32-1:0] wb_dat_o;
input                      [3:0] wb_sel_i;
input                            wb_we_i;
input                            wb_stb_i;
input                            wb_cyc_i;
output                           wb_ack_o;
output                           wb_err_o;
output                           wb_int_o;
output          [`SPI_SS_NB-1:0] ss_pad_o;
output                           sclk_pad_o;
output                           mosi_pad_o;
input                            miso_pad_i;
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### freecores/spi/doc/spi.pdf

SPI Master Core
    Specification
             Author: Simon Srot
         simons@opencores.org


                     Rev. 0.6
               March 15, 2004
 OpenCores                 SPI Master Core Specification                 3/15/2004


                                                           Revision History

Rev.   Date              Author       Description
0.1    June 13, 2002     Simon Srot   First Draft
0.2    July 12, 2002     Simon Srot   Document is lectured.
0.3    December 28,      Simon Srot   Support for 64 bit character len added.
       2002
0.4    March       26,   Simon Srot   Automatic slave select signal generation added.
       2003
0.5    April 15 2003     Simon Srot   Support for 128 bit character len added.
0.6    March       15,   Simon Srot   Bit fields in CTRL changed.
       2004




www.opencores.org                     Rev 0.5                                    i
  OpenCores                                SPI Master Core Specification                                      3/15/2004




Contents
CONTENTS.......................................................................................................... II

INTRODUCTION................................................................................................. 1

IO PORTS.............................................................................................................. 2
   2.1 WISHBONE INTERFACE SIGNALS.................................................................. 2
   2.2 SPI EXTERNAL CONNECTIONS ......................................................................... 2
REGISTERS .......................................................................................................... 3
   3.1 CORE REGISTERS LIST .................................................................................... 3
   3.2 DATA RECEIVE REGISTER LOW/HIGH[RXL/RXH]............................................ 3
   3.3 DATA TRANSMIT REGISTER LOW/HIGH[TXL/TXH] ......................................... 4
   3.4 CONTROL AND STATUS REGISTER [CTRL]...................................................... 4
   3.5 DIVIDER REGISTER [DIVIDER]...................................................................... 5
   3.6 SLAVE SELECT REGISTER [SS] ........................................................................ 5
OPERATION......................................................................................................... 7
   4.1 WISHBONE INTERFACE ................................................................................ 7
   4.2 SERIAL INTERFACE ......................................................................................... 7
ARCHITECTURE ................................................................................................ 9

CORE CONFIGURATION ............................................................................... 10




www.opencores.org                                          Rev 0.5                                                   ii
  OpenCores                  SPI Master Core Specification                 3/15/2004




                                             Introduction
This document provides specifications for the SPI (Serial Peripheral Interface) Master
core. Synchronous serial interfaces are widely used to provide economical board-level
interfaces between different devices such as microcontrollers, DACs, ADCs and
other. Although there is no single standard for a synchronous serial bus, there are
industry-wide accepted guidelines based on two most popular implementations:

       SPI (a trademark of Motorola Semiconductor)
       Microwire/Plus (a trademark of National Semiconductor)

Many IC manufacturers produce components that are compatible with SPI and
Microwire/Plus.
The SPI Master core is compatible with both above-mentioned protocols as master
with some additional functionality. At the hosts side, the core acts like a WISHBONE
compliant slave device.

Features:
   Full duplex synchronous serial data transfer
   Variable length of transfer word up to 128 bits
   MSB or LSB first data transfer
   Rx and Tx on both rising or falling edge of serial clock independently
   8 slave select lines
   Fully static synchronous design with one clock domain
   Technology independent Verilog
   Fully synthesizable




www.opencores.org                       Rev 0.6                               1 of 10
 OpenCores                 SPI Master Core Specification                      3/15/2004




                                                               IO ports
2.1 WISHBONE interface signals
Port         Width    Direction     Description
wb_clk_i       1      Input         Master clock
wb_rst_i       1      Input         Synchronous reset, active high
wb_adr_i       5      Input         Lower address bits
wb_dat_i      32      Input         Data towards the core
wb_dat_o      32      Output        Data from the core
wb_sel_i       4      Input         Byte select signals
wb_we_i        1      Input         Write enable input
wb_stb_i       1      Input         Strobe signal/Core select input
wb_cyc_i       1      Input         Valid bus cycle input
wb_ack_o       1      Output        Bus cycle acknowledge output
wb_err_o       1      Output        Bus cycle error output
wb_int_o       1      Output        Interrupt signal output
                         Table 1: Wishbone interface signals


All output WISHBONE signals are registered and driven on the rising edge of
wb_clk_i. All input WISHBONE signals are latched on the rising edge of wb_clk_i.

2.2 SPI external connections
Port          Width     Direction    Description
/ss_pad_o       8       Output       Slave select output signals
sclk_pad_o      1       Output       Serial clock output
mosi_pad_o      1       Output       Master out slave in data signal output
miso_pad_i      1       Input        Master in slave out data signal input
                          Table 2: SPI external connections




www.opencores.org                       Rev 0.6                                 2 of 10
  OpenCores                     SPI Master Core Specification                             3/15/2004




                                                                  Registers
3.1 Core Registers list
Name         Address    Width            Access             Description
Rx0            0x00        32               R               Data receive register 0
Rx1            0x04        32               R               Data receive register 1
Rx2            0x08        32               R               Data receive register 2
Rx3            0x0c        32               R               Data receive register 3
Tx0            0x00        32              R/W              Data transmit register 0
Tx1            0x04        32              R/W              Data transmit register 1
Tx2            0x08        32              R/W              Data transmit register 2
Tx3            0x0c        32              R/W              Data transmit register 3
CTRL           0x10        32              R/W              Control and status register
DIVIDER        0x14        32              R/W              Clock divider register
SS             0x18        32              R/W              Slave select register
                                Table 3: List of core registers


All registers are 32-bit wide and accessible only with 32 bits (all wb_sel_i signals
must be active).

3.2 Data receive registers[RxX]
 Bit #                                               31:0
Access                                                R
Name                                                  Rx

                                Table 4: Data Receive register
Reset Value: 0x00000000

RxX
The Data Receive registers hold the value of received data of the last executed
transfer. Valid bits depend on the character length field in the CTRL register (i.e. if
CTRL[9:3] is set to 0x08, bit RxL[7:0] holds the received data). If character length is
less or equal to 32 bits, Rx1,Rx2 and Rx3 are not used, if character length is less than
64 bits, Rx2 and Rx3 are not used and so on.

NOTE: The Data Received registers are read-only registers. A Write to these registers
will actually modify the Transmit registers because those registers share the same
FFs.




www.opencores.org                           Rev 0.6                                         3 of 10
  OpenCores                     SPI Master Core Specification                     3/15/2004



3.3 Data transmit register [TxX]
 Bit #                                              31:0
Access                                              R/W
Name                                                 Tx

                               Table 5: Data Transmit register
Reset Value: 0x00000000

TxX
The Data Receive registers hold the data to be transmitted in the next transfer. Valid
bits depend on the character length field in the CTRL register (i.e. if CTRL[9:3] is set
to 0x08, the bit Tx0[7:0] will be transmitted in next transfer). If character length is
less or equal to 32 bits, Tx1, Tx2 and Tx3 are not used, if character len is less than 64
bits, Tx2 and Tx3 are not used and so on.

3.4 Control and status register [CTRL]
 Bit #      31:14      13     12      11        10         9          8           7           6:0
Access        R       R/W    R/W     R/W       R/W       R/W         R/W          R          R/W
Name       Reserved   ASS     IE     LSB     Tx_NEG     Rx_NEG      GO_BSY     Reserved    CHAR_LEN

                             Table 6: Control and Status register
Reset Value: 0x00000000

ASS
If this bit is set, ss_pad_o signals are generated automatically. This means that slave
select signal, which is selected in SS register is asserted by the SPI controller, when
transfer is started by setting CTRL[GO_BSY] and is de-asserted after transfer is
finished. If this bit is cleared, slave select signals are asserted and de-aserted by
writing and clearing bits in SS register.

IE
If this bit is set, the interrupt output is set active after a transfer is finished. The
Interrupt signal is deasserted after a Read or Write to any register.

LSB
If this bit is set, the LSB is sent first on the line (bit TxL[0]), and the first bit received
from the line will be put in the LSB position in the Rx register (bit RxL[0]). If this bit
is cleared, the MSB is transmitted/received first (which bit in TxX/RxX register that is
depends on the CHAR_LEN field in the CTRL register).

Tx_NEG
If this bit is set, the mosi_pad_o signal is changed on the falling edge of a sclk_pad_o
clock signal, or otherwise the mosi_pad_o signal is changed on the rising edge of
sclk_pad_o.



www.opencores.org                           Rev 0.6                                  4 of 10
  OpenCores                       SPI Master Core Specification                3/15/2004


Rx_NEG
If this bit is set, the miso_pad_i signal is latched on the falling edge of a sclk_pad_o
clock signal, or otherwise the miso_pad_i signal is latched on the rising edge of
sclk_pad_o.

GO_BSY
Writing 1 to this bit starts the transfer. This bit remains set during the transfer and is
automatically cleared after the transfer finished. Writing 0 to this bit has no effect.

NOTE: All registers, including the CTRL register, should be set before writing 1 to
the GO_BSY bit in the CTRL register. The configuration in the CTRL register must be
changed with the GO_BSY bit cleared, i.e. two Writes to the CTRL register must be
executed when changing the configuration and performing the next transfer, firstly
with the GO_BSY bit cleared and secondly with GO_BSY bit set to start the transfer.
When a transfer is in progress, writing to any register of the SPI Master core has no
effect.

CHAR_LEN
This field specifies how many bits are transmitted in one transfer. Up to 64 bits can be
transmitted.
CHAR_LEN = 0x01 … 1 bit
CHAR_LEN = 0x02 … 2 bits
…
CHAR_LEN = 0x7f … 127 bits
CHAR_LEN = 0x00 … 128 bits

3.5 Divider register [DIVIDER]
 Bit #                     31:16                                    15:0
Access                       R                                      R/W
Name                      Reserved                                DIVIDER

                                     Table 7: Divider register
Reset Value: 0x0000ffff

DIVIDER
The value in this field is the frequency divider of the system clock wb_clk_i to
generate the serial clock on the output sclk_pad_o. The desired frequency is obtained
according to the following equation:

                     f wb _ clk
         f sclk
                  DIVIDER 1 2

3.6 Slave select register [SS]
 Bit #                        31:8                                  7:0
Access                         R                                    R/W




www.opencores.org                              Rev 0.6                            5 of 10
  OpenCores                   SPI Master Core Specification                    3/15/2004


Name                     Reserved                                    SS

                               Table 8: Slave Select register
Reset Value: 0x00000000

SS
If CTRL[ASS] bit is cleared, writing 1 to any bit location of this field sets the proper
ss_pad_o line to an active state and writing 0 sets the line back to inactive state. If
CTRL[ASS] bit is set, writing 1 to any bit location of this field will select appropriate
ss_pad_o line to be automatically driven to active state for the duration of the transfer,
and will be driven to inactive state for the rest of the time.




www.opencores.org                          Rev 0.6                                6 of 10
           OpenCores                                SPI Master Core Specification                     3/15/2004




                                                                              Operation
  This core is an SPI and Microwire/Plus compliant synchronous serial controller. At
  the host side, it is controlled via registers accessible through a WISHBONE rev. B1
  interface.

                       /ss_pad_o[0]
WISHBONE




                       /ss_pad_o[1]
                            /ss_pad_o[0]
           WISHBONE




                       /ss_pad_o[2]
                            /ss_pad_o[1]
                      MASTER/ss_pad_o[2]
                         sclk_pad_o
                           MASTER
                              sclk_pad_o
                        mosi_pad_o
                         miso_pad_i
                              mosi_pad_o
                               miso_pad_i
                                            MISO MOSI SCLK /SS      MISO MOSI SCLK / SS     MISO MOSI SCLK /SS
                                                MISO MOSI SCLK/SS       MISO MOSI SCLK/SS       MISO MOSI SCLK/SS
                                                  SLAVE 0
                                                     SLAVE  0             SLAVE 1
                                                                             SLAVE  1            SLAVE 2
                                                                                                     SLAVE 2




  4.1 WISHBONE interface
  The SPI core has five 32-bit registers through the WISHBONE rev. B1 compatible
  interface. All accesses to SPI registers must be 32-bit (wb_sel[3:0] = 0xf). Please refer
  to the WISHBONE specification at
  http://www.opencores.org/wishbone/specs/wbspec_b1.pdf

  4.2 Serial interface
  The serial interface consists of slave select lines, serial clock lines, as well as input
  and output data lines. All transfers are full duplex transfers of a programmable
  number of bits per transfer (up to 64 bits).
  Compared to the SPI/Microwire protocol, this core has some additional functionality.
  It can drive data to the output data line in respect to the falling (SPI/Microwire
  compliant) or rising edge of the serial clock, and it can latch data on an input data line
  on the rising (SPI/Microwire compliant) or falling edge of a serial clock line. It also
  can transmit (receive) the MSB first (SPI/Microwire compliant) or the LSB first.
  It is important to know that the RxX and TxX registers share the same flip-flops,
  which means that what is received from the input data line in one transfer will be
  transmitted on the output data line in the next transfer if no write access to the TxX
  register is executed between the transfers.




  www.opencores.org                                             Rev 0.6                                  7 of 10
 OpenCores                      SPI Master Core Specification                             3/15/2004


   ss_pad_o


   sclk_pad_o


                                          MSB                          LSB
   mosi_pad_o                            (Tx[7])                      (Tx[0])




                                          MSB                          LSB
   miso_pad_i                            (Rx[7])                      (Rx[0])




          CTRL[LSB] = 0, CTRL[CHAR_LEN] = 0x08, CTRL[TX_NEG] = 1, CTRL[RX_NEG] = 0



   ss_pad_o


   sclk_pad_o


                                               LSB                               MSB
   mosi_pad_o                                 (Tx[0])                           (Tx[9])




                                               LSB                               MSB
   miso_pad_i                                 (Rx[0])                           (Rx[9])




          CTRL[LSB] = 1, CTRL[CHAR_LEN] = 0x0a, CTRL[TX_NEG] = 0, CTRL[RX_NEG] = 1




www.opencores.org                                       Rev 0.6                             8 of 10
   OpenCores                                   SPI Master Core Specification                              3/15/2004




                                                              Architecture
The SPI Master core consists of three parts shown in the following figure:




                                                    Clock generator

                                                      spi_clgen.v
 WHISHBONE SOC Bus




                         WHISHBONE Interface




                                                                      Serial Interface
                                                                                                       sclk_pad_o




                                                                                         spi_shift.v
                                                                                                       ss_pad_o

                                                                                                       mosi_pad_o
                                                                                                       miso_pad_i




                                                         spi_top.v




www.opencores.org                                        Rev 0.6                                              9 of 10
  OpenCores                  SPI Master Core Specification                3/15/2004




                         Core configuration

To meet specific system requirements and size constraints on behalf of the core
functionality, the SPI Master core can be configuredby setting the appropriate define
directives in the spi_defines.v source file. The directives are as follows:

SPI_DIVIDER_BIT_NB
This parameter defines the maximum number of bits needed for the divider. Set this
parameter accordingly to the maximum system frequency and lowest serial clock
frequency:
                                  f sys max
SPI_DIVIDER_BIT_NB log 2                    1
                               f sclk min 2
Default value is 16.

SPI_MAX_CHAR
This parameter defines the maximum number of bits that can be received/transmitted
in one transfer.
The default value is 64.

SPI_SS_NB
This parameter defines the number of slave select lines.
The default value is 8.




www.opencores.org                        Rev 0.6                            10 of 10

