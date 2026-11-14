# SystemVerilog UART 调试记录打印项目

anrst异步低有效。empty=0时读取一条记录；r_rnw为1输出R否则W，地址与数据各32位高半字优先，格式为R/W、空格、四位大写十六进制、下划线、四位十六进制、空格、同格式数据、CR，共22字符。输入记录保持到r_req脉冲，之后可更新下一条。8N1串口。原件自行定义SIMULATION，仿真位周期固定10系统周期；综合时使用CLK_HZ/BAUD。基线验证两条完整记录及确认脉冲；不验证中途复位时内置TX行为。

## 编译配置

原生语言：systemverilog。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。

## 顶层接口

```systemverilog
module uart_debug_printer #( parameter
  CLK_HZ = 100_000_000,
  BAUD = 115200
)(
  input clk,    // clock 100MHz
  input anrst,  // async reset

  // fifo output
  input empty,                // data valid flag
  output logic r_req = 1'b0,  // data request acknowledge
  input r_rnw,                // read/nwrite bit
  input [31:0] r_addr,        // first 32 bit word
  input [31:0] r_data,        // second 32 bit word

  // UART TX
  output uart_txd             // UART tx pin
);
endmodule
```

## 项目公开文档

来源：https://github.com/pConst/basic_verilog/tree/2654273b2c4e556a98e806f3a19b52c9b3c74614

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

接口摘录作者 Konstantin Pavlov；原件及本派生接口摘录依 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。构建副本显式补齐parameter关键字；SPI将edge_detect复位端口旧名nrst映射为anrst，不改变顶层端口或数据通路。
