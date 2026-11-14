# USB 1.1 Host＋Device 完整控制系统

Complete USB 1.1 host and slave IP pair: both Wishbone tops, host/slave protocol controllers, endpoint FIFOs, packet scheduling, serial interface engine, CRC and wire-level transport. The public project exports usbHost and usbSlave; deliver both and every descendant. No board-specific wrappers or vendor primitives.

## 交付与时序契约

同时交付usbHost和usbSlave两个顶层；Wishbone同步高有效复位，独立USB时钟域。Host FIFO深度64，地址宽6；四个device端点FIFO也分别深度64、地址宽6。需完整寄存器组、端点数据通道、packet/SIE、CRC、握手和串行物理信号处理。至少支持USB1.1全速Host/Device的SETUP/OUT/IN和总线复位/连接检测；不要求板卡wrapper或combined-role第三顶层。地址与控制位见附录完整公开规范。

必须交付全部顶层和所有子模块；每个顶层至少有一个实际展开的子模块。内部模块/寄存器名不要求与参考一致。所有模块必须由本次响应提供，不允许链接参考RTL、行为桩或Testbench。所有顶层端口、参数名和含义必须保留。有限测试并非完整证明，仍应实现公开功能的全部合法输入。

## 编译配置

方言：2005；预定义宏：SIM_COMPILE（若为空则无）。SystemVerilog目标使用2012。

SIM_COMPILE模式将Host resume发送计数从30000缩短为10个低速位周期；其余协议行为不变。

## 顶层接口

```verilog
module usbHost(
  clk_i,
  rst_i,
  address_i, 
  data_i, 
  data_o, 
  we_i, 
  strobe_i,
  ack_o,
  usbClk,
  hostSOFSentIntOut, 
  hostConnEventIntOut, 
  hostResumeIntOut, 
  hostTransDoneIntOut,
  USBWireDataIn,
  USBWireDataInTick,
  USBWireDataOut,
  USBWireDataOutTick,
  USBWireCtrlOut,
  USBFullSpeed
   );
parameter HOST_FIFO_DEPTH = 64;
parameter HOST_FIFO_ADDR_WIDTH = 6;
input clk_i;
input rst_i;
input [7:0] address_i;
input [7:0] data_i;
output [7:0] data_o;
input we_i;
input strobe_i;
output ack_o;
input usbClk;
output hostSOFSentIntOut;
output hostConnEventIntOut;
output hostResumeIntOut;
output hostTransDoneIntOut;
input [1:0] USBWireDataIn;
output [1:0] USBWireDataOut;
output USBWireDataOutTick;
output USBWireDataInTick;
output USBWireCtrlOut;
output USBFullSpeed;
endmodule

module usbSlave(
  clk_i,
  rst_i,
  address_i, 
  data_i, 
  data_o, 
  we_i, 
  strobe_i,
  ack_o,
  usbClk,
  slaveVBusDetIntOut,
  slaveNAKSentIntOut,
  slaveSOFRxedIntOut, 
  slaveResetEventIntOut, 
  slaveResumeIntOut, 
  slaveTransDoneIntOut,
  USBWireDataIn,
  USBWireDataInTick,
  USBWireDataOut,
  USBWireDataOutTick,
  USBWireCtrlOut,
  USBFullSpeed,
  USBDPlusPullup,
  USBDMinusPullup,
  vBusDetect
   );
parameter EP0_FIFO_DEPTH = 64;
parameter EP0_FIFO_ADDR_WIDTH = 6;
parameter EP1_FIFO_DEPTH = 64;
parameter EP1_FIFO_ADDR_WIDTH = 6;
parameter EP2_FIFO_DEPTH = 64;
parameter EP2_FIFO_ADDR_WIDTH = 6;
parameter EP3_FIFO_DEPTH = 64;
parameter EP3_FIFO_ADDR_WIDTH = 6;
input clk_i;
input rst_i;
input [7:0] address_i;
input [7:0] data_i;
output [7:0] data_o;
input we_i;
input strobe_i;
output ack_o;
input usbClk;
output slaveSOFRxedIntOut;
output slaveResetEventIntOut;
output slaveResumeIntOut;
output slaveTransDoneIntOut;
output slaveNAKSentIntOut;
output slaveVBusDetIntOut;
input [1:0] USBWireDataIn;
output [1:0] USBWireDataOut;
output USBWireDataOutTick;
output USBWireDataInTick;
output USBWireCtrlOut;
output USBFullSpeed;
output USBDPlusPullup;
output USBDMinusPullup;
input vBusDetect;
endmodule
```


## 上游公开规范附录

以下是公开README/设计规格，不含参考实现或隐藏测试。保留来源许可，文档中的源码链接仅为出处；不提供读取参考源码的工具。

### freecores/usbhostslave/doc/README.txt

USBHostSlave has been successfully compiled using Quartus 6.0
Note, that the component Builder in Quartus 6.0 will not accept include files, so you have to use Quartus to generate a
single .vqm file, rename this as a .v file, and then import this using component Builder.
USBHostSlave has been tested in a SystemC simulation, and on a Altera Nios development kit Cyclone edition.


