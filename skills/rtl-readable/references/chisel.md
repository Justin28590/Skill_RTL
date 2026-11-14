# Chisel 硬件生成器

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)。Scala编译、Chisel展开、HDL编译和功能验证是不同阶段，前一阶段成功不等于后续通过。

## 工程准备

先读取已授权工程的`build.sbt/build.sc/build.mill`、插件配置和相关源码，确认Scala/Chisel/firtool版本、源码布局、实际展开入口、顶层、构造参数、输出路径与RTL方言。复用工程当前配置，不把版本升级混入普通修复。

`chisel3.stage/circt.stage` API随版本变化；`sbt compile`不是展开，`runMain`及Mill目标必须实际存在，不猜通用emit命令。没有构建入口时询问用户，或经授权提供最小可复现工程；不能自动下载、升级或用模板覆盖原工程。

构造参数在展开期决定硬件，通常不是运行时配置或可覆写的Verilog parameter。每组参数都要重新展开并核对实际接口。双向端口、外部IP、初始化和生成断言需确认所用版本及后端能力，不能假设改语言后自动兼容。

## 硬件语义要点

| 主题 | 要点 |
| --- | --- |
| Scala与硬件 | `val/var`不是寄存器；Scala `if/for`和集合操作为展开期逻辑。运行期条件用`when/elsewhen/otherwise`、`Mux`或`switch/is`。`:=`是连接，`=`是Scala赋值，`<=`不是寄存器更新。 |
| 类型与宽度 | 区分`UInt/SInt/Bool/Clock`及复位类型，公开边界显式`.W`，字面量按需`.U/.S`。完整加法进位用`+&`；普通`+`/`+%`不保留额外位，更宽输出不能挽回已丢进位。 |
| 转换与边界 | `.asUInt/.asSInt`是位解释，不自动按数学意图扩展。明确截断/符号扩展；检查乘法、移位、拼接、索引、`log2Ceil`、宽度1及非二次幂深度。 |
| 组合连接 | `Wire/WireDefault/Mux`完整定义输出；`switch/is`在外部给默认值，不用`DontCare`补洞。默认连接和条件覆盖可合法表达优先级，不能机械套用HDL多驱动规则，但须避免意外覆盖。 |
| 状态 | `Reg`无复位初始化，`RegInit`遵循所在时钟/复位作用域；读取寄存器得到当前状态。`RegNext/RegEnable`可能改变延迟/保持，只在契约需要时使用。 |
| 复位 | `Bool`为同步、`AsyncReset`为异步，抽象`Reset`须结合连接/展开确认。低有效需显式转换极性，改名`rst_n`不改变语义；保留复位与使能优先级。 |
| 接口 | `Module`带隐式clock/reset，精确接口或纯组合可用`RawModule`和独立IO；时序用明确的时钟/复位作用域。核对Bundle/Vec方向、顺序/打包、`io_`前缀、去重后缀及实际端口。`desiredName`只是命名意图，仍查生成结果。 |
| 握手 | `Decoupled`不自动实现队列或背压保持；明确传输条件、稳定性和状态更新，不额外增加握手。 |
| 风格 | 遵循工程`.scalafmt.conf`，通常类/Bundle为`UpperCamelCase`、内部值为`lowerCamelCase`；公开命名优先。表达清楚状态、组合式和更新优先级，不把生成RTL当手工重构目标。 |

不要把调试打印、测试激励或宿主文件/网络操作当作硬件功能。工程需要的断言、BlackBox、资源文件和外部IP应显式声明，并确认仿真与综合处理方式；生成器和构建入口只访问已授权资源。

## 验证与修复

1. 确认实际版本、构建/展开入口和依赖；缺失为`not_run`，不盲改源码或自动下载。
2. 编译/展开保留真实命令、退出码、顶层/参数及本轮完整文件清单。一个命令可覆盖多阶段，但不虚构执行过的命令；无完整RTL不进入仿真。
3. 核对生成模块/端口/宽度/符号性/时钟复位和延迟，再运行工程测试或依据契约建立的HDL验证。每轮用本次展开产物，防止旧RTL混入。实现偏离契约时改Chisel，不改正确的TB判据。
4. 类型/API、插件/依赖、无连接/宽度、firtool问题分别定位；读取相关诊断，分享日志前去除密钥和无关环境信息。修改后重跑受影响的完整链路。

生成器若输出初始化宏、断言或额外文件，按实际版本和工具配置处理并核对语义；不静默删除断言或文本修补生成RTL。只有编译/展开证据时，功能仿真仍是未运行。Scala格式检查与RTL Lint分别报告。

可维护性审查针对Scala源码，实际硬件行为依据展开后的RTL验证。重构后重新展开并运行回归；出现功能退化时回退自己的修改及对应生成产物，不能只保留旧RTL来掩盖新源码的问题。

## 示例（仅说明写法，未承诺编译/仿真验收）

以下不是数据集案例，使用前确认版本/API。为对应公开RTL端口，示例保留下划线名称。

### 组合加法，无隐式时钟/复位

```scala
import chisel3._

class AddWithCarry extends RawModule {
  override def desiredName: String = "add_with_carry"

  val operand_a = IO(Input(UInt(8.W)))
  val operand_b = IO(Input(UInt(8.W)))
  val sum = IO(Output(UInt(9.W)))

  // +& 保留额外进位；输出宽度与公开接口一致。
  sum := operand_a +& operand_b
}
```

核对生成顶层`add_with_carry`仅有两个8位输入和一个9位输出，没有clock/reset或`io_`前缀。

### 上升沿、同步高有效复位、低使能保持

```scala
import chisel3._

class EnabledRegister extends RawModule {
  override def desiredName: String = "enabled_register"

  val clk = IO(Input(Clock()))
  val rst = IO(Input(Bool()))
  val enable = IO(Input(Bool()))
  val data_in = IO(Input(UInt(8.W)))
  val data_out = IO(Output(UInt(8.W)))

  // Bool 复位明确为同步；RegInit 的复位优先于普通更新。
  withClockAndReset(clk, rst) {
    val dataReg = RegInit(0.U(8.W))
    when(enable) {
      dataReg := data_in
    }
    data_out := dataReg
  }
}
```

这不是异步/低有效复位模板；修改作用域/类型后重新验证，不为便于连接多加一拍。

交付源码、必要且已授权的构建变更、实际命令/版本/参数、生成RTL路径、验证证据与限制。Scala构建、插件和展开代码会执行宿主程序；执行不可信工程需要隔离，下载/安装需授权，超时不能代替安全沙箱。
