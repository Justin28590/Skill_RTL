# Chisel 分级双缓冲流 FIFO 项目

包fifo，类DoubleBufferFifo[T <: Data](gen: T, depth: Int)，固定UInt(8.W)、depth=8。顶层DoubleBufferFifo，clock及同步高有效reset；io_enq/io_deq均ready/valid/bits接口，bits宽8。四级双缓冲，容量8，支持每周期一字，保持FIFO顺序，阻塞输出保持valid及数据；复位清空。不要求内部类名相同，但保留实际子模块层次。基线填满、1000周期背压、排空与复位；不验证其他宽度/深度。

## 编译配置

原生语言：chisel。RTL验证方言2012。每个顶层必须包含实际子模块。内部命名不要求与原件一致。
固定Scala 2.13.12、Chisel 6.5.0；可信构造配置：`[{"module": "DoubleBufferFifo", "class": "fifo.DoubleBufferFifo", "args": [{"uint_width": 8}, 8]}]`。不要提供App/main、构建脚本或外部RTL。

## 顶层接口

```systemverilog
module DoubleBufferFifo(
  input clock,
  input reset,
  output io_enq_ready,
  input io_enq_valid,
  input [7:0] io_enq_bits,
  input io_deq_ready,
  output io_deq_valid,
  output [7:0] io_deq_bits
);
endmodule
```

## 项目公开文档

来源：https://github.com/schoeberl/chisel-examples/tree/4440f6ca77f6b64ed903bd1892f7870c42896e11

参照本契约实现公开行为；参考源码与隐藏测试不提供给生成器。

许可：BSD-2-Clause，保留原始版权及许可，见数据集LICENSES.md和锁定源码中的LICENSE/COPYING。