Release notes:
// Version 0.6 - Feb 4th 2005. Fixed bit stuffing and de-stuffing. This version succesfully supports 
//             control reads and writes to USB flash dongle
// Version 0.7 - Feb 24th 2005. Added support for isochronous transfers, fixed resume, connect and disconnect 
//             time outs, added low speed EOP keep alive. The TX bit rate is now controlled by 
//             SIETransmitter, and takes account of the requirement that SOF, and PREAMBLE are always full
//             speed, and TX resume is always low speed.
//             Fixed read clock recovery (readUSBWireData.v) issue which was resulting 
//             in missing receive packets.
//             Fixed broken SOF Sync mode (where transacations are synchronized with the SOF transmission)
//             by adding kludged delay to softranmit. This needs to be fixed properly.
//             This version has undergone limited testing
//             with full speed flash dongle, low speed keyboard, and a PC in full and low speed modes.
// Version 0.8 - June 24th 2005. Added bus access to the host SOFTimer. This version has been tested
//             with uClinux, and is known to work with a full speed USB flash stick.
//             Moving Opencores project status from Beta to done.
// Version 1.0 - October 14th 2005. Seperated the bus clock from the usb logic clock
//               Modified RX and TX fifo status registers, and removed TX fifo data count
//               register. Added RESET_CORE bit to HOST_SLAVE_CONTROL_REG.
//               Fixed slave mode bug which caused receive fifo to
//               be filled with incoming data when the slave was
//               responding with a NAK, and the data should have been discarded.
//             TODO: Test isochronous mode, and low speed mode using uClinux driver
//                   Add frame period adjustment capability
//                   Add compilation flags for slave only and host only versions
//                   Create data bus width options beyond 8-bit              
// Version 1.1 - February 23rd 2006. Fixed bug related to 'noActivityTimeOut'
//             Previously the 'noActivityTimeOut' flag was repetitively pulsed whenever
//             there was no detected activity on the USB data lines. This caused an infrequent
//             misreporting of time out errors. 'noActivityTimeOut' is now only enabled when
//             the higher level state machines are actively looking for receive packets. 
//             Modified USB RX data clock recovery, so that data is sampled during the middle
//             of a USB bit period. Fixed a bug which could result in double sampling
//             of USB RX data if clock phase adjustments were required in the middle of a 
//             USB packet.
// Version 1.2 - October 1st 2006. Small changes to .asf FSM's required
//             during migration to ActiveHDL 7.1. Released SystemC test bench.
//             Re-generated .v files using ActiveHDL 7.1
//             Replaced individual timescale directives with `include "timescale.v
//             Renamed top level Altera wrapper from 'usbHostSlaveWrap' to 
//             'usbHostSlaveAvalonWrap'
// Version 1.3 - March 22nd 2008. Fixed bug in 'readUSBWireData'. Added
//             synchronizer to incoming USB wire data to avoid
//             metastability, and delay hazards. Not entirely sure, but it appears that 
//             this bug caused more problems with some of the newer low power FPGAs
//             Maybe because they are more prone to problems with metastable
//             inputs that feed logic functions causing excessive high speed
//             toggle activity, and disrupting nearby cicuits.
// Version 2.0 - June 16th 2008. Added two new top level modules which
//             allow the instantiation of only host (usbHost.v), or only device
//             features. Added double sync stages between usbClk, and busClk domains
//             to fix possible metastability issues. Also modified synchronization to
//             allow operation with busClk frequency less than usbClk frequency (down to
//             24MHz). Integrated full support for USB PHY. Prior to this modification
//             the user would need to instantiate a GPIO module to control USB speed,
//             D+ and D- pull-up control, and VBUS detect. Fixed bug in bus interface wb_ack.
//             Modified cross-clock synchronisation of fifo resets
//             Added usbDevice, a standalone usb device implementation of usbhostslave
//             no additional hardware or software required

 




### freecores/usbhostslave/doc/USBHostSlave_IPCore_Specification.pdf

USBHostSlave IP
           Core
   Specification

             Author: Steve Fielding
        sfielding@base2designs.com




                          Rev. 1.2
                      June 8, 2008
   OpenCores                                                  6/8/2008




               This page has been intentionally left blank.




www.opencores.org                 Rev 1.2                            ii
   OpenCores                                                                6/8/2008




                                                       Revision History
 Rev. Date          Author      Description
 0.1  10/01/04      Sfielding   Created
 0.2  12/05/04      Sfielding   Fixed frame_num register description
 0.3  01/11/05      Sfielding   Added host slave mode register
 0.4  01/25/05      Sfielding   Added Version number register, and changed host
                                and slave frameNum registers
 0.5    02/10/05 Sfielding      Added instructions for clearing interrupt registers
 0.6    02/25/05 Sfielding      Added isochronous mode control. Altered
                                descriptions of endpoint control and status
                                registers
 0.7    06/04/05 Sfielding      Added SOF timer register
                                Split version number into major, and minor
                                Added HOST_RX_FIFO_DATA reg to register
                                memory map
 1.0   10/14/05     Sfielding   Seperated bus clock and usb clock. Updated
                                Wishbone datasheet. Removed Tx and Rx fifo
                                status registers, and removed TX fifo data count
                                register. Added RESET_CORE bit to
                                HOST_SLAVE_CONTROL_REG.
                                Fixed slave mode bug which caused receive fifo to
                                be filled with incoming data when the slave was
                                responding with a NAK, and the data should have
                                been discarded.
 1.1   3/24/06      Sfielding   Fixed 48MHz clock tolerance requirement, and
                                added note to clock chapter about 48MHz
                                oscillator on Development boards.
 1.2   6/06/08      Sfielding   Added slave register descriptions, and pin
                                descriptions for VBUS detect, and D+ D- pull-up
                                control. Changed minimum bus clock frequency.




www.opencores.org                  Rev 1.2                                        iii
      OpenCores                                                                                                        6/8/2008




                                                                                   Contents
INTRODUCTION............................................................................................................. 1
ARCHITECTURE.............................................................................................................2
OPERATION..................................................................................................................... 4
REGISTERS...................................................................................................................... 6
CLOCKS...........................................................................................................................21
IO PORTS........................................................................................................................ 22
WISHBONE DATASHEET........................................................................................... 24
RESOURCE UTILIZATION......................................................................................... 25
USB TRANSCEIVERS................................................................................................... 26




www.opencores.org                                           Rev 1.2                                                             iv
     OpenCores                                                                    6/8/2008




                                                                                   1
                                               Introduction

USBHostSlave is a USB 1.1 Host and Device IP core.
–   Supports full speed (12Mbps) and low speed (1.5Mbps) operation.
–   USB Device has four endpoints, each with their own independent FIFO.
–   Supports the four types of USB data transfer; control, bulk, interrupt, and isochronous
    transfers.
–   Host can automatically generate SOF packets.
–   8-bit Wishbone slave bus interface.
–   FIFO depth configurable via parameters.




www.opencores.org                         Rev 1.1                                   1 of 30
    OpenCores                                                                    6/8/2008




                                                                                  2
                                             Architecture

