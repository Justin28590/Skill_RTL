# RTL Skill 优化与评估

本项目的核心目标是**迭代优化可复用的 RTL 编码 Skill，使模型在保持接口、功能与逐周期行为正确的前提下，生成更清晰、可维护的完整 RTL 项目**。主要交付是经过对照实验验证的 Skill、规则与示例，以及效果、成本和失败分析；不是单纯生成更多 RTL 案例。

本仓库评测主流程：**高层需求 → 模型设计说明与接口/时序契约 → 独立审查并冻结 → 独立验证环境准备与冻结 → RTL生成 → 独立仿真与限轮修复/回退**。不保留旧固定契约生成入口。全部32个案例使用同一流程，详见[设计流程与信任边界](docs/设计流程.md)。

支持 **Verilog / SystemVerilog / Chisel**，默认模型 **GLM-5.3 / high**，Python 3.10+ 标准库实现。[高层需求清单](data/requirements.json)覆盖全部32个案例，可选目标分别为 **27 / 30 / 2**，翻译不重复计数。[原开源IP材料](data/project-rtl/README.md)仅用于来源和历史工具回归，不再作为固定接口/TB输入。数据仍为 pilot，未冻结 dev/test。独立验证使用同一模型的隔离上下文、负控和审查，不是可信数学证明；所有案例接入不代表已通过真实模型实测。

## 直接在你的工程中使用 Skill

将整个 [`skills/rtl-readable/`](skills/rtl-readable/README.md) 目录安装到编码助手的Skill目录，即可用于自己的工程；不需要`run.py`、本数据集、GLM配置或评分器。入口 [`SKILL.md`](skills/rtl-readable/SKILL.md) 面向实际设计、文件修改、TB和工具验证，不强制JSON交付。

例如在Pi中安装后调用：

```text
/skill:rtl-readable 设计一个8位、深度16、支持输出背压的同步FIFO。
目标SystemVerilog，先给出设计说明与接口/时序契约，确认后实现并验证。
```

