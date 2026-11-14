# Chisel 硬件生成器

配合 [SKILL.md](../SKILL.md) 和 [rules.md](../rules.md)。Scala编译、Chisel展开、HDL编译和功能验证是不同阶段，前一阶段成功不等于后续通过。

## 工程与当前后端

当前项目只接收清单中的固定构造配置，完整JSON `files`仅含`.scala`。宿主提供JDK17/sbt1.10.7/Scala2.13.12/Chisel6.5.0/firtool1.62.0及可信`RTLFlowMain`；候选不得提供main/App、构建脚本、依赖配置、BlackBox或外部RTL，导入仅限`chisel3`、`scala.collection`、`scala.math`。

展开保留子模块、禁用随机初始化，再执行同一HDL策略、接口/层次和独立TB检查。不支持任意Verilog参数覆写、双向端口或把全部Verilog任务直接迁移为Chisel。构造参数在展开期决定硬件，通常不是运行时配置或Verilog parameter；修改参数必须重新展开验证。

对其他已授权用户工程，先核对公开`build.sbt/build.sc/build.mill`、插件、源码布局、版本、真实展开入口/顶层/参数、输出路径与RTL方言。`chisel3.stage/circt.stage` API随版本变化，不猜通用emit命令；`sbt compile`不是展开，`runMain`及Mill目标必须实际存在。无工程/入口时询问，或仅提供标明未编译的候选；不自动下载、升级或用模板覆盖原工程。**批处理模型没有读取这些工程文件或执行命令的权限。**

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

DUT不含`printf/stop`、测试断言或宿主文件/网络访问；可信入口只能写必要产物/元数据，不读隐藏测试。其他工程的BlackBox/资源/IP须显式授权并进入验证范围，当前候选后端不支持。

## 验证与修复

1. 确认实际版本、构建/展开入口和依赖；缺失为`not_run`，不盲改源码或自动下载。
2. 编译/展开保留真实命令、退出码、顶层/参数及本轮完整文件清单。一个命令可覆盖多阶段，但不虚构执行过的命令；无完整RTL不进入仿真。
3. 核对生成模块/端口/宽度/符号性/时钟复位和延迟，再运行独立HDL验证。每轮独立产物，防止旧RTL混入。修接口时改Chisel，不改TB。
4. 类型/API、插件/依赖、无连接/宽度、firtool问题分别定位；只反馈裁剪的候选诊断。修改后重跑整链，不把整个构建日志、环境或隐藏测试转给模型。

生成器若输出初始化宏、断言或额外文件，须按锁定版本配置处理并核对语义；无法兼容就报告限制，不静默关策略、删断言或文本修补生成RTL。功能通过要求全部必需阶段通过；只有编译/展开证据时功能为`not_run`。Scala格式检查与RTL Lint分别报告，未运行不算通过。

评分`static-chisel-heuristic-v1`直接评价Scala源码，不用生成RTL分数替代；不是语义证明或跨语言指标。两组按相同预算重构，仅重新展开、独立验证通过且源码分数严格提高才接受，否则源码与对应RTL成对回退；无分数则跳过。

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

交互式交付源码、已授权构建变更、命令/版本/参数、RTL清单/哈希、阶段证据与限制；批处理只交源码JSON。Scala构建、插件和展开代码会执行宿主程序，过滤与超时不是沙箱；不可信工程需无密钥、无网络、非特权及资源隔离，下载/安装需授权。