The USBhostSlave IP core consists of five major functional blocks (see Figure (1) ).
USBSerialInterfaceEngine – Supports the lowest level of the USB 1.1 protocol layer. On
the transmit path, USBSerialInterfaceEngine implements, sync insertion, CRC calculation
and insertion, parallel to serial conversion, bit stuffing, and NRZI encoding. On the
receive path, USBSerialInterfaceEngine, implements connection state detection, sync
detection and stripping, clock recovery, NRZI decoding, bit de-stuffing, CRC calculation
and checking, and serial to parallel conversion.
HostSlaveMux – Allows host and slave controllers to share access to the
USBSerialInterfaceEngine.
USBSlaveControl – Supports the USB 1.1 Device specific portion of the USB 1.1
protocol layer. Supports all USB 1.1 transaction types; bulk, setup, interrupt, and
isochronous.
USBHostControl – Supports the USB 1.1 Host specific portion of the USB 1.1 protocol
layer. Supports all USB 1.1 transaction types; bulk, setup, interrupt, and isochronous.
Supports automatic preamble insertion, and automatic SOF generation and transmission
WishBoneBI – Provides Wishbone compatible interface to host/slave controllers and the
transmit/receive FIFOs.




www.opencores.org                        Rev 1.1                                   2 of 30
   OpenCores                                                    6/8/2008




                          WishBone Bus

                                 wishBoneBI




   slaveRxFifo[3:0]                                            hostRxFifo
   slaveTxFifo[3:0]
                      USBSlaveControl         USBHostControl
                                                               hostTxFifo




                                    hostSlaveMux




                              USBSerialInterfaceengine




                                 USB PHY
                         Figure 1USBHostSlave block diagram




www.opencores.org                 Rev 1.1                        3 of 30
   OpenCores                                                           6/8/2008




                                                                        3
                                                     Operation

Consider a system consisting of a USBHostSlave IP core, a USB PHY (eg Fairchild
USB1T11A), and a microprocessor (see figure (2) ).




                      Microprocessor

               Interrupts                   Wishbone bus
                          USBHostSlave
                            IP Core

                                             USB data/control

                             USB PHY

                        Figure 2USBHostSlave in a typical system




www.opencores.org                      Rev 1.1                           4 of 30
     OpenCores                                                                     6/8/2008

There are two scenarios to consider. Firstly where a USBHostSlave is configured as a
USB Host, and the second where it is configured as USB Device.
Let's consider the Host configuration first. On power up, the microprocessor will
configure USBHostSlave as a USB Host. If the Host is not connected to a USB Device,
then USBHostSlave will report that the USB line is in a disconnect state. When the Host
is connected to a Device, USBHostSlave will report the connection event and the
connection speed. Now the following USBHostSlave parameters can be configured;
•   USB speed.
•   USB polarity.
•   The USB address of the attached Device (Address zero is the default Device address).
•   The USB endpoint (endpoint zero is used for set up) within the attached Device.
Now that the Host has been configured, the Host can attempt to complete a transfer with
the attached USB Device. Let's use the example of the Host sending data to the USB
Device. First the USBHostSlave transmit FIFO will be loaded with data, then the
transaction type will be set, and finally the transaction request flag will be set. The
microprocessor detects that the transaction is complete by checking for the transaction
done flag to be set, or waiting for the transaction done interrupt.

Now let's take a look at the case where USBHostSlave is configured as a USB Device. On
power up, the microprocessor will configure USBHostSlave as a USB Device. If the
Device is not connected to a USB Host, then USBHostSlave will report that the USB line
is in a reset state. When the Device is connected to a Host, USBHostSlave will report the
connection event and the connection speed. Now the following USBHostSlave
parameters can be configured;
• USB speed.

•   USB polarity.
•   The USB address (Address zero is the default Device address).
•   Set the global endpoint enable flag
If the Device is expecting a transaction then it must be prepared to accept the transaction.
If an incoming data packet is expected then simply set the enable flag for the endpoint
that is expecting a transaction, and wait for the transaction done flag (or transaction done
interrupt) to be set. If the expected transaction involves outgoing data, then the endpoint
FIFO will have to be loaded with data before the enable flag is set.




www.opencores.org                         Rev 1.1                                     5 of 30
   OpenCores                                                         6/8/2008




                                                                      4
                                             Registers

USB Host Slave Common Registers

Register Address Name
0xe0             HOST_SLAVE_CONTROL_REG
0xe1             HOST_SLAVE_VERSION_REG

HOST_SLAVE_CONTROL_REG
Bit Position Name                           Description
      0      HOST_MODE                      Set to 1 to enable host mode. Set
                                            to 0 to enable slave mode.
      1      RESET_CORE                     Write only. Value is not latched.
                                            Set to 1 to reset all the logic
                                            including registers. Must wait 10
                                            usbClk cycles for reset to
                                            complete.

HOST_SLAVE_VERSION_REG
Bit Position Name                           Description
     [7:4]     VERSION_NUM_MAJOR            Major revision number
     [3:0]     VERSION_NUM_MINOR            Minor revision number


USB Host

Register Address    Name
0x0                 HOST_TX_CONTROL_REG
0x1                 HOST_TX_TRANS_TYPE_REG
0x2                 HOST_TX_LINE_CONTROL_REG
0x3                 HOST_TX_SOF_ENABLE_REG
0x4                 HOST_TX_ADDR_REG
0x5                 HOST_TX_ENDP_REG


www.opencores.org                 Rev 1.1                              6 of 30
   OpenCores                                                                 6/8/2008

Register Address    Name
0x6                 HOST_FRAME_NUM_MSP_REG
0x7                 HOST_FRAME_NUM_LSP_REG
0x8                 HOST_INTERRUPT_STATUS_REG
0x9                 HOST_INTERRUPT_MASK_REG
0xa                 HOST_RX_STATUS_REG
0xb                 HOST_RX_PID_REG
0xc                 HOST_RX_ADDR_REG
0xd                 HOST_RX_ENDP_REG
0xe                 HOST_RX_CONNECT_STATE_REG
0xf                 HOST_SOF_TIMER_MSB_REG

0x20                HOST_RX_FIFO_DATA
0x21                Reserved
0x22                HOST_RX_FIFO_DATA_COUNT_MSB
0x23                HOST_RX_FIFO_DATA_COUNT_LSB
0x24                HOST_RX_FIFO_CONTROL_REG

0x30                HOST_TX_FIFO_DATA
0x31                Reserved
0x32                Reserved
0x33                Reserved
0x34                HOST_TX_FIFO_CONTROL_REG




