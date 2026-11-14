# Verilog RTL

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)；本文件仅补充Verilog语义与示例，通用流程和权限不重复。

## 方言与编码要点

- 用`.v/.vh`及工程指定方言；需要传统Verilog兼容性时优先2001/2005。TB方言不改变DUT语言，不能混入`logic/always_ff/always_comb/typedef enum`。
- 显式声明类型、位宽和符号性，不依赖隐式网络。`assign`驱动`wire`，过程赋值驱动`reg`；`reg`本身不意味着触发器。一个信号一个驱动源，不混合过程/连续驱动。
- 简单组合式用`assign`；分支用`always @*`与阻塞赋值`=`，先给默认值再覆盖。`case`显式处理`default`，不用`casex`掩盖未知态；跨周期保持不能靠漏赋值。
- 时序块用非阻塞赋值`<=`，同沿读取旧状态。同步复位只在采样沿生效，异步复位敏感列表含正确边沿；不能为过测互换。FSM用有意义的`localparam`，保留非法状态处理与更新优先级。
- 加法进位需扩展操作数；核对中间表达式、无尺寸常量、符号扩展/截断和移位。`$clog2(1)`、最小宽度、非二次幂深度可能导致零宽或越界；系统函数还须符合实际方言。
- 内部名优先`lower_snake_case`，参数/状态常量用`UPPER_SNAKE_CASE`；`_reg/_next`或`_q/_d`保持一致，公开接口不改名。按接口、常量、信号、组合、时序组织，简单模块不堆空分区。

源码与构建文件列表包含全部子模块、头文件及已声明依赖，include搜索路径和宏沿用工程约定。不要用仿真延时、force/release、跨层窥探或文件I/O代替硬件。FPGA存储器初始化等特性必须确认目标综合工具支持；不能将仿真行为当作综合结果。

## 示例（保持契约，不直接套用）

以下两个小模块分别说明位宽扩展和寄存器更新。使用时按自己的接口、方言与复位契约调整，不能把示例当作当前工程已通过验证的证据。

### 两个无符号8位输入，完整9位和

```verilog
module add_with_carry (
    input  wire [7:0] operand_a,
    input  wire [7:0] operand_b,
    output wire [8:0] sum
);
    // 扩展操作数，明确保留最高位进位。
    assign sum = {1'b0, operand_a} + {1'b0, operand_b};
endmodule
```

若契约只要低8位，应明确截断，不擅自扩大端口。

### 上升沿、同步高有效复位优先于使能

```verilog
module enabled_register (
    input  wire       clk,
    input  wire       rst,
    input  wire       enable,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 8'd0;
        end else if (enable) begin
            data_out <= data_in;
        end
        // 未使能时由触发器保持原值，无需自赋值。
    end
endmodule
```

该写法不适用于异步复位，不能为风格改变复位或多加一拍。测试复位与使能同时有效、未使能保持、两次采样间的数据变化，以及复位是否只在约定采样沿生效。

使用本次源码运行工程的编译、Lint和自检查TB。Lint不代替功能仿真；保行为重构需要原回归通过，并说明修改改善了什么。
