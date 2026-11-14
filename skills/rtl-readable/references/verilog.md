# Verilog RTL

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)；本文件仅补充Verilog语义与示例，通用流程和权限不重复。

## 方言与编码要点

- 用`.v/.vh`，优先Verilog-2001/2005，服从清单的Icarus方言；少数项目需要2012。TB方言不改变DUT语言，不能混入`logic/always_ff/always_comb/typedef enum`。
- 显式声明类型、位宽和符号性，不依赖隐式网络。`assign`驱动`wire`，过程赋值驱动`reg`；`reg`本身不意味着触发器。一个信号一个驱动源，不混合过程/连续驱动。
- 简单组合式用`assign`；分支用`always @*`与阻塞赋值`=`，先给默认值再覆盖。`case`显式处理`default`，不用`casex`掩盖未知态；跨周期保持不能靠漏赋值。
- 时序块用非阻塞赋值`<=`，同沿读取旧状态。同步复位只在采样沿生效，异步复位敏感列表含正确边沿；不能为过测互换。FSM用有意义的`localparam`，保留非法状态处理与更新优先级。
- 加法进位需扩展操作数；核对中间表达式、无尺寸常量、符号扩展/截断和移位。`$clog2(1)`、最小宽度、非二次幂深度可能导致零宽或越界；系统函数还须符合实际方言。
- 内部名优先`lower_snake_case`，参数/状态常量用`UPPER_SNAKE_CASE`；`_reg/_next`或`_q/_d`保持一致，公开接口不改名。按接口、常量、信号、组合、时序组织，简单模块不堆空分区。

完整JSON快照须包含全部子模块与头文件；include为相对项目根目录的本地双引号字面量。允许常规宏，但候选先隔离预处理；展开后仅允许`$clog2/$signed/$unsigned/$bits`系统函数。DUT不用`initial`初始化、`#`延时、仿真I/O、`force/release`或层次引用。这是保守策略，不是可综合性证明。

## 示例（保持契约，不直接套用）

两个公开独立模块仅说明写法，不是人工审核的few-shot数据集。[tests/test_skill.py](../../../tests/test_skill.py)提取代码，以Icarus/vvp检查加法65,536组二值输入、寄存器256个采样值及同步复位/优先级/使能保持；另用`-g2005`检查DUT方言。缺工具时明确skip，示例成绩不代表新候选通过。

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

该写法不适用于异步复位，不能为风格改变复位或多加一拍。验证使用本轮完整源码及可信TB，检查接口/层次与完整日志；不修改TB或链接参考RTL。

可读性方法为`static-heuristic-v1`，不是语义/锁存器检查；功能、Lint与评分状态分开报告，重构遵循主文档的严格接受/回退条件。