HOST_TX_CONTROL_REG
Bit Position Name                            Description
      0         TRANS_REQ_BIT                Set to 0 to disable transaction. Set to 1
                                             to enable transaction, automatically
                                             cleared when transaction complete.
       1            SOF_SYNC_BIT             Set to 1 to syncrhonize transaction
                                             with      the      end       of     SOF
                                             transmission.Transaction       will    be
                                             scheduled        for        transmission
                                             immediately after SOF transmission.
       2            PREAMBLE_ENABLE_BIT      Set to 1 to enable preamble. Should
                                             only be enabled when the host is
                                             connected to a low speed device via a
                                             hub. The preamble is a token which is
                                             prefixed to all packet transmissions,
                                             and is transmitted at full speed
                                             irrespective of the state of          the
                                             FULL_SPEED_LINE_RATE_BIT.


www.opencores.org                  Rev 1.1                                     7 of 30
   OpenCores                                                                   6/8/2008

Bit Position Name                               Description
      3      ISO_ENABLE_BIT                     Set to 1 to enable isochronous mode.
                                                In      isochronous      mode,    no
                                                acknowledgements are sent or
                                                received.           Note,        the
                                                TRANS_TYPE_REG must be set to
                                                either          IN_TRANS          or
                                                OUTDATA0_TRANS. Isochronous
                                                mode is not allowed with any other
                                                transaction types.

HOST_RX_CONNECT_STATE_REG
Bit Position Name                      Description
     [1:0]     RX_LINE_STATE           The                  contents                    of
                                       RX_CONNECT_STATE_REG               reflect      the
                                       current connection state, where;
                                       DISCONNECT = 0
                                       LOW_SPEED_CONNECT = 1
                                       FULL_SPEED_CONNECT = 2



HOST_INTERRUPT_STATUS_REG
Bit Position Name                        Description
      0         TRANS_DONE_BIT           Automatically set to 1 when a
                                         transaction is completed. Must be
                                         cleared by writing 1.
      1             RESUME_INT_BIT       Automatically set to 1 when resume
                                         state is detected. Must be cleared by
                                         writing 1.
      2             CONNECTION_EVENT_BIT Automatically set to 1 when a connect
                                         or disconnect occurs. Must be cleared
                                         by writing 1.
      3             SOF_SENT_BIT         Automatically set to 1 when a SOF
                                         transmission occurs. Must be cleared
                                         by writing 1.

HOST_INTERRUPT_MASK_REG
Bit Position Name                               Description
      0         TRANS_DONE_BIT                  Set to 1 to enable interrupt on
                                                transaction completion.
      1             RESUME_INT_BIT              Set to 1 to enable interrupt on resume
                                                detected.



www.opencores.org                     Rev 1.1                                       8 of 30
   OpenCores                                                                   6/8/2008

Bit Position Name                    Description
      2         CONNECTION_EVENT_BIT Set to 1 to enable interrupt on connect
                                     or disconnect event.
      3         SOF_SENT_BIT         Set to 1 to enable interrupt on SOF
                                     transmission.

HOST_RX_STATUS_REG
Bit Position Name                               Description
      0         CRC_ERROR_BIT                   When set to 1, indicates CRC error
                                                detected on the last transaction.
      1             BIT_STUFF_ERROR_BIT         When set to 1, indicates bit stuff error
                                                detected on the last transaction.
      2             RX_OVERFLOW_BIT             When set to 1, indicates insufficient
                                                free space in RX fifo to accept entire
                                                data packet.
      3             RX_TIME_OUT_BIT             When set to 1, indicates no response
                                                from USB device.
      4             NAK_RXED_BIT                When set to 1, indicates NAK received
                                                from USB device.
      5             STALL_RXED_BIT              When set to 1, indicates STALL
                                                received from USB device.
      6             ACK_RXED_BIT                When set to 1, indicates ACK received
                                                from USB device.
      7             DATA_SEQUENCE_BIT           If the last transaction was of type
                                                IN_TRANS, then this bit indicates the
                                                sequence number of the last receive
                                                packet. DATA0 = 0, DATA1 = 1.

HOST_TX_TRANS_TYPE_REG
Bit Position Name                               Description
     [1:0]      TRANSACTION_TYPE                SETUP_TRANS = 0
                                                IN_TRANS = 1
                                                OUTDATA0_TRANS = 2
                                                OUTDATA1_TRANS = 3
                                                These are the four basic types of
                                                transaction. The transaction types
                                                detailed in USB 1.1 (Setup, bulk, and
                                                isochronous) are composed of a series
                                                of one or more of these basic atomic
                                                transactions.

HOST_TX_LINE_CONTROL_REG



www.opencores.org                     Rev 1.1                                    9 of 30
   OpenCores                                                                 6/8/2008

Bit Position Name                                   Description
    [1:0]    TX_LINE_STATE                          When
                                                    DIRECT_CONTROL_BIT=1,T
                                                    X_LINE_STATE            directly
                                                    controls the state of the USB
                                                    physical     wires,      where;
                                                    TX_LINE_STATE [1] = D+
                                                    TX_LINE_STATE [0] = D-
     2      DIRECT_CONTROL_BIT                      Set to 1 to allow direct control
                                                    the state of the USB physical
                                                    wires. Clear to 0 for normal
                                                    operation.
     3      FULL_SPEED_LINE_POLARITY_BIT            Set to 1 to enable full speed line
                                                    polarity. That is J= differential
                                                    1, K= differential 0.
                                                    Clear to zero to enable low
                                                    speed line poarity. That is J=
                                                    differential 0, K= differential 1.
                                                    If the host is communicating
                                                    with a full speed device, then
                                                    full speed line polarity should
                                                    be enabled. If the host is
                                                    communicating with a low
                                                    speed device directly then full
                                                    speed line polarity should be
                                                    disabled. If the host is
                                                    communicating with a low
                                                    speed device via a hub, then
                                                    full speed line polarity should
                                                    be enabled.
     4      FULL_SPEED_LINE_RATE_BIT                Set to 1 to enable full speed line
                                                    rate of 12Mbps. Clear to 0 to
                                                    enable low speed line rate of
                                                    1.5Mbps. If the host is
                                                    communicating with a full
                                                    speed device, then full speed
                                                    line rate should be enabled. If
                                                    the host is communicating with
                                                    a low speed device full speed
                                                    line rate should be disabled.

HOST_TX_SOF_ENABLE_REG
Bit Position Name          Description
      0         SOF_EN_BIT If FULL_SPEED_LINE_POLARITY_BIT is set, then
                           setting this bit to 1 to enables automatic transmission


www.opencores.org                     Rev 1.1                                 10 of 30
   OpenCores                                                                  6/8/2008

