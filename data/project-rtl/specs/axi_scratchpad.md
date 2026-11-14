# 双端口AXI片上共享存储与读写仲裁

两个独立时钟域的AXI端口共享RAM，含各端口读写协议引擎、仲裁与可选输出流水级；适合作为scratchpad构件。

## 行为与时序契约

两个AXI slave端口A/B共享同一字节可寻址RAM，分别使用a_clk/a_rst与b_clk/b_rst，复位均同步高有效。
各端口接受AW/W/B与AR/R通道，保留ID、burst长度/size、WSTRB和RLAST语义，响应OKAY。支持FIXED与INCR；WRAP、exclusive、原子操作不在契约范围。
数据低字节对应低地址，WSTRB按byte lane更新，未使能字节保持不变。同一端口读写需要内部仲裁，A_INTERLEAVE/B_INTERLEAVE控制是否按拍交织；PIPELINE_OUTPUT为0/1控制输出寄存级。
背压时保持响应valid、ID、data、resp、last。接口复位清除事务状态但不清空已写RAM；不要依赖上电未写内存值。
禁止并发访问引起的同地址读写或双写冲突，跨端口同地址的可见性在先前写事务完成后检查；不保证冲突结果，也不是cache-coherent存储。
基线ADDR_WIDTH=12（4KiB）、DATA_WIDTH=32、ID_WIDTH=4、A/B输出流水为1/0、INTERLEAVE均1，时钟周期10/14。
必须交付双端口共享存储和完整协议/仲裁子模块，不能用两个不相干的私有内存替代。

## 编译配置

SystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。

## 顶层接口

