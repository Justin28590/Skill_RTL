# 工程回归测试

这里检查流程和评估工具，不评估Skill效果，也不调用真实模型API。`test_design_flow.py`覆盖当前需求设计主流程；`data/project-rtl/tests/`仅用于历史来源与底层工具回归，不参与新模型运行。

## 按改动范围运行

仅修改 Skill 文档或已有 HDL 示例时：

```bash
python3 -m unittest discover -s tests -p 'test_skill*.py' -v
```

其他修改可按模块选择；命令在仓库根目录执行，例如：

```bash
# 验证、修复、回退及两组公平性
PYTHONPATH=src:tests python3 -m unittest -v test_design_flow test_cli test_verify test_pipeline test_comparison

# 配置、HDL/Chisel 评分
PYTHONPATH=src:tests python3 -m unittest -v test_core test_chisel_score

# 正式冻结前，或改动跨多个模块时
python3 -m unittest discover -s tests -v
```

Icarus/vvp 缺失时，依赖真实 HDL 编译/仿真的测试会跳过，不代表通过。实际 Chisel 构建另用 `RTL_CHISEL_INTEGRATION=1 python3 -m unittest discover -s tests -p 'test_chisel.py' -v`；需要固定工具链，缺缓存时可能下载依赖。数据相关集成测试需要恢复上游快照，见[运行与验证](../docs/运行与验证.md)。

## 保留范围与精简原则

- `test_skill*.py`：可独立复制的Skill目录与内链、通用文档/评测约束分离、HDL示例、受限加载、读取证据、工具轮次与两组实际调用差异。
- `test_core.py`、`test_glm_provider.py`、`test_glm_stream.py`、`test_chisel*.py`：配置、协议、评分和语言后端。流式回归覆盖正文/工具参数分段、超时/断流/截断、用量完整性、脱敏及两组真实 HDL 修复链，HTTP 全部为本地模拟。
- `test_design_flow.py`：全部案例的高层输入、通用契约、独立审查、冻结/防篡改、TB策略/负控、不同接口与延迟、RTL修复及全部阶段成本。
- `test_design_protocol.py`：按语言生成有效契约示例、单个 JSON 围栏的受限兼容与审计、拒绝非法/截断/混合响应、语言与参数一致性反馈；用模拟 HTTP 和真实 HDL 验证一次设计修订后的完整流程，禁止绕过独立审查。
- `test_workflow_skill.py`：全流程每阶段/每轮Skill加载、TB使用SystemVerilog参考、Baseline无加载、审查/验证/RTL上下文隔离、缺失/部分读取阻止推进、早停与整项目回退的加载证据，以及报告/CSV成本计数；HTTP模拟、HDL真实验证。
- `test_cli.py`：默认全部任务/语言/组别、支持组合筛选、离线计划与预算、多语言产物隔离和汇总。
- `test_verify.py`、`test_pipeline.py`、`test_comparison.py`：功能判定、输入隔离、修复/回退、预算与组间独立性。共享控制器不再按两组完整重复测试；两组一致性由专项测试覆盖。
- `test_project_dataset.py`、`test_dataset_import.py`：小型临时夹具上的数据完整性、判据有效性及导入保护。
- `test_project_generation.py`、`test_compute_projects.py`、`test_modern_projects.py`：代表性真实项目集成和语义故障拒绝，防止“编译成功即功能通过”。

`ImplementationTestCase`仅在测试中把调用接到私有RTL实现层，复用已有修复/回退/HTTP夹具；生产入口没有跳过设计的开关。完整主流程另由`test_design_flow.py`验证。

不再锁死历史项目数、旧目录和迁移前清单摘要，也不依赖历史验收报告。当前输入哈希校验、负向对照和数据集 Testbench 保留；全量数据验证通过[验收脚本](../docs/运行与验证.md#工程回归与离线验收)按需运行。

回归通过后，仍需用真实模型对旧版/新版 Skill 做同条件任务对照，才能判断优化是否有效。