Bit Position Name            Description
                             of SOF tokens every 1mS. Note that SOF tokens will
                             be transmitted at full speed line rate irrespective of the
                             state of FULL_SPEED_LINE_RATE_BIT.
                             If FULL_SPEED_LINE_POLARITY_BIT is clear,
                             then setting this bit to 1 to enables automatic
                             transmission of low speed EOP keep alive every 1mS.
                             Transition from 0 to 1 causes transmission of resume
                             state prior to EOP transmission. Note that this mode is
                             only used when the host is connected directly to a low
                             speed device.
                             Clear to 0 to disable automatic SOF/EOP
                             transmission, and allow any devices attached to the
                             host to enter the suspend state.

HOST_TX_ADDR_REG
Bit Position Name                            Description
     [6:0]      DEVICE_ADDRESS               USB Device address.

HOST_TX_ENDP_REG
Bit Position Name                            Description
     [3:0]      ENDP_ADDRESS                 Endpoint address.

HOST_FRAME_NUM_MSP_REG
Bit Position Name                            Description
     [2:0]   FRAME_NUM_MSP                   Most significant part of the frame
                                             number used for SOF transmission.
                                             That is FRAME_NUM_MSP =
                                             FRAME_NUM[10:8].

HOST_FRAME_NUM_LSP_REG
Bit Position Name                            Description
     [7:0]   FRAME_NUM_LSP                   Least significant part of the frame
                                             number used for SOF transmission.
                                             That is FRAME_NUM_LSP =
                                             FRAME_NUM[7:0].

HOST_SOF_TIMER_MSB_REG


Bit Position Name               Description
     [7:0]   HOST_SOF_TIMER_MSB Most significant byte of the SOF timer used


www.opencores.org                  Rev 1.1                                     11 of 30
   OpenCores                                                             6/8/2008

Bit Position Name                   Description
                                    for SOF transmission. Timer is incremented
                                    at 48MHz, thus there are 48000 ticks in a
                                    1mS frame.
                                    This register can be used to calculate the
                                    number of ticks remaining in a frame.
                                    Trem = 0xbb - HOST_SOF_TIMER_MSB

HOST_RX_PID_REG
Bit Position Name                           Description
     [3:0]      RECEIVE_PID                 Packet identifier for the last packet
                                            received.

HOST_RX_ADDR_REG
Bit Position Name                           Description
     [6:0]      RECEIVE_ADDRESS             Address from which the last receive
                                            packet was sent.
HOST_RX_ENDP_REG
Bit Position Name                           Description
     [3:0]      RECEIVE_ENDP                End point from which the last receive
                                            packet was sent.

HOST_RX_FIFO_DATA
Bit Position Name                           Description
     [7:0]      RX_FIFO_DATA                If the last transaction was an
                                            IN_TRANS, then the receive payload
                                            can be retrieved by reading
                                            RX_FIFO_DATA

HOST_TX_FIFO_DATA
Bit Position Name                           Description
     [7:0]      TX_FIFO_DATA                Prior      to  requesting   an
                                            OUTDATA0_TRANS          or  an
                                            OUTDATA1_TRANS , load transmit
                                            fifo with data by writing to
                                            TX_FIFO_DATA.




HOST_RX_FIFO_DATA_COUNT_MSB



www.opencores.org                 Rev 1.1                                12 of 30
   OpenCores                                                              6/8/2008

Bit Position Name                           Description
     [7:0]     FIFO_DATA_COUNT_MSB          MSByte of FIFO_DATA_COUNT.
                                            Indicates the number of data entries
                                            within the fifo.

HOST_RX_FIFO_DATA_COUNT_LSB
Bit Position Name                           Description
     [7:0]     FIFO_DATA_COUNT_LSB          LSByte of FIFO_DATA_COUNT.
                                            Indicates the number of data entries
                                            within the fifo.

HOST_[T,R]X_FIFO_CONTROL
Bit Position Name                           Description
      0           FIFO_FORCE_EMPTY          Write only. Set to 1 to delete all the
                                            data samples within the fifo.




   USB Slave (Device)

Register Address    Name
0x40                ENDPOINT0_CONTROL_REG
0x41                ENDPOINT0_STATUS_REG
0x42                ENDPOINT0_TRANSTYPE_STATUS_REG
0x43                ENDPOINT0_NAK_TRANSTYPE_STATUS_REG

0x44                ENDPOINT1_CONTROL_REG
0x45                ENDPOINT1_STATUS_REG
0x46                ENDPOINT1_TRANSTYPE_STATUS_REG
0x47                ENDPOINT1_NAK_TRANSTYPE_STATUS_REG

0x48                ENDPOINT2_CONTROL_REG
0x49                ENDPOINT2_STATUS_REG
0x4a                ENDPOINT2_TRANSTYPE_STATUS_REG
0x4b                ENDPOINT2_NAK_TRANSTYPE_STATUS_REG


www.opencores.org                 Rev 1.1                                 13 of 30
   OpenCores                                             6/8/2008

Register Address Name

0x4c                ENDPOINT3_CONTROL_REG
0x4d                ENDPOINT3_STATUS_REG
0x4e                ENDPOINT3_TRANSTYPE_STATUS_REG
0x4f                ENDPOINT3_NAK_TRANSTYPE_STATUS_REG

0x50                SC_CONTROL_REG
0x51                SC_LINE_STATUS_REG
0x52                SC_INTERRUPT_STATUS_REG
0x53                SC_INTERRUPT_MASK_REG
0x54                SC_ADDRESS
0x55                SC_FRAME_NUM_MSP
0x56                SC_FRAME_NUM_LSP

0x60                EP0_RX_FIFO_DATA
0x61                Reserved
0x62                EP0_RX_FIFO_DATA_COUNT_MSB
0x63                EP0_RX_FIFO_DATA_COUNT_LSB
0x64                EP0_RX_FIFO_CONTROL_REG

0x70                EP0_TX_FIFO_DATA
0x71                Reserved
0x72                Reserved
0x73                Reserved
0x74                EP0_TX_FIFO_CONTROL_REG

0x80                EP1_RX_FIFO_DATA
0x81                Reserved
0x82                EP1_RX_FIFO_DATA_COUNT_MSB
0x83                EP1_RX_FIFO_DATA_COUNT_LSB
0x84                EP1_RX_FIFO_CONTROL_REG