```systemverilog
module axi_dp_ram #
(
    // Width of data bus in bits
    parameter DATA_WIDTH = 32,
    // Width of address bus in bits
    parameter ADDR_WIDTH = 16,
    // Width of wstrb (width of data bus in words)
    parameter STRB_WIDTH = (DATA_WIDTH/8),
    // Width of ID signal
    parameter ID_WIDTH = 8,
    // Extra pipeline register on output port A
    parameter A_PIPELINE_OUTPUT = 0,
    // Extra pipeline register on output port B
    parameter B_PIPELINE_OUTPUT = 0,
    // Interleave read and write burst cycles on port A
    parameter A_INTERLEAVE = 0,
    // Interleave read and write burst cycles on port B
    parameter B_INTERLEAVE = 0
)
(
    input  wire                   a_clk,
    input  wire                   a_rst,

    input  wire                   b_clk,
    input  wire                   b_rst,

    input  wire [ID_WIDTH-1:0]    s_axi_a_awid,
    input  wire [ADDR_WIDTH-1:0]  s_axi_a_awaddr,
    input  wire [7:0]             s_axi_a_awlen,
    input  wire [2:0]             s_axi_a_awsize,
    input  wire [1:0]             s_axi_a_awburst,
    input  wire                   s_axi_a_awlock,
    input  wire [3:0]             s_axi_a_awcache,
    input  wire [2:0]             s_axi_a_awprot,
    input  wire                   s_axi_a_awvalid,
    output wire                   s_axi_a_awready,
    input  wire [DATA_WIDTH-1:0]  s_axi_a_wdata,
    input  wire [STRB_WIDTH-1:0]  s_axi_a_wstrb,
    input  wire                   s_axi_a_wlast,
    input  wire                   s_axi_a_wvalid,
    output wire                   s_axi_a_wready,
    output wire [ID_WIDTH-1:0]    s_axi_a_bid,
    output wire [1:0]             s_axi_a_bresp,
    output wire                   s_axi_a_bvalid,
    input  wire                   s_axi_a_bready,
    input  wire [ID_WIDTH-1:0]    s_axi_a_arid,
    input  wire [ADDR_WIDTH-1:0]  s_axi_a_araddr,
    input  wire [7:0]             s_axi_a_arlen,
    input  wire [2:0]             s_axi_a_arsize,
    input  wire [1:0]             s_axi_a_arburst,
    input  wire                   s_axi_a_arlock,
    input  wire [3:0]             s_axi_a_arcache,
    input  wire [2:0]             s_axi_a_arprot,
    input  wire                   s_axi_a_arvalid,
    output wire                   s_axi_a_arready,
    output wire [ID_WIDTH-1:0]    s_axi_a_rid,
    output wire [DATA_WIDTH-1:0]  s_axi_a_rdata,
    output wire [1:0]             s_axi_a_rresp,
    output wire                   s_axi_a_rlast,
    output wire                   s_axi_a_rvalid,
    input  wire                   s_axi_a_rready,

    input  wire [ID_WIDTH-1:0]    s_axi_b_awid,
    input  wire [ADDR_WIDTH-1:0]  s_axi_b_awaddr,
    input  wire [7:0]             s_axi_b_awlen,
    input  wire [2:0]             s_axi_b_awsize,
    input  wire [1:0]             s_axi_b_awburst,
    input  wire                   s_axi_b_awlock,
    input  wire [3:0]             s_axi_b_awcache,
    input  wire [2:0]             s_axi_b_awprot,
    input  wire                   s_axi_b_awvalid,
    output wire                   s_axi_b_awready,
    input  wire [DATA_WIDTH-1:0]  s_axi_b_wdata,
    input  wire [STRB_WIDTH-1:0]  s_axi_b_wstrb,
    input  wire                   s_axi_b_wlast,
    input  wire                   s_axi_b_wvalid,
    output wire                   s_axi_b_wready,
    output wire [ID_WIDTH-1:0]    s_axi_b_bid,
    output wire [1:0]             s_axi_b_bresp,
    output wire                   s_axi_b_bvalid,
    input  wire                   s_axi_b_bready,
    input  wire [ID_WIDTH-1:0]    s_axi_b_arid,
    input  wire [ADDR_WIDTH-1:0]  s_axi_b_araddr,
    input  wire [7:0]             s_axi_b_arlen,
    input  wire [2:0]             s_axi_b_arsize,
    input  wire [1:0]             s_axi_b_arburst,
    input  wire                   s_axi_b_arlock,
    input  wire [3:0]             s_axi_b_arcache,
    input  wire [2:0]             s_axi_b_arprot,
    input  wire                   s_axi_b_arvalid,
    output wire                   s_axi_b_arready,
    output wire [ID_WIDTH-1:0]    s_axi_b_rid,
    output wire [DATA_WIDTH-1:0]  s_axi_b_rdata,
    output wire [1:0]             s_axi_b_rresp,
    output wire                   s_axi_b_rlast,
    output wire                   s_axi_b_rvalid,
    input  wire                   s_axi_b_rready
);
parameter VALID_ADDR_WIDTH = ADDR_WIDTH - $clog2(STRB_WIDTH);
parameter WORD_WIDTH = STRB_WIDTH;
parameter WORD_SIZE = DATA_WIDTH/WORD_WIDTH;
endmodule
```

## 验证边界

33个16拍写突发，576拍读回；全部字节先通过公开接口初始化，之后全/零/部分WSTRB覆盖；双端口并发、跨端口读回、单端口同时读写非冲突区域、B/R阻塞稳定性、ID/RLAST及接口复位后的数据保留。

- Only aligned full-width INCR bursts in 4KiB/32-bit configuration; no narrow/FIXED burst, collision or atomic/coherence verification.
- Digital two-clock simulation is not physical CDC/metastability or SRAM macro sign-off.

## 来源与兼容性

https://github.com/alexforencich/verilog-axi/tree/516bd5dadc3365b7f9e225d2af8fe0b8d804fe53

原版直接编译；候选回放仅去掉静态无效参数诊断。测试不窥探内部RAM，只检查公开AXI端口。

MIT许可；版权及许可原文保留于sources/alexforencich/verilog-axi/COPYING，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。
