# 参数化二维脉动阵列矩阵乘法引擎

完整输入错位/移位调度、N×N PE网格、8位无符号乘法与32位累加、完成控制。不是完整TPU/NPU。

## 行为与时序契约

参数N默认4，合法范围3..256。输入元素是**无符号UINT8**，不是有符号INT8或浮点。
计算C[i][j]=sum(A[i][k]*B[k][j], k=0..N-1)，输出无符号32位。
所有矩阵为packed数组；元素[i][j]对应扁平总线的(N*i+j)*元素位宽处，低位是[0][0]。
i_arst异步高有效，清除结果、完成标志与在途操作。i_clk上升沿采样。
i_validInput在空闲时拉高一拍，锁存两输入矩阵，之后输入可任意变化。
若接受输入的上升沿为t，o_validResult在t+(3*N-2)上升沿之后拉高且仅保持一拍；此时o_c有效。
在其他周期不保证o_c保留结果。没有ready/背压接口；调用方在一次接受后至少等3*N+3拍再提交下一组矩阵，禁止重叠请求。
实现完整调度和实际PE子模块网格，不得用常量表/行为桩代替。内部命名不要求与上游相同。

## 编译配置

SystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。

## 顶层接口

```systemverilog
module topSystolicArray
  #(parameter logic [31:0] N = 4)
  ( input  wire logic                      i_clk
  , input  wire logic                      i_arst

  , input  wire logic [N-1:0][N-1:0][7:0]  i_a
  , input  wire logic [N-1:0][N-1:0][7:0]  i_b

  , input  wire logic                      i_validInput

  , output logic [N-1:0][N-1:0][31:0] o_c

  , output logic                      o_validResult
  );

endmodule
```

## 验证边界

N=3/4/8各40组独立整数矩阵乘法scoreboard：零、单位、置换、全255、非对称及固定种子随机矩阵；输入采样隔离、精确完成延迟/单拍脉冲、连续独立事务、异步复位取消在途任务。共120组矩阵、3560个输出元素。

- Only N=3,4,8 exercised; other legal dimensions are not exhaustively verified.
- Unsigned integer matrix engine only; no signed INT8, floating point, quantization, DMA, software stack or full NPU claims.

## 来源与兼容性

https://github.com/tms4517/2D-Systolic-Array-Multiplier/tree/d2eac0638b61c5f8bf4062bc636e774c61a38d8c

Icarus构建副本将var端口改为显式net/output类型，int unsigned改为等宽无符号logic [31:0]；参数诊断置于initial中；两个网格边界连接改为wire+连续赋值，避免packed切片混合驱动限制。不改变算法、时序或原始文件。候选回放仅另删除无效N的诊断。

MIT许可；版权及许可原文保留于sources/tms4517/2D-Systolic-Array-Multiplier/LICENSE，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。
