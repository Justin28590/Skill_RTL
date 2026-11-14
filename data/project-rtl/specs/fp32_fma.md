# IEEE binary32 融合乘加与舍入/异常处理核

完整FMA：操作数解码、乘加/对齐、消去后的规格化、单次舍入和IEEE异常标志；组合核，无时钟。

## 行为与时序契约

公开顶层为mulAddRecFN；expWidth为指数位数、sigWidth为含隐藏位的有效位数；本任务默认参数8/24，即binary32。上游3/3占位默认在Icarus独立展开时有非法part-select，参考TB显式覆写为8/24，交付顶层默认也应为8/24。
输入/输出采用HardFloat recFN，不是直接32位IEEE编码。E=expWidth、P=sigWidth；总宽E+P+1，最高位为符号，随后E+1位指数r和P-1位小数f。
对于IEEE正常数，r=IEEE指数+2^(E-1)+1，f不变；对于非零次正规数，把原小数左移n位使隐藏位到bit(P-1)，r=2^(E-1)+2-n，f取移位后低P-1位。
r的最高3位为000表示零、110为无穷、111为NaN；特殊值不用位字段不要求特定值。NaN小数最高位1为quiet、0为signaling，输入只允许合法recFN编码。
结果按(-1)^op[1]*(a*b)+(-1)^op[0]*c计算：00加、01减c、10负乘积加c、11负乘积减c。
**融合**乘加只在最终结果舍入，禁止先把乘积舍入到binary32再相加。
roundingMode：0最近偶数、1向零、2向负无穷、3向正无穷、4最近且中点远离零、6 round-to-odd（非精确结果最低有效位置1），5/7不属于合法配置。
control=0在舍入前检测tininess，1在舍入后检测；基线为1。舍入后tininess依据目标精度、无限指数范围下的舍入结果，不简单等同于最终编码为次正规数。
exceptionFlags[4:0]={invalid,infinite/divide-by-zero,overflow,underflow,inexact}；本核不执行除法，bit3为0。
支持±0、正常数、次正规数、无穷、quiet/signaling NaN。无效包括sNaN、0×无穷和相反符号无穷相加；使用RISC-V特化的正号默认quiet NaN，binary32解码后为0x7fc00000，不传播payload。
精确抵消为零时，向负无穷舍入产生-0，其他模式为+0；同号零相加保留符号。无时钟/复位/ready，输入稳定后组合结果有效。
必须交付真正的乘加/规格化/舍入子模块及本地头文件，不允许调用软件浮点或嵌入测试向量答案。保留公开参数；基线只验证binary32配置。

## 编译配置

SystemVerilog-2012仿真。必须交付所有依赖，不链接参考RTL；每个顶层必须实际展开子模块。

## 顶层接口

```systemverilog
module mulAddRecFN #(parameter expWidth=8, parameter sigWidth=24)(
  input [0:0] control, input [1:0] op,
  input [expWidth+sigWidth:0] a, b, c,
  input [2:0] roundingMode,
  output [expWidth+sigWidth:0] out, output [4:0] exceptionFlags
);
endmodule
```

## 验证边界

3432组：15组定向+128组固定种子随机三元组，分别遍历4种op和6种舍入；独立Python Fraction整数/有理数oracle核对binary32结果和5位异常，含融合消去、tie、次正规、上下溢、符号零及NaN/Inf。

- Only expWidth=8/sigWidth=24 and tininess-after are tested; no exhaustive IEEE certification or other precision claims.
- Combinational arithmetic block only, not a pipelined vector FPU or full tensor processor.

## 来源与兼容性

https://github.com/bsg-external/HardFloat/tree/bf579553c927092650f5976d8da573af1ac64741

参考原版直接编译，使用锁定的RISC-V特化头。候选回放将三个.vi头及include名称映射为.vh；countLeadingZeros内部generate层次连线等价改写为父作用域wire数组。顶层默认特化为本任务的8/24以支持独立编译；参考配置本身也是8/24。不改变算术，也不放宽候选后缀或跨层引用安全策略。选择未引入外部BSG依赖的Release 1固定导入版本，不声称是最新上游。

BSD-3-Clause许可；版权及许可原文保留于sources/bsg-external/HardFloat/COPYING.txt，见数据集LICENSES.md。不提供参考实现或隐藏测试正文。
