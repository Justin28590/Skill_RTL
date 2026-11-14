# 项目级 RTL 生成与验证

公开契约 → 生成完整多文件项目 → 独立编译与仿真 → 限轮修复/可读性重构 → 整项目交付或回退。

支持 **Verilog / SystemVerilog / Chisel**，默认模型 **GLM-5.3 / high**，Python 3.10+ 标准库实现。数据包含 [32 个开源 IP](data/project-rtl/README.md)：原生语言分别为 **27 / 3 / 2**；可选生成目标分别为 **27 / 30 / 2**，翻译不重复计数。数据仍为 pilot，未冻结 dev/test；离线回放不是模型生成成绩。

## 快速检查（不调用模型）

首次从 Git 获取项目后，先执行以下命令恢复未纳入版本控制的上游源码快照（需要联网，按 `sources.lock.json` 校验固定版本与哈希；不调用模型）：

```bash
python3 scripts/project_dataset.py --download
```

Git 保留源码、配置、文档、数据清单/契约及测试夹具；不记录 `.tools/`、上游下载快照、缓存、日志、验收生成产物、实验输出、密钥和本地课程 PDF。工具安装见[环境与依赖](docs/环境与依赖.md)。当前已有快照无需重新下载。

```bash
source scripts/env.sh
python3 run.py --check-data
python3 run.py --language systemverilog --check-data
python3 run.py --language chisel --check-data
python3 scripts/project_dataset.py --check-data  # 原始快照与锁定哈希
python3 -m unittest discover -s tests -v
```

普通回归不依赖历史验收报告和日志；两项本地证据哈希检查默认跳过，生成证据后可用 `RTL_VALIDATE_EVIDENCE=1` 启用，见[离线验收与复现](docs/验收.md)。

Linux、Python 3.10+ 和 Icarus Verilog/vvp 为基础依赖。Chisel 另需固定 JDK17、sbt1.10.7、Scala2.13.12、Chisel6.5.0、firtool1.62.0，见[环境与依赖](docs/环境与依赖.md)。`--check-data` 不运行 HDL/Scala、不联网、不读取密钥。

## 生成项目（消耗 API 额度）

```bash
read -rsp 'GLM API Key: ' GLM_API_KEY; echo
export GLM_API_KEY

python3 run.py --task fp32_fma --group Baseline --output results/fma-baseline
python3 run.py --task axis_packet_switch --group Skill --output results/switch-skill
python3 run.py --language systemverilog --task systolic_matmul --group Skill --output results/matmul-skill
python3 run.py --language chisel --task chisel_double_buffer_fifo --group Skill --output results/fifo-skill

# 同一任务的两组独立对照
python3 run.py --task aes --groups Baseline Skill --output results/aes-comparison
```

**务必先选择任务和组别。** 未指定时运行该语言全部项目、Baseline/Skill 两组。默认 Verilog 上限为 54 份结果、216 次候选生成、756 次 HTTP 尝试；执行前会显示预算。

配置在 [`configs/glm.json`](configs/glm.json)，默认 `max_repairs=2`、`max_refactors=1`、阈值95、`max_tokens=32768`、`max_agent_turns=6`。两组仅切换 Skill 加载；模型、公开契约、评分、反馈、验证和预算上限相同，源码和对话互不共享。Skill 读取增加的 HTTP/token/耗时单独记录，不宣称总成本相同。

## 产物与验证约定

模型每轮交付完整快照，而非补丁：

```json
{"files":[{"path":"rtl/top.v","content":"<完整顶层源码>"},{"path":"rtl/core.v","content":"<完整子模块源码>"}]}
```

- 最多128个文件、源码总计2 MB；限定项目内路径与语言后缀，拒绝外部 include、宿主 I/O、仿真系统任务和参考源码回填。
- 候选先独立预处理/编译，再与可信 TB 链接；核对公开参数、端口、实际子模块层次及功能日志。编译成功或退出码0不等于功能通过。
- 只向修复模型提供候选编译诊断和粗粒度失败原因，不发送隐藏 TB、期望值或原始仿真日志。
- 功能通过且低分时才重构；新项目功能通过且分数严格提高才接受，否则回退整个项目。
- Chisel 仅支持清单中的固定构造配置；候选不能自带构建脚本或外部 RTL。可读性评分针对 Scala 源码，不是展开后的 RTL。

完整[协议与信任边界](docs/项目级生成.md)、[评分规则](docs/源码可读性评分.md)。**超时和源码过滤不是安全沙箱**；不可信 HDL/Scala 应在无密钥、无网络、非特权且有限资源的环境执行。项目级可选 Lint 尚未接入，报告为 `not_run`。

## 输出

```text
results/<run>/
  config.json, summary.json, summary.csv
  <组>/<项目>/                 # 单组运行无组目录
    report.json                # schema 4，状态、成本、哈希、选择理由
    final.project.json, final/ # 被保留的完整快照
    final-rtl/                 # 仅 Chisel：选中轮次展开的 RTL
    attempt_00_initial/        # prompt、response、source、checks
    attempt_01_repair/ ...
```

`final/` 存在不代表功能通过；检查 `functional_status`、`initial_functional_status`、`stop_reason` 和 `selected_attempt`。已有输出目录不会覆盖。CLI 退出码：`0` 全通过，`1` 失败/未运行，`2` 配置/运行错误，`130` 中断。原始日志仅用于本地审计，不要整体上传给模型。

## 目录与进一步阅读

- `src/rtlflow/`：CLI、模型/Skill 工具、项目验证、Chisel 后端、评分与修复流水线。
- `data/project-rtl/`：`tasks.json`统一任务入口，`specs/`需求、`sources/`原件、`tests/`测试。
- 本地验证报告、日志和回放产物按需生成，不随仓库保留；输出位置见[验收说明](docs/验收.md)。
- `scripts/`：工具安装、固定版本数据导入、候选测试适配再生、参考验证与回放。
- `skills/rtl-readable/`：Skill 与三种语言的编码指导；`tests/`：临时单元夹具及回归。
- [数据清单、许可与覆盖](data/project-rtl/README.md) · [离线验收与复现](docs/验收.md) · [计算与互连案例](docs/计算与互连案例.md) · [实验计划](docs/实施方案.md)。
