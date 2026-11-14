# SystemVerilog SPI 命令/读写控制器

同步低有效nrst。spi_clk是同步分频输入，每半周期至少2个系统周期。命令上升沿锁存mosi_data；写命令只发送，读命令先发送命令字再采样MISO。默认8位MSB先行、CPOL=0；CPOL=1反转时钟。ncs低有效，oe在发送阶段为1。数据在SPI下降沿更新、上升沿采样。支持公开参数，不在busy时发新命令。基线测试mode0两次写、全0/全1读；未穷举其他模式和宽度。

## 编译配置

原生语言：systemverilog。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。

## 顶层接口

```systemverilog
module spi_master #( parameter

  bit CPOL = 0,                  // Clock polarity for SPI interface
                                 // 0 - SPI mode 0
                                 //     data updates on rising edge
                                 //     data reads on falling edge
                                 // 1 - SPI mode 2
                                 //     data updates on falling edge
                                 //     data reads on rising edge
  parameter bit FREE_RUNNING_SPI_CLK = 0,  // 0 - clk_pin is active only when ncs_pin = 0
                                 // 1 - clk pin is always active
  parameter bit [5:0] MOSI_DATA_WIDTH = 8, // data word width in bits
  parameter bit WRITE_MSB_FIRST = 1,       // 0 - LSB first
                                 // 1 - MSB first
  parameter bit [5:0] MISO_DATA_WIDTH = 8, // data word width in bits
  parameter bit READ_MSB_FIRST = 1         // 0 - LSB first
                                 // 1 - MSB first
)(
  input clk,                     // system clock
  input nrst,                    // reset (inversed)

  input spi_clk,                 // prescaler clock
                                 // spi_clk must be >= 2 clk cycles
                                 // must be synchronous multiple of clk cycles

  input spi_wr_cmd,              // spi write command, shifting begins on rising edge
  input spi_rd_cmd,              // spi read command, shifting begins on rising edge
  output logic spi_busy,         // shifting is active

  input [MOSI_DATA_WIDTH-1:0] mosi_data,            // data for shifting out from master
  output logic [MISO_DATA_WIDTH-1:0] miso_data,     // shifted in data from slave

  output logic clk_pin,          // spi master's clock pin
  output logic ncs_pin = 1,      // spi master's chip select (inversed)
  output logic mosi_pin = 0,     // spi master's data in
  output logic oe_pin = 0,       // spi master's output enable
                                 // in case of using bidirectional buffer for SDIO pin
  input miso_pin                 // spi master's data in
);
endmodule
```

## 项目公开文档

来源：https://github.com/pConst/basic_verilog/tree/2654273b2c4e556a98e806f3a19b52c9b3c74614

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

接口摘录作者 Konstantin Pavlov；原件及本派生接口摘录依 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。构建副本显式补齐parameter关键字；SPI将edge_detect复位端口旧名nrst映射为anrst，不改变顶层端口或数据通路。
