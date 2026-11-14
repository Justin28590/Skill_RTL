# AXI-Stream 位宽转换缓冲项目

同步高有效复位。实现带FIFO的AXI-Stream宽度转换，低有效字节先打包，保留tkeep/tlast/tid/tdest/tuser及ready/valid背压；阻塞时输出稳定。实现公开参数、帧控制和状态接口。基线DEPTH=64、8→32位、ID/DEST启用、其他默认，覆盖256字节/16帧、输入空隙及输出背压；不代表所有参数组合验证。

## 编译配置

原生语言：verilog。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。

## 顶层接口

```systemverilog
module axis_fifo_adapter #
(
    // FIFO depth in words
    // KEEP_WIDTH words per cycle if KEEP_ENABLE set
    // Rounded up to nearest power of 2 cycles
    parameter DEPTH = 4096,
    // Width of input AXI stream interface in bits
    parameter S_DATA_WIDTH = 8,
    // Propagate tkeep signal on input interface
    // If disabled, tkeep assumed to be 1'b1
    parameter S_KEEP_ENABLE = (S_DATA_WIDTH>8),
    // tkeep signal width (words per cycle) on input interface
    parameter S_KEEP_WIDTH = ((S_DATA_WIDTH+7)/8),
    // Width of output AXI stream interface in bits
    parameter M_DATA_WIDTH = 8,
    // Propagate tkeep signal on output interface
    // If disabled, tkeep assumed to be 1'b1
    parameter M_KEEP_ENABLE = (M_DATA_WIDTH>8),
    // tkeep signal width (words per cycle) on output interface
    parameter M_KEEP_WIDTH = ((M_DATA_WIDTH+7)/8),
    // Propagate tid signal
    parameter ID_ENABLE = 0,
    // tid signal width
    parameter ID_WIDTH = 8,
    // Propagate tdest signal
    parameter DEST_ENABLE = 0,
    // tdest signal width
    parameter DEST_WIDTH = 8,
    // Propagate tuser signal
    parameter USER_ENABLE = 1,
    // tuser signal width
    parameter USER_WIDTH = 1,
    // number of RAM pipeline registers in FIFO
    parameter RAM_PIPELINE = 1,
    // use output FIFO
    // When set, the RAM read enable and pipeline clock enables are removed
    parameter OUTPUT_FIFO_ENABLE = 0,
    // Frame FIFO mode - operate on frames instead of cycles
    // When set, m_axis_tvalid will not be deasserted within a frame
    // Requires LAST_ENABLE set
    parameter FRAME_FIFO = 0,
    // tuser value for bad frame marker
    parameter USER_BAD_FRAME_VALUE = 1'b1,
    // tuser mask for bad frame marker
    parameter USER_BAD_FRAME_MASK = 1'b1,
    // Drop frames larger than FIFO
    // Requires FRAME_FIFO set
    parameter DROP_OVERSIZE_FRAME = FRAME_FIFO,
    // Drop frames marked bad
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    parameter DROP_BAD_FRAME = 0,
    // Drop incoming frames when full
    // When set, s_axis_tready is always asserted
    // Requires FRAME_FIFO and DROP_OVERSIZE_FRAME set
    parameter DROP_WHEN_FULL = 0,
    // Mark incoming frames as bad frames when full
    // When set, s_axis_tready is always asserted
    // Requires FRAME_FIFO to be clear
    parameter MARK_WHEN_FULL = 0,
    // Enable pause request input
    parameter PAUSE_ENABLE = 0,
    // Pause between frames
    parameter FRAME_PAUSE = FRAME_FIFO
)
(
    input  wire                     clk,
    input  wire                     rst,

    /*
     * AXI input
     */
    input  wire [S_DATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [S_KEEP_WIDTH-1:0]  s_axis_tkeep,
    input  wire                     s_axis_tvalid,
    output wire                     s_axis_tready,
    input  wire                     s_axis_tlast,
    input  wire [ID_WIDTH-1:0]      s_axis_tid,
    input  wire [DEST_WIDTH-1:0]    s_axis_tdest,
    input  wire [USER_WIDTH-1:0]    s_axis_tuser,

    /*
     * AXI output
     */
    output wire [M_DATA_WIDTH-1:0]  m_axis_tdata,
    output wire [M_KEEP_WIDTH-1:0]  m_axis_tkeep,
    output wire                     m_axis_tvalid,
    input  wire                     m_axis_tready,
    output wire                     m_axis_tlast,
    output wire [ID_WIDTH-1:0]      m_axis_tid,
    output wire [DEST_WIDTH-1:0]    m_axis_tdest,
    output wire [USER_WIDTH-1:0]    m_axis_tuser,

    /*
     * Pause
     */
    input  wire                     pause_req,
    output wire                     pause_ack,

    /*
     * Status
     */
    output wire [$clog2(DEPTH):0]   status_depth,
    output wire [$clog2(DEPTH):0]   status_depth_commit,
    output wire                     status_overflow,
    output wire                     status_bad_frame,
    output wire                     status_good_frame
);
endmodule
```

## 项目公开文档

来源：https://github.com/alexforencich/verilog-axis/tree/48ff7a7e2ef782cf778d47910cf85835c64b1bce

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

许可：MIT，保留原始版权及许可，见数据集LICENSES.md和锁定源码中的LICENSE/COPYING。