0x90                EP1_TX_FIFO_DATA
0x91                Reserved
0x92                Reserved
0x93                Reserved
0x94                EP1_TX_FIFO_CONTROL_REG

0xa0                EP2_RX_FIFO_DATA
0xa1                Reserved
0xa2                EP2_RX_FIFO_DATA_COUNT_MSB
0xa3                EP2_RX_FIFO_DATA_COUNT_LSB
0xa4                EP2_RX_FIFO_CONTROL_REG

0xb0                EP2_TX_FIFO_DATA
0xb1                Reserved


www.opencores.org                  Rev 1.1               14 of 30
   OpenCores                                                     6/8/2008

Register Address    Name
0xb2                Reserved
0xb3                Reserved
0xb4                EP2_TX_FIFO_CONTROL_REG

0xc0                EP3_RX_FIFO_DATA
0xc1                Reserved
0xc2                EP3_RX_FIFO_DATA_COUNT_MSB
0xc3                EP3_RX_FIFO_DATA_COUNT_LSB
0xc4                EP3_RX_FIFO_CONTROL_REG

0xd0                EP3_TX_FIFO_DATA
0xd1                Reserved
0xd2                Reserved
0xd3                Reserved
0xd4                EP3_TX_FIFO_CONTROL_REG

ENDPOINT[3..0]_CONTROL_REG
 Bit Position              Name                      Description
      0       ENDPOINT_ENABLE_BIT          Set to 1 to enable the
                                           endpoint. If endpoint is not
                                           enabled then it will not
                                           respond to any transactions.
                                           If endpoint is enabled, not
                                           ready, and not in
                                           isochronous mode, then all
                                           transactions will be NAK'd.
       1     ENDPOINT_READY_BIT            Set to 1 make the endpoint
                                           ready. If endpoint is enabled
                                           and ready then it can
                                           respond to a host inititiated
                                           transaction. Automatically
                                           cleared to 0 when
                                           transaction is complete.
       2     ENDPOINT_OUTDATA_SEQUENCE_BIT If set to 1 then the endpoint
                                           will respond to a host IN
                                           request with a DATA1
                                           packet, otherwise it will
                                           respond with a DATA0
                                           packet.
       3     ENDPOINT_SEND_STALL_BIT       If set to 1 and endpoint is
                                           enabled, ready, and not in
                                           isochronous mode, then
                                           endpoint will send STALL
                                           in response to a host
                                           inititiated transaction.


www.opencores.org                 Rev 1.1                         15 of 30
    OpenCores                                                                    6/8/2008

 Bit Position               Name                                      Description
      4       ENDPOINT_ISO_ENABLE_BIT                        Set to 1 to enable
                                                             isochronous transfers. In
                                                             isochronous mode the
                                                             endpoint does not send
                                                             acknowledgements, nor
                                                             does it expect to receive
                                                             acknowledgements.

ENDPOINT[3..0]_STATUS_REG
Bit Position Name                                 Description
      0         SC_CRC_ERROR_BIT                  When set to 1, indicates CRC error
                                                  detected on the last transaction.
       1           SC_BIT_STUFF_ERROR_BIT When set to 1, indicates bit stuff error
                                                  detected on the last transaction.
       2           SC_RX_OVERFLOW_BIT             When set to 1, indicates insufficient
                                                  free space in RX fifo to accept entire
                                                  data packet.
       3           SC_RX_TIME_OUT_BIT             When set to 1, indicates no response
                                                  from USB host.
       4           SC_NAK_SENT_BIT                When set to 1, indicates NAK sent to
                                                  USB host.
       5           SC_STALL_SENT_BIT              When set to 1, indicates STALL sent
                                                  to USB host.
       6           SC_ACK_RXED_BIT                When set to 1, indicates ACK received
                                                  from USB host.
       7           SC_DATA_SEQUENCE_BIT If the last transaction was of type
                                                  OUT_TRANS, then this bit indicates
                                                  the sequence number of the last
                                                  receive packet. DATA0 = 0, DATA1
                                                  = 1.
Note that SC_NAK_SENT_BIT refers to the last host inititiated transaction that occurred
whilst the endpoint was enabled, but not ready. The other bits in this register are not
effected by host transactions that are NAK'd, and they refer to the last transaction which
resulted in           ENDPOINT_READY_BIT being changed from 1 to 0.
SC_NAK_SENT_BIT is cleared to zero immediately after an enabled/ready transaction
is completed. Note that the usb slave endpoint cannot NAK a host transmission when the
endpoint is enabled and ready. So the NAK_SENT_BIT never refers to a transaction
which resulted in ENDPOINT_READY_BIT being changed from 1 to 0


ENDPOINT[3..0]_TRANSTYPE_STATUS_REG
Bit Position Name                                  Description
     [1:0]      TRANSACTION_TYPE                   SC_SETUP_TRANS = 0
                                                   SC_IN_TRANS = 1


www.opencores.org                        Rev 1.1                                  16 of 30
   OpenCores                                                                6/8/2008

Bit Position Name                           Description
                                            SC_OUTDATA_TRANS = 2
                                            This is the transaction type of the last
                                            transaction    which      resulted    in
                                            ENDPOINT_READY_BIT                 being
                                            changed from 1 to 0

ENDPOINT[3..0]_NAK_TRANSTYPE_STATUS_REG
Bit Position Name                           Description
     [1:0]      TRANSACTION_TYPE            SC_SETUP_TRANS = 0
                                            SC_IN_TRANS = 1
                                            SC_OUTDATA_TRANS = 2
                                            This is the transaction type of the last
                                            transaction which resulted in a NAK
                                            being sent to the host.

SC_CONTROL_REG
Bit      Name                                   Description
Position
    0 SC_GLOBAL_ENABLE_BIT                      When cleared to 0, all endpoints
                                                are disabled, and the slave will
                                                not respond to any host inititiated
                                                transactions.
 [2:1] SC_TX_LINE_STATE                         When
                                                SC_DIRECT_CONTROL_BIT=1
                                                ,SC_TX_LINE_STATE directly
                                                controls the state of the USB
                                                physical wires, where;
                                                SC_TX_LINE_STATE [2] = D+
                                       SC_TX_LINE_STATE [1] = D-
   3   SC_DIRECT_CONTROL_BIT           Set to 1 to allow direct control the
                                       state of the USB physical wires.
                                       Clear to 0 for normal operation.
   4   SC_FULL_SPEED_LINE_POLARITY_BIT Set to 1 to enable full speed line
                                       polarity. That is J= differential 1,
                                       K= differential 0.
                                                Clear to zero to enable low speed
                                                line poarity. That is J= differential
                                                0, K= differential 1.
   5   SC_FULL_SPEED_LINE_RATE_BIT              Set to 1 to enable full speed line
                                                rate of 12Mbps. Clear to 0 to
                                                enable low speed line rate of



