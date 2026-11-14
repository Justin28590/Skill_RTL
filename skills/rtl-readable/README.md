# rtl-readable：直接用于硬件工程的 Skill

把整个`rtl-readable/`目录交给支持`SKILL.md`的编码助手，就可以从需求设计硬件，或在已有工程中生成、审查、验证、修复和重构Verilog、SystemVerilog、Chisel。**不需要本仓库的数据集、模型API配置、评分器或运行脚本。**

Skill是给助手的工作指导，不是独立可执行程序。文件读写和命令执行由宿主助手提供；仿真、综合或Chisel展开需要用户工程对应的工具链。没有工具时只能交付源码/建议，不能声称已验证。

## 安装与加载

完整复制以下文件，保留相对路径；不要只复制入口文件：

```text
rtl-readable/
  SKILL.md
  rules.md
  README.md
  references/
    verilog.md
    systemverilog.md
    chisel.md
```

放入宿主支持的Skill目录，例如支持Agent Skills的项目目录`.agents/skills/rtl-readable/`。已有安装先备份、比较再更新，不覆盖未知内容。

以Pi个人安装为例，在本仓库根目录执行；目标已存在时下面的复制不会执行：

```bash
mkdir -p ~/.pi/agent/skills
test ! -e ~/.pi/agent/skills/rtl-readable && cp -R skills/rtl-readable ~/.pi/agent/skills/
```

在Pi中重启会话或执行`/reload`，然后用`/skill:rtl-readable`加任务描述。其他助手按其Skill加载机制调用；也可以明确要求助手读取`rtl-readable/SKILL.md`及其语言参考。

## 直接使用的请求示例

### 从高层需求开始

```text
/skill:rtl-readable 设计一个8位数据、深度16的同步FIFO，要求保持顺序，
支持连续入出和输出背压。目标SystemVerilog。
先给出接口、复位、满空和同拍入出规则，以及延迟/吞吐说明，等我确认再写代码。
```

希望一次完成时明确授权设计选择：

```text
/skill:rtl-readable 用Verilog实现一个可配置时钟分频器。
请自行提出并记录合理的接口、复位和分频范围，校验契约后完成源码及自检查TB。
在当前工程中创建必要文件；允许使用已有仿真工具，不要联网或安装依赖。
```

### 修复已有工程

```text
/skill:rtl-readable 检查rtl/stream_fifo.sv和tb/下的测试。
输出背压时数据会变化，请复现并修复，保持现有接口和正常传输延迟，
运行相关回归，不要修改正确的测试期望。
```

### 只审查或保行为重构

```text
/skill:rtl-readable 只审查rtl/arbiter.sv，重点看仲裁公平性、包级锁定和复位。
给出带位置的发现及验证建议，不修改文件。
```

```text
/skill:rtl-readable 重构现有Chisel队列以改善职责划分和命名。
保留构造参数、生成端口和逐周期行为，使用工程已有构建/展开入口，
重跑现有测试；不要升级依赖或手改生成RTL。
```

## 默认行为与交付

- 新设计先形成设计说明与接口/时序契约，校验并确认后实现。已有确认契约直接沿用。
- 按任务授权读写工程文件、编写TB并执行已有工具；审查请求默认只读。
- 测试依据需求、标准和独立参考判据，不从DUT输出反推答案。旧TB与新契约冲突时先说明并确认迁移。
- 用户未指定时最多3轮修改/复测；无新证据、缺工具或契约不明确时停止猜测并报告阻塞。
- 默认交付工程文件和简洁结果说明，不强制JSON；检查结果区分通过、失败和未执行。
- 不依赖风格评分；保行为重构必须有回归证据。有限测试不能代替形式证明、物理CDC或PPA验证。

助手会先读取[工作流程](SKILL.md)、[编码规则](rules.md)和相应[Verilog](references/verilog.md)、[SystemVerilog](references/systemverilog.md)或[Chisel](references/chisel.md)参考。所有运行所需文档都在本目录内。
