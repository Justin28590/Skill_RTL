# 异步时钟域流桥接、帧FIFO与位宽转换

输入/输出位宽转换和异步帧FIFO，包含跨域指针同步、背压与坏帧丢弃；不是把同步FIFO换一个名称。

## 行为与时序契约

s_clk/s_rst与m_clk/m_rst分别控制输入/输出时钟域。复位协调施加于两侧，释放后允许同步延迟；复位清空在途数据/未完成帧。独立单侧复位行为未纳入本契约验证。
两侧均为AXI-Stream握手，阻塞时保持所有字段。按低字节lane顺序组包/拆包；保留tkeep/tlast及启用的ID/dest/user。
S/M_DATA_WIDTH均为相同byte lane位宽的整数倍，lane数比例为整数；KEEP关闭时该侧视作单lane。
FRAME_FIFO=1时完整帧提交后才对输出可见，未完成帧不能泄漏。DEPTH按输入byte lane单位计数，RAM侧深度向上取2的幂；正常满状态应背压。
DROP_BAD_FRAME=1按帧末USER_BAD_FRAME_MASK/VALUE标记丢弃整帧，s_status_bad_frame脉冲计数；DROP_OVERSIZE_FRAME处理超深度帧，DROP_WHEN_FULL可选择满时丢弃。上述drop参数约束必须满足原公开声明，不能无条件吞掉正确帧。
PAUSE_ENABLE启用后响应s/m_pause_req并反馈ack，FRAME_PAUSE决定只在帧间暂停；本轮pause关闭。
基线DEPTH=64，8→32位，keep启用，4位ID/dest，1位user，FRAME_FIFO=1、DROP_BAD_FRAME=1、DROP_OVERSIZE_FRAME=1、DROP_WHEN_FULL=0，其他参数默认。
源端在一帧内保持ID/dest，坏帧user只在末拍标记。必须有真正跨时钟域存储/同步逻辑，不允许直接组合连通。

## 编译配置

SystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。

## 顶层接口

```systemverilog
module axis_async_fifo_adapter #
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
    /*
     * AXI input
     */
    input  wire                     s_clk,
    input  wire                     s_rst,
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
    input  wire                     m_clk,
    input  wire                     m_rst,
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
    input  wire                     s_pause_req,
    output wire                     s_pause_ack,
    input  wire                     m_pause_req,
    output wire                     m_pause_ack,

    /*
     * Status
     */
    output wire [$clog2(DEPTH):0]   s_status_depth,
    output wire [$clog2(DEPTH):0]   s_status_depth_commit,
    output wire                     s_status_overflow,
    output wire                     s_status_bad_frame,
    output wire                     s_status_good_frame,
    output wire [$clog2(DEPTH):0]   m_status_depth,
    output wire [$clog2(DEPTH):0]   m_status_depth_commit,
    output wire                     m_status_overflow,
    output wire                     m_status_bad_frame,
    output wire                     m_status_good_frame
);

endmodule
```

## 验证边界

两套时钟半周期3/5与7/4，各48帧、长度1..17，各输出41好帧/丢弃7坏帧；输入快/输出快、长时间阻塞到满、宽度打包和部分末拍、逐字节/ID/dest/last检查、阻塞稳定性、协调复位丢弃未完成帧。

- Digital functional CDC simulation only; not a metastability, timing-constraint or formal CDC proof.
- No single-sided reset, oversize/drop-when-full, pause or arbitrary-width configuration coverage.

## 来源与兼容性

https://github.com/alexforencich/verilog-axis/tree/48ff7a7e2ef782cf778d47910cf85835c64b1bce

原版直接编译；候选回放仅去掉静态无效参数诊断，不改Gray指针/同步、帧提交或位宽转换逻辑。

MIT许可；版权及许可原文保留于sources/alexforencich/verilog-axis/COPYING，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。