安装路径、已有工程修复和只读审查示例见[Skill使用说明](skills/rtl-readable/README.md)。下文是维护者的**评测/优化流程**，不是普通用户使用Skill的前置条件。评测的JSON协议、受限工具、评分及调用预算由运行器单独施加，见[适配边界](docs/评估规则.md#可复用skill与评测适配边界)。

## 核心工作流：如何优化 Skill

**开发任务对照 → 归纳共性问题 → 修改 Skill → 同条件复测 → 保留或回退 → 冻结后独立评估。**

这里有两层不同的循环：

- **内层：自动优化一次生成的 RTL。** `run.py` 已实现编译/仿真、反馈、限轮修复、可读性重构和整项目回退；不会修改 Skill 文件。
- **外层：优化 Skill 本身。** 目前由维护者分析结果、修改规则/示例、重跑对照并决定版本取舍；尚无自动 Skill 搜索、自动改写或版本择优器。下述步骤是现有工具支持的人工迭代方法，不是已完成的优化成绩。

### 1. 明确优化对象与不变量

| 文件 | 适合优化的内容 |
| --- | --- |
| [`skills/rtl-readable/SKILL.md`](skills/rtl-readable/SKILL.md) | 工作步骤、契约检查顺序、自检清单、规则优先级；消除重复、歧义和冲突 |
| [`skills/rtl-readable/rules.md`](skills/rtl-readable/rules.md) | 跨任务可复用的编码规则，把笼统要求改成可执行检查 |
| [`skills/rtl-readable/references/verilog.md`](skills/rtl-readable/references/verilog.md) | Verilog 语义陷阱、正确/错误写法与最小示例 |
| [`skills/rtl-readable/references/systemverilog.md`](skills/rtl-readable/references/systemverilog.md) | SystemVerilog 可用子集、类型与过程块规则、示例 |
| [`skills/rtl-readable/references/chisel.md`](skills/rtl-readable/references/chisel.md) | Chisel 宽度、连接、展开与生成接口规则、示例 |

本仓库评测中，Skill组的设计、契约修订、独立审查、TB准备/修订/审查、RTL生成/修复/重构均独立加载Skill。每次调用只允许读取`SKILL.md`、`rules.md`的通用及所需语言分支、对应语言参考三份文档（TB阶段使用SystemVerilog，其余使用DUT目标语言）；**另建示例文件不会自动被加载**。当前 CLI 固定读取上述目录，没有 `--skill-dir` 或 Skill 版本选择参数。用 Git 提交或完整快照区分版本；一次运行期间不要修改 Skill，避免不同轮次读取不同版本。

单次实验只改变一个主要因素。固定模型、采样、需求、设计/审查/验证协议、评分及各阶段预算；每次运行的模型设计与TB可能不同，须记录冻结哈希并报告这种额外波动，不声称是同契约同TB的严格配对。不要通过改TB、放宽接口检查或提高预算制造Skill提升；新旧流程应分开统计。

### 2. 先保存旧版 Skill 的对照结果

先按[运行与验证](docs/运行与验证.md)准备环境，并设置 API Key。以下命令**消耗 API 额度**，仅用两个项目演示一次小规模 pilot；它们不是已冻结的开发集或测试集：

```bash
# 当前 Skill 记为 v0；记录 Git 提交、未提交改动和实验配置。
python3 run.py --language verilog \
  --task fp32_fma axis_packet_switch --output results/skill-v0-pilot-r1
```

不要只比较“有 Skill / 无 Skill”：这只能评估当前 Skill 的作用；**优化是否有效还需要比较旧版 Skill / 新版 Skill**。先预定任务、重复次数、费用上限和接受标准，再看结果，不能只保留成功任务。正式开发/测试需按来源、共享依赖和算法族隔离；当前加载器与报告仍限定 `pilot`，没有 `--split` 入口，正式划分与评估支持尚待完成。

### 3. 从失败证据提出一条可检验的改进假设

先看 `summary.csv` / `summary.json` 定位任务，再看对应 `report.json` 的 `design.attempts`、`verification_preparation.attempts` 和 RTL `attempts`：

- **加载问题**：先看 `skill_by_phase`、`skill_required_calls` / `skill_loaded_calls`，再核对各轮 `generation_metadata.skill_loaded`、`skill_documents` 和 `agent_trace_path`；文档未成功加载，不能当作规则已经生效。顶层 `skill_loaded` 表示至少一轮完整加载，不表示完整流程执行成功。
- **功能问题**：区分交付格式、候选编译/展开、接口/层次、功能仿真失败；结合公开契约、候选源码与允许反馈判断，不从隐藏测试提取答案。
- **可读性问题**：查看 `attempts[].readability.dimensions` / `issues`，人工检查命名、职责划分、复杂度和注释是否真的改善；不要只追总分。
- **成本问题**：检查冗长、重复或冲突规则是否增加工具轮次、token 与耗时；Skill 越长不等于越好。

例如，开发任务反复出现背压期间数据变化，而已有“背压保持”规则过于抽象：可将其改为明确的传输条件、保持条件及数据/边带自检，并在目标语言参考中加入与具体任务无关的最小示例。预期是这类功能错误减少，且其他任务的正确性不退化；这是待验证假设，不能先写成提升结论。

每轮记录：**版本/文档哈希、任务与配置、问题证据、改进假设、修改位置、预期收益、回归风险**。规则必须可跨任务复用，禁止写入任务答案、参考实现、隐藏 TB 或测试期望值；若借助模型改写 Skill，只提供脱敏问题摘要、公开契约和必要候选片段，不整体上传原始日志或 `results/`。

### 4. 修改后复测，并做针对性消融

只改 Skill 时先检查链接、加载协议及已有示例，不必每轮跑全部工程回归。新增或修改示例应补充相应的编译/仿真测试；修改评分器、验证器或数据时再跑对应测试，正式冻结前跑全量回归，见[测试说明](tests/README.md)。这些检查不替代真实模型的效果对照：

```bash
python3 -m unittest discover -s tests -p 'test_skill*.py' -v  # Skill 加载与示例检查

# 当前 Skill 记为 v1；与 v0 使用相同任务、配置和预算。
python3 run.py --language verilog \
  --task fp32_fma axis_packet_switch --output results/skill-v1-pilot-r1
```

按预先约定重复实验，输出使用新的 `r2`、`r3` 等目录，并记录波动。跨版本重点比较 v0/Skill 与 v1/Skill，同时查看各自 Baseline；不能把随机采样波动直接归因于规则修改。若同时改了流程、规则和示例，应分别撤去某项改动重跑，确认收益来自哪里。其他语言按同样方法独立评估，不作跨语言分数排名。

### 5. 按功能、可读性和成本决定保留或回退

| 判断面 | 证据与比较方式 |
| --- | --- |
| 功能 | 比较 `initial_functional_status`、`functional_status` 与 `repair_success`；同时看首次和最终通过，避免额外修复掩盖首次生成退化 |
| 可读性 | 比较初始轮及最终选中轮分数；报告全部样本、功能通过样本及双方都通过的同题配对结果，注明缺失值，配合隐藏版本/组别的人工评价 |
| 成本 | 比较 `provider_calls`、`model_calls`、`tool_calls`、`elapsed_seconds`，从 `attempts[].usage` 汇总 token；未返回的用量记为未知，不记为零 |
| 可追溯性 | 保存配置、数据/工具/代码版本、Skill 快照、各轮读取哈希与结果路径；`skill_version=tool-v1` 是加载协议，不是 Skill 内容版本 |

**不能以牺牲功能换可读性分数，也不能把单次涨分或通过离线回归当成优化成功。** 按事先约定的标准和多次运行证据保留有收益的修改；出现功能回归先定位或回退，收益不明确时标为待验证。Skill 版本的保留/回退目前是人工操作，与流水线自动回退 RTL 快照不同。

开发迭代结束后冻结 Skill、数据、配置和评分器，再在未参与规则修改的任务上独立评估；不能根据测试结果继续调 Skill 后仍称其为独立测试。每轮结论至少包含“改了什么、相比 v0 和 Baseline 的变化、成本、失败样本、接受/回退理由”。正式实验与人工盲评要求见[实验口径](docs/评估规则.md#实验口径)。

## 单次生成与评估（消耗 API 额度）

```bash
read -rsp 'GLM API Key: ' GLM_API_KEY; echo
export GLM_API_KEY

# 完整脉动阵列案例，运行 Baseline/Skill 两组
python3 run.py --task systolic_matmul

# 按需缩小范围
python3 run.py --language verilog --task fp32_fma --group Baseline --output results/fma-baseline
python3 run.py --language verilog --task axis_packet_switch --group Skill --output results/switch-skill
python3 run.py --task systolic_matmul --group Skill --output results/matmul-skill
python3 run.py --task chisel_double_buffer_fifo --group Skill --output results/fifo-skill

# 同一任务的两组独立对照；限定 Verilog，避免同时运行 SystemVerilog 翻译
python3 run.py --language verilog --task aes --output results/aes-comparison
```

**默认运行全部任务、Baseline/Skill 两组，以及各任务在清单中已支持的全部目标语言；不是每个任务都运行三种语言。** 可选语言由 [`requirements.json`](data/requirements.json) 中每个任务的 `target_languages` 决定。

例如，`aes` 支持 Verilog/SystemVerilog，省略语言则分别运行两种。这是当前目标语言范围，不是算法只能用这些语言实现。

`python3 run.py` 会遍历全部支持的任务/目标语言组合；同一项目的多个目标语言不重复计为独立项目。全量运行消耗更多额度，且需要 HDL 和 Chisel 工具链；可先执行 `python3 run.py --check-data` 查看零调用运行计划。

筛选只保留 `--task`、`--group`、`--language`，均支持一个或多个值，也可重复传入；例如 `--task aes cmac --language verilog systemverilog --group Skill`。移除冗余的 `--groups` / `--all-groups`。选择仅由这些 CLI 参数决定，不指定时不会被配置中的旧 `group` / `language` 字段缩小；`--config` 仍用于模型和预算等设置。仅运行清单支持的任务/目标语言组合；未知 ID 或指定任务不支持任何所选语言会在调用模型前报错。执行前显示整个运行计划的预算。

配置在 [`configs/glm.json`](configs/glm.json)，默认 `max_design_repairs=1`、`max_verification_repairs=1`、`max_repairs=2`、`max_refactors=1`、阈值95、`max_agent_turns=6`；默认不发送`max_tokens`（也可配置为`null`），不再隐式回退到8192。省略表示使用服务端默认值，不是无限输出，默认值也可能低于32768；需要更大额度时应按实际端点支持范围显式设置正整数。每组每任务最多12次阶段调用；默认Baseline最多12次HTTP，Skill全部阶段各最多6个工具轮次，最多72次HTTP，两组合计84次。设计、契约审查、验证准备与验证审查也计费；`--check-data` 显示完整预算。API 默认流式接收（`api_stream=true`），超时 `api_timeout_seconds=600`，支持正文与 Skill 工具参数分段组装；不导出私有推理。兼容端点可显式设 `api_stream=false`。超时/断流不接受部分源码、不自动重试，也不占用 RTL 修复预算；详见[请求诊断](docs/运行与验证.md#模型请求与失败诊断)。Skill组在全部模型阶段加载Skill，Baseline全程不加载；两组模型、需求、阶段协议和修订上限相同，但各自生成并冻结的设计/TB可能不同，源码和对话互不共享。独立审查指独立上下文，不是不同模型或Skill；共享指导可能带来共同偏差。Skill读取增加的HTTP/token/耗时单独记录，不宣称总成本相同。旧的仅RTL阶段加载实验须与全流程加载实验分开统计。

## 产物与验证约定

设计与验证准备使用各自JSON协议，见[设计流程](docs/设计流程.md)。RTL模型每轮交付完整快照，而非补丁：

```json
{"files":[{"path":"rtl/top.v","content":"<完整顶层源码>"},{"path":"rtl/core.v","content":"<完整子模块源码>"}]}
```

- 最多128个文件、源码总计2 MB；限定项目内路径与语言后缀，拒绝外部 include、宿主 I/O、仿真系统任务和参考源码回填。
- 独立上下文先根据需求与冻结契约构造TB，经源码检查、恒零/恒一负控及独立审查后冻结。候选独立预处理/编译，再与该TB链接，核对契约接口、实际子模块层次和功能日志；不使用旧固定端口或延迟。
- 只向修复模型提供候选编译诊断和粗粒度失败原因，不发送隐藏 TB、期望值或原始仿真日志。
- 功能通过且低分时才重构；新项目功能通过且分数严格提高才接受，否则回退整个项目。
- Chisel使用模型设计并冻结的构造配置；候选不能自带构建脚本或外部RTL。可读性评分针对Scala源码，不是展开后的RTL。
- 设计/验证环境不能冻结或冻结文件改变时，功能记为`not_run`，不误判为RTL失败，也不进入RTL修复。

完整协议、评分及信任边界见[评估规则](docs/评估规则.md)。**超时和源码过滤不是安全沙箱**；不可信 HDL/Scala 应在无密钥、无网络、非特权且有限资源的环境执行。项目级可选 Lint 尚未接入，报告为 `not_run`。

## 输出

```text
results/<run>/
  config.json, summary.json, summary.csv
  [<语言>/][<组>/]<项目>/      # 多语言增加语言层；多组增加组层
    report.json                # schema 6，分阶段加载/状态、全部成本、冻结哈希
    design/                    # 设计提案、审查、冻结契约
    verification/              # 独立TB、负控、审查、冻结测试
    final.project.json, final/ # 被保留的完整快照
    final-rtl/                 # 仅 Chisel：选中轮次展开的 RTL
    attempt_00_initial/        # prompt、response、source、checks
    attempt_01_repair/ ...
```

单语言保持原目录结构；多语言分别写入 `verilog/`、`systemverilog/`、`chisel/`，根目录汇总计数与 CSV，`summary.json.by_language` 保留各语言结果，不跨语言排名。`--check-data` 的多语言 `total` 是任务/目标语言组合数，`task_count` 是独立任务数，`task_group_runs` 才是预计交付数。

`final/` 存在不代表功能通过；检查 `functional_status`、`initial_functional_status`、`stop_reason` 和 `selected_attempt`。修复返回无效 JSON 时继续在剩余预算内修复；预算耗尽仍保留上一份完整快照，不会用无效响应覆盖它。`generation_failures` / `generation_error_counts` 单列失败的生成轮次（包括后来修复成功的轮次）；`last_error_code` / `last_error` 提供原因，API 失败仍保持 `functional_status=not_run`，不伪装成功能失败。`usage` 仅汇总已返回的计数，`usage_complete=false` 表示不能视为完整费用。已有输出目录不会覆盖。CLI 退出码：`0` 全通过，`1` 失败/未运行，`2` 配置/运行错误，`130` 中断。原始日志仅用于本地审计，不要整体上传给模型。

## 目录与进一步阅读

- `src/rtlflow/`：CLI、模型/Skill 工具、项目验证、Chisel 后端、评分与修复流水线。
- `data/requirements.json`：全部案例的唯一模型任务入口；`data/project-rtl/`仅保留来源、许可证和历史参考回归材料。
- 本地验证报告、日志和回放产物按需生成，不随仓库保留；输出位置见[运行与验证](docs/运行与验证.md)。
- `scripts/`：工具安装、固定版本数据导入、候选测试适配再生、参考验证与回放。
- `skills/rtl-readable/`：**核心优化与交付对象**，包含 Skill、通用规则与三种语言指导；`tests/`：临时单元夹具及回归。
- [运行与验证](docs/运行与验证.md)：环境准备、离线复现及数据维护。
- [评估规则](docs/评估规则.md)：实验口径、交付协议、功能判定及评分。
- [数据清单、许可与覆盖](data/project-rtl/README.md)。
