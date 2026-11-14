# 数据集

当前只有一套数据：[Project RTL：32 个开源硬件 IP](project-rtl/README.md)。

```text
project-rtl/
  tasks.json          # 唯一任务入口：来源、参考验证、模型生成配置
  specs/              # 每个项目一份有效需求说明，提供给模型
  sources/            # 锁定版本的上游源码、文档和许可证
  tests/              # 黑盒测试、固件和候选测试适配
  sources.lock.json   # 上游提交与文件哈希；仅用于来源锁定
```

**看需求 → `specs/<ID>.md`；选任务 → `tasks.json`；生成和检查验证结果 → [验收说明](../docs/验收.md)。**

32 个独立项目的原生语言 Verilog/SystemVerilog/Chisel 为 27/3/2；生成目标可选 27/30/2，不按翻译重复计数。当前仍为 pilot，未冻结 dev/test，也没有真实模型能力成绩。

```bash
python3 scripts/project_dataset.py --check-data
python3 scripts/project_dataset.py --stats
python3 run.py --check-data
```

这些检查不调用模型、不执行 HDL/Scala、不联网。首次检出需按[快速检查](../README.md)恢复锁定的上游源码。许可见 [LICENSES.md](project-rtl/LICENSES.md)。
