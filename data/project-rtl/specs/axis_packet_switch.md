# 多端口AXI-Stream分组交换与仲裁互连

可参数化多输入/多输出流交换，目的路由、逐输出仲裁、整帧锁定和skid缓冲；用于加速器流互连，不是完整NoC。

## 行为与时序契约

clk上升沿；rst同步高有效，清空缓冲和路由/仲裁状态。
各接口均为标准ready/valid握手，valid=1且ready=0时必须保持数据和所有边带稳定。
端口i对应各扁平总线的低位起第i个切片。保留tdata/tkeep/tlast/tid/tdest/tuser语义。
每个输入在帧首选择输出，直到tlast握手完成前保持整帧路由；同一输出不能混入另一输入的帧。
M_BASE=0时使用输入tdest的最高$clog2(M_COUNT)位选输出，M_COUNT=1时忽略路由位；
否则M_TOP=0表示逐输出精确匹配M_BASE，否则使用包含端点的[M_BASE,M_TOP]范围。
M_CONNECT中第m*S_COUNT+s位决定输入s能否到输出m；无匹配或禁止连接的帧被接收并丢弃。
UPDATE_TID启用时，输出ID高$clog2(S_COUNT)位标记输入端口，低位保留输入ID；tdest截取到M_DEST_WIDTH。
KEEP/ID/USER禁用时分别输出全1/0/0。S_REG_TYPE/M_REG_TYPE为0旁路、1简单缓冲、2 skid缓冲。
仲裁按整帧执行，ARB_TYPE_ROUND_ROBIN=1轮询否则固定优先级；ARB_LSB_HIGH_PRIORITY选择优先方向。
保留全部公开参数及合法配置行为、实际仲裁器/缓冲子模块。时延可随握手和缓冲变化，不要求固定拍数。
验证配置为4入2出、32位data、4位keep、4/6位输入/输出ID、2位dest、1位user，ID更新开启，双侧skid及轮询仲裁。

## 编译配置

SystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。

## 顶层接口

```systemverilog
module axis_switch #
(
    // Number of AXI stream inputs
    parameter S_COUNT = 4,
    // Number of AXI stream outputs
    parameter M_COUNT = 4,
    // Width of AXI stream interfaces in bits
    parameter DATA_WIDTH = 8,
    // Propagate tkeep signal
    parameter KEEP_ENABLE = (DATA_WIDTH>8),
    // tkeep signal width (words per cycle)
    parameter KEEP_WIDTH = ((DATA_WIDTH+7)/8),
    // Propagate tid signal
    parameter ID_ENABLE = 0,
    // input tid signal width
    parameter S_ID_WIDTH = 8,
    // output tid signal width
    parameter M_ID_WIDTH = S_ID_WIDTH+$clog2(S_COUNT),
    // output tdest signal width
    parameter M_DEST_WIDTH = 1,
    // input tdest signal width
    // must be wide enough to uniquely address outputs
    parameter S_DEST_WIDTH = M_DEST_WIDTH+$clog2(M_COUNT),
    // Propagate tuser signal
    parameter USER_ENABLE = 1,
    // tuser signal width
    parameter USER_WIDTH = 1,
    // Output interface routing base tdest selection
    // Concatenate M_COUNT S_DEST_WIDTH sized constants
    // Port selected if M_BASE <= tdest <= M_TOP
    // set to zero for default routing with tdest MSBs as port index
    parameter M_BASE = 0,
    // Output interface routing top tdest selection
    // Concatenate M_COUNT S_DEST_WIDTH sized constants
    // Port selected if M_BASE <= tdest <= M_TOP
    // set to zero to inherit from M_BASE
    parameter M_TOP = 0,
    // Interface connection control
    // M_COUNT concatenated fields of S_COUNT bits
    parameter M_CONNECT = {M_COUNT{{S_COUNT{1'b1}}}},
    // Update tid with routing information
    parameter UPDATE_TID = 0,
    // Input interface register type
    // 0 to bypass, 1 for simple buffer, 2 for skid buffer
    parameter S_REG_TYPE = 0,
    // Output interface register type
    // 0 to bypass, 1 for simple buffer, 2 for skid buffer
    parameter M_REG_TYPE = 2,
    // select round robin arbitration
    parameter ARB_TYPE_ROUND_ROBIN = 1,
    // LSB priority selection
    parameter ARB_LSB_HIGH_PRIORITY = 1
)
(
    input  wire                             clk,
    input  wire                             rst,

    /*
     * AXI Stream inputs
     */
    input  wire [S_COUNT*DATA_WIDTH-1:0]    s_axis_tdata,
    input  wire [S_COUNT*KEEP_WIDTH-1:0]    s_axis_tkeep,
    input  wire [S_COUNT-1:0]               s_axis_tvalid,
    output wire [S_COUNT-1:0]               s_axis_tready,
    input  wire [S_COUNT-1:0]               s_axis_tlast,
    input  wire [S_COUNT*S_ID_WIDTH-1:0]    s_axis_tid,
    input  wire [S_COUNT*S_DEST_WIDTH-1:0]  s_axis_tdest,
    input  wire [S_COUNT*USER_WIDTH-1:0]    s_axis_tuser,

    /*
     * AXI Stream outputs
     */
    output wire [M_COUNT*DATA_WIDTH-1:0]    m_axis_tdata,
    output wire [M_COUNT*KEEP_WIDTH-1:0]    m_axis_tkeep,
    output wire [M_COUNT-1:0]               m_axis_tvalid,
    input  wire [M_COUNT-1:0]               m_axis_tready,
    output wire [M_COUNT-1:0]               m_axis_tlast,
    output wire [M_COUNT*M_ID_WIDTH-1:0]    m_axis_tid,
    output wire [M_COUNT*M_DEST_WIDTH-1:0]  m_axis_tdest,
    output wire [M_COUNT*USER_WIDTH-1:0]    m_axis_tuser
);
parameter CL_S_COUNT = $clog2(S_COUNT);
parameter CL_M_COUNT = $clog2(M_COUNT);
parameter S_ID_WIDTH_INT = S_ID_WIDTH > 0 ? S_ID_WIDTH : 1;
parameter M_DEST_WIDTH_INT = M_DEST_WIDTH > 0 ? M_DEST_WIDTH : 1;
endmodule
```

## 验证边界

4入2出，两个复位分隔epoch共192帧，1..7拍/帧；四输入竞争同一输出、多输出并行路由、输入气泡、长输出阻塞及独立背压；核对每拍数据/keep/last/ID/dest/user、帧内不交织、输出阻塞稳定性、无丢失/重复及复位清空在途缓冲。

- Only the documented 4x2 round-robin/skid-buffer configuration is tested; fixed priority, custom address ranges and disconnected-route dropping are not covered.
- Packet stream switch only, not a mesh NoC, virtual-channel router or cache-coherent fabric.

## 来源与兼容性

https://github.com/alexforencich/verilog-axis/tree/48ff7a7e2ef782cf778d47910cf85835c64b1bce

原版可直接编译。候选回放副本仅删除静态配置打印/无效参数诊断，不修改路由、仲裁或数据通路；正常模型候选的安全策略不放宽。

MIT许可；版权及许可原文保留于sources/alexforencich/verilog-axis/COPYING，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。
