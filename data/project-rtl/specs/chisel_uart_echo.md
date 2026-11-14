# Chisel UART 接收/缓冲/回送项目

包uart，类Echo(frequency: Int, baudRate: Int)，固定构造Echo(800,100)。生成顶层Echo，clock及同步高有效reset，io_rxd/io_txd各1位。接收8位LSB先行串口，经单字节缓冲回送，TX采用1起始、8数据、2停止位，每位8个系统周期。RX有两级同步；不得直接组合连通RX/TX。调用方为有限缓冲留足间隔。基线16个独立字节及停止位检查；不是通用高吞吐UART性能测试。

## 编译配置

原生语言：chisel。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。
固定Scala 2.13.12、Chisel 6.5.0；可信构造配置：`[{"module": "Echo", "class": "uart.Echo", "args": [800, 100]}]`。不要提供App/main、构建脚本或外部RTL。

## 顶层接口

```systemverilog
module Echo(
  input clock,
  input reset,
  output io_txd,
  input io_rxd
);
endmodule
```

## 项目公开文档

来源：https://github.com/schoeberl/chisel-examples/tree/4440f6ca77f6b64ed903bd1892f7870c42896e11

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

许可：BSD-2-Clause，保留原始版权及许可，见数据集LICENSES.md和锁定源码中的LICENSE/COPYING。