www.opencores.org                 Rev 1.1                                    17 of 30
   OpenCores                                                                6/8/2008

Bit      Name                                    Description
Position
                                                 1.5Mbps.
   6       SC_CONNECT_TO_HOST_BIT                Controls the activation of the D+
                                                 and D- pull-ups. If set to 1, and
                                                 FULL_SPEED_LINE_RATE is
                                                 asserted, then the D+ line will be
                                                 pulled high. If set to 1, and
                                                 FULL_SPEED_LINE_RATE is
                                                 de-asserted, then the D- line will
                                                 be pulled high. If cleared to 0 then
                                                 neither D+ or D- will be pulled
                                                 high. The mechanism for
                                                 controlling the pull up resistors is
                                                 dependent on the USB PHY that
                                                 is used.

SC_LINE_STATUS_REG
Bit Position Name                   Description
     [1:0]   RX_LINE_STATE          The                  contents                  of
                                    RX_CONNECT_STATE_REG               reflect    the
                                    current connection state, where;
                                    RESET = 0
                                    LOW_SPEED_CONNECT = 1
                                    FULL_SPEED_CONNECT = 2
       2      VBUS_STATE            1 = +5V USB supply present.
                                    0 = +5V USB supply absent.

SC_INTERRUPT_STATUS_REG
Bit Position Name                            Description
      0      SC_TRANS_DONE_BIT               Set to 1 when a transaction is
                                             completed. Must be cleared by writing
                                             1.
       1      SC_RESUME_INT_BIT              Set to 1 when resume state is detected.
                                             Must be cleared by writing 1.
       2      SC_RESET_EVENT_BIT             Set to 1 when a change in reset state
                                             (D+ and D- low) is detected. ie either
                                             entered or left reset state. Must be
                                             cleared by writing 1.
       3      SC_SOF_RECEIVED_BIT            Set to 1 when a SOF packet is
                                             received. Must be cleared by writing 1.
       4      SC_NAK_SENT_INT_BIT            Set to 1 when a NAK sent. Must be
                                             cleared by writing 1.


www.opencores.org                  Rev 1.1                                   18 of 30
   OpenCores                                                               6/8/2008

Bit Position Name                           Description
      5      VBUS_DET_INT_BIT               Set to 1 when a change VBUS
                                            presence is detected. Must be cleared
                                            by writing 1.

SC_INTERRUPT_MASK_REG
Bit Position Name                           Description
      0      SC_TRANS_DONE_BIT              Set to 1 to enable interrupt on
                                            transaction complete.
      1      SC_RESUME_INT_BIT              Set to 1 to enable interrupt on resume
                                            detected.
      2      SC_RESET_EVENT_BIT             Set to 1 to enable interrupt on reset
                                            detected.
      3      SC_SOF_RECEIVED_BIT            Set to 1 to enable interrupt on SOF
                                            received.
      4      SC_NAK_SENT_INT_BIT            Set to 1 to enable interrupt on NAK'd
                                            transaction.

SC_ADDRESS
Bit Position Name                           Description
     [6:0]   DEVICE_ADDRESS                 USB Device address.



SC_FRAME_NUM_MSP
Bit Position Name                           Description
     [2:0]   SC_FRAME_NUM_MSP               Most significant part of the frame
                                            number received in the last SOF
                                            transmission. That is
                                            SC_FRAME_NUM_MSP                         =
                                            FRAME_NUM[10:8].

SC_FRAME_NUM_LSP
Bit Position Name                           Description
     [7:0]   SC_FRAME_NUM_LSP               Least significant part of the frame
                                            number received in the last SOF
                                            transmission. That is
                                            SC_FRAME_NUM_LSP                         =
                                            FRAME_NUM[7:0].




www.opencores.org                 Rev 1.1                                   19 of 30
   OpenCores                                                            6/8/2008

EP[3..0]_TX_FIFO_DATA
Bit Position Name                         Description
     [7:0]   TX_FIFO_DATA                 Prior to receiving a IN_TRANS, load
                                          transmit fifo with data by writing to
                                          TX_FIFO_DATA.

EP[3..0]_RX_FIFO_DATA
Bit Position Name                         Description
     [7:0]   RX_FIFO_DATA                 After         receiving            an
                                          OUTDATA_TRANS,               or     a
                                          SETUP_TRANS, get receive data
                                          from     fifo by     reading    from
                                          RX_FIFO_DATA.

EP[3..0]_RX_FIFO_DATA_COUNT_MSB
Bit Position Name                         Description
     [7:0]   FIFO_DATA_COUNT_MSB          MSByte of FIFO_DATA_COUNT.
                                          Indicates the number of data samples
                                          within the fifo.

EP[3..0]_RX_FIFO_DATA_COUNT_LSB
Bit Position Name                         Description
     [7:0]   FIFO_DATA_COUNT_LSB          LSByte of FIFO_DATA_COUNT.
                                          Indicates the number of data samples
                                          within the fifo.

EP[3..0]_[T,R]X_FIFO_CONTROL
Bit Position Name                         Description
      0      FIFO_FORCE_EMPTY             Write only. Set to 1 to delete all the
                                          data samples within the fifo.




www.opencores.org               Rev 1.1                                 20 of 30
    OpenCores                                                                    6/8/2008




                                                                                  5
                                                                   Clocks

 Name       Source    Rates (MHz)                        Remarks          Description
                      Max      Min             Res
 usbClk     Input     48.024   47.976          -         Duty cycle       USB system
            Pad                                          50/50.           clock.
 clk_i      Input     240        UsbClk/2                Duty cycle       Wishbone bus
            Pad                                          50/50.           clock.
                                   Table 1: List of clocks


