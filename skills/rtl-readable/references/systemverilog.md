# SystemVerilog RTL

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)；目标是可综合DUT，不是SystemVerilog验证平台。

## 方言与编码要点

- 新文件用`.sv/.svh`，允许已有兼容`.v/.vh`。工程参数可能为`.v`启用SV，扩展名不能覆盖已确认的目标语言。Icarus `-g2012`并非完整SV实现，解析失败也可能是工具限制。
- 当前完整JSON项目按路径排序编译，include仅用项目根目录相对字面量。无外部package搜索、interface/modport、DPI、层次引用或完整SVA支持；结构体成员点号也可能被保守策略拒绝，优先明确打包信号，不关闭策略绕过限制。
- `logic`是四态数据类型，不代表寄存器也不解决多驱动；解析网络显式用net。不得用二态`bit`掩盖X/Z，也不把`===`等测试比较惯用法直接当综合数据通路写法。
- `logic [7:0] data`和`logic data [7:0]`不是同一接口，保留packed/unpacked维度和符号性。`int`默认有符号、32位，谨防意外扩大硬件；检查无尺寸常量、转换、拼接和移位的中间宽度。
- `always_comb`用阻塞赋值与完整默认值，不自动补齐漏赋值；避免隐晦先读后写、时钟/延时或副作用任务。简单组合式可用`assign`。
- `always_ff`用非阻塞赋值，状态不能由其他过程写入。同步复位在采样沿内判断；异步低有效复位才用`@(posedge clk or negedge rst_n)`并检查`!rst_n`。不能为过测互换，也不为风格引入`always_latch`。
- FSM可用显式宽度的`typedef enum logic`，保留复位状态、外部可观察编码与非法状态恢复。`unique/priority`影响诊断/综合假设，不能替代完整分支或把非法输入变成don't-care。
- struct、数组、function、generate只在工具支持且确实简化实现时使用。class、随机约束、UVM、动态容器、DPI、测试时钟块不放入DUT；不加入/删除断言改变测试判据。

候选宏不能影响可信TB，语言域隔离由控制器负责。扩展名改成`.sv`不能绕过HDL系统函数/宿主I/O策略，也不能以工具不支持为由修改TB或链接参考RTL。

## 示例（需求不同，不照抄复位和延迟）

两个独立模块仅说明写法，不承诺所有工具版本均支持。[tests/test_skill.py](../../../tests/test_skill.py)以Icarus/vvp检查加法65,536组二值输入及寄存器256个采样值、同步复位/优先级/使能保持；缺工具明确skip，不将示例结果当新候选证据。

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

只改写为`always_ff`不是形式等价证明。功能须经完整候选策略、接口/层次及独立仿真检查。

评分方法`static-sv-heuristic-v1`识别`logic/bit/int`声明，但不完整解析enum/struct/数组；不作跨语言比较。Lint不支持/未运行不能算零违规，重构只在功能通过且分数严格提高时接受。
