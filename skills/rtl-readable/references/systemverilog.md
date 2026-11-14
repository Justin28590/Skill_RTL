# SystemVerilog RTL

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)；目标是可综合DUT，不是SystemVerilog验证平台。

## 方言与编码要点

- 新文件用`.sv/.svh`，允许已有兼容`.v/.vh`。工程参数可能为`.v`启用SV，扩展名不能覆盖已确认的目标语言。Icarus `-g2012`并非完整SV实现，解析失败也可能是工具限制。
- 保留工程的文件列表、include路径和宏；package需在使用方之前编译。使用interface/modport、struct或SVA前确认当前仿真/综合工具支持，不把某个后端的限制推广为SystemVerilog语言禁令。
- `logic`是四态数据类型，不代表寄存器也不解决多驱动；解析网络显式用net。不得用二态`bit`掩盖X/Z，也不把`===`等测试比较惯用法直接当综合数据通路写法。
- `logic [7:0] data`和`logic data [7:0]`不是同一接口，保留packed/unpacked维度和符号性。`int`默认有符号、32位，谨防意外扩大硬件；检查无尺寸常量、转换、拼接和移位的中间宽度。
- `always_comb`用阻塞赋值与完整默认值，不自动补齐漏赋值；避免隐晦先读后写、时钟/延时或副作用任务。简单组合式可用`assign`。
- `always_ff`用非阻塞赋值，状态不能由其他过程写入。同步复位在采样沿内判断；异步低有效复位才用`@(posedge clk or negedge rst_n)`并检查`!rst_n`。不能为过测互换，也不为风格引入`always_latch`。
- FSM可用显式宽度的`typedef enum logic`，保留复位状态、外部可观察编码与非法状态恢复。`unique/priority`影响诊断/综合假设，不能替代完整分支或把非法输入变成don't-care。
- struct、数组、function、generate只在工具支持且确实简化实现时使用。class、随机约束、UVM、动态容器、DPI、测试时钟块不放入DUT；不加入/删除断言改变测试判据。

注意宏、timescale和default_nettype对其他编译单元的影响，DUT与TB按工程约定隔离。工具不支持某特性时，选择等价的受支持实现或说明限制，不能删掉正确检查来制造通过。

## 示例（需求不同，不照抄复位和延迟）

以下模块仅说明位宽和时序写法。按工程契约选择复位、接口和工具版本，重新运行自己的检查；示例不是当前工程的验证证据。

### 两个无符号8位输入，完整9位和

```systemverilog
module add_with_carry (
    input  logic [7:0] operand_a,
    input  logic [7:0] operand_b,
    output logic [8:0] sum
);
    // 扩展操作数，避免进位宽度依赖隐晦的表达式上下文。
    assign sum = {1'b0, operand_a} + {1'b0, operand_b};
endmodule
```

### 上升沿、同步高有效复位优先于使能

```systemverilog
module enabled_register (
    input  logic       clk,
    input  logic       rst,
    input  logic       enable,
    input  logic [7:0] data_in,
    output logic [7:0] data_out
);
    always_ff @(posedge clk) begin
        if (rst) begin
            data_out <= 8'd0;
        end else if (enable) begin
            data_out <= data_in;
        end
        // 无使能时保留旧状态，不增加额外流水级。
    end
endmodule
```

只改写为`always_ff`不是形式等价证明。用自检查TB验证同步复位、使能优先级、保持和采样周期；验证侧可使用断言、四态比较和看门狗，但要避免在DUT更新的竞争区读取输出。

功能仿真、Lint、综合/时序分别给出实际证据。结构更清晰不能抵消功能回归，未运行的检查不能算通过。