Several Development kits, such as the Altera Nios Development Kit Cyclone Edition,
come with a 50MHz oscillator. Although the Cyclone PLL in the NIOS Development Kit
can be used to derive a 48.076923MHz clock, and this complies with the low speed
frequency tolerance (+/- 0.25%), it is not sufficient for full speed operation where a +/-
0.05% frequency tolerance is required. The 48MHz socketed half can oscillator on the
NIOS Development Kit can be replaced with a 50MHz oscillator (eg ECS ECS-2200B-
480, Digikey part number XC280-ND)




www.opencores.org                         Rev 1.1                                 21 of 30
    OpenCores                                                                   6/8/2008




                                                                                 6
                                                             IO Ports

Port                    Width   Direction         Description
usbClk                    1     input             usb logic clock. 48MHz +/- 0.25%
clk_i                     1     input             WISHBONE clock input. Can be asynchronous
                                                  to usbClk. 24MHz <= clk_i <= 240MHz
rst_i                     1     input             WISHBONE reset. Synchronous to clk_i.
                                                  Resets all logic.
address_i                 8     input             WISHBONE address input
data_i                    8     input             WISHBONE data input
data_o                    8     output            WISHBONE data output
writeEn                   1     input             WISHBONE write enable
strobe_i                  1     input             WISHBONE strobe input
ack_o                     1     output            WISHBONE acknowledge output
hostSOFSentIntOut         1     output            Host SOF sent interrupt
hostConnEventIntOut       1     output            Host connection event interrupt
hostResumeIntOut          1     output            Host resume interrupt
hostTransDoneIntOut       1     output            Host transaction done interrupt
slaveSOFRxedIntOut        1     output            SlaveSOF received interrupt
slaveResetEventIntOut     1     output            Slave reset event interrupt
slaveResumeIntOut         1     output            Slave resume interrupt
slaveTransDoneIntOut      1     output            Slave transaction done interrupt
slaveNAKSentIntOut        1     output            Slave NAK sent interrupt
USBWireDataIn             2     input             USB wire differential data input
                                                  USBWireDataIn[1] = D+
                                                  USBWireDataIn[0] = D-
USBWireDataOut            2     output            USB wire differential data output
                                                  USBWireDataOut[1] = D+
                                                  USBWireDataOut[0] = D-
USBWireDataOutTick        1     output            Debug output. 6MHz in full speed mode,
                                                  750KHz in low speed mode.
USBWireDataInTick         1     output            Debug output. 6MHz in full speed mode,
                                                  750KHz in low speed mode.
USBWireCtrlOut            1     output            USB tansmit output enable. Connect to OE pin
                                                  on USB PHY (eg invert and connect to OE_n
                                                  on USB1T11A)



www.opencores.org                       Rev 1.1                                  22 of 30
   OpenCores                                                                   6/8/2008


Port                Width    Direction         Description
USBFullSpeed          1      output            USB full speed enable. 1 = Full speed, 0 = low
                                               speed. Connect to FULL_SPEED pin on USB
                                               PHY. Typically used to control the USB line
                                               edge rate, which is different or full and low
                                               speed. (eg connect to SPEED on USB1T11A)
USBDPlusPullup        1      output            Enable USB device D+ 1.5K pull-up resistor. 1
                                               = enable, 0 = disable. (eg connect to ISP1102
                                               SOFTCON pin). Note that this output is only
                                               used in slave mode.
USBDMinusPullup       1      output            Enable USB device D- 1.5K pull-up resistor. 1
                                               = enable, 0 = disable. Note that this output is
                                               only used in slave mode, and is only required
                                               for implementations that require low speed
                                               support.
VBusDetect            1      input             USB +5V voltage detector. 1 = +5V present.
                                               (eg connect to ISP1102 VBUSDET pin). Note
                                               that this input is only used in slave mode.
                            Table 2: List of IO ports




www.opencores.org                    Rev 1.1                                    23 of 30
   OpenCores                                                                     6/8/2008




                                                                                 7
                  Wishbone Datasheet

                               WISHBONE DATASHEET
                               for USBHostSlave IP Core
              Description                                  Specification
General Description:                         8-bit slave input and output port
Supported cycles:                            SLAVE READ/WRITE
Data port Size:                              8-bit
Data port granularity:                       8-bit
Data port, max operand size:                 8-bit
Data transfer ordering:                      N/A
Data transfer sequencing:                    Undefined
                                             Signal Name            WISHBONE Equiv.
                                             address_i              ADR_I
Supported signal list and cross reference to data_i[7:0]            DAT_I()
equivalet WISHBONE signals:                  data_o[7:0]            DAT_O()
                                             we_i                   WE_I
                                             strobe_i               STB_I
                                             ack_o                  ACK_O
                                             clk_i                  CLK_I
                                             rst_i                  RST_I
                               Table 3: WISHBONE data sheet




www.opencores.org                        Rev 1.1                                 24 of 30
   OpenCores                                                                         6/8/2008




                                                                                     8
                Resource Utilization

       Design Entity                    Logic Cells                    Memory bits
     USBHostControl                         508                              0
     USBSlaveControl                        545                              0
 USBSerialInterfaceEngine                   984                              0
       WishBoneBI                            49                              0
      HostSlaveMux                           16                              0
8 slave FIFOs each 64x8-bit                 412                             4096
2 host FIFOs each 64x8-bit                  103                             1024
 USBHostSlave (top level)                  2617                             5120
                    Table 4 Resource utilization for Altera CycloneEP1C20




www.opencores.org                         Rev 1.1                                    25 of 30
    OpenCores                                                                    6/8/2008




                                                                                  9
                         USB Transceivers

The core must be used with a USB transciver that is capable of driving the USB cable,
and complies with the USB 1.1 specification. There are many options available, one of
the simplest is the Fairchild USB1T11A. The USB1T11A has seperate pins for transmit
and receive paths, and is available in a large SOIC package (nice for prototyping and
cheap PCBs), and a very small (3mm x 3mm) MLP package. The USB1T11A will
connect directly to the core apart from an inverter between ' USBWireCtrlOut' and
USB1T11A OEn.
Other parts such as the Philips ISP1105 offer more features such as larger I/O voltage
range, and soft connect. The ISP1105 and many other USB transcievers use a single pair
of pins for transmit and receive. Thus a tri-state buffer must be implemented in order to
connect the two seperate transmit receive pairs between the core and the transceiver, with
'USBWireCtrlOut' used to control the tri-state buffer output enable.




www.opencores.org                        Rev 1.1                                  26 of 30

