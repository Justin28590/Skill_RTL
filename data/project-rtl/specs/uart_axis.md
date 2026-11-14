# AXI-Stream 全双工 UART

同步高有效复位rst。8位默认数据宽度，8N1、LSB先传。prescale为位周期的1/8，调用方保持稳定且非零。TX/RX独立ready/valid接口，发送方持有数据直到握手。RX只有有限缓冲，消费端应及时接收；报告溢出和停止位错误。完整实现公开参数及收发模块。测试prescale=2、16个双向字节及停止位；未穷举错误帧。

## 编译配置

原生语言：verilog。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。

## 顶层接口

```systemverilog
module uart #
(
    parameter DATA_WIDTH = 8
)
(
    input  wire                   clk,
    input  wire                   rst,

    /*
     * AXI input
     */
    input  wire [DATA_WIDTH-1:0]  s_axis_tdata,
    input  wire                   s_axis_tvalid,
    output wire                   s_axis_tready,

    /*
     * AXI output
     */
    output wire [DATA_WIDTH-1:0]  m_axis_tdata,
    output wire                   m_axis_tvalid,
    input  wire                   m_axis_tready,

    /*
     * UART interface
     */
    input  wire                   rxd,
    output wire                   txd,

    /*
     * Status
     */
    output wire                   tx_busy,
    output wire                   rx_busy,
    output wire                   rx_overrun_error,
    output wire                   rx_frame_error,

    /*
     * Configuration
     */
    input  wire [15:0]            prescale

);
endmodule
```

## 项目公开文档

来源：https://github.com/alexforencich/verilog-uart/tree/1b867e53af738e4a8bc7c839ca2f1c07f40382dc

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

许可：MIT，保留原始版权及许可，见数据集LICENSES.md和锁定源码中的LICENSE/COPYING。
