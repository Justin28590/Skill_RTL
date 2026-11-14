# 数据

模型主流程唯一输入：[`requirements.json`](requirements.json)，包含全部32个案例的高层需求和目标语言，不携带旧端口、参数、固定周期或TB路径。

```bash
python3 run.py --check-data
python3 run.py --task aes systolic_matmul --check-data
```

这些检查不调用模型、不执行HDL/Scala、不联网，也不需要下载参考源码。目标语言组合为Verilog/SystemVerilog/Chisel的27/30/2项，翻译不重复计为独立案例。数据仍为pilot，未冻结dev/test。

全部案例使用同一个[设计、冻结与独立验证流程](../docs/设计流程.md)。模型自行设计接口、参数、时序；外部标准和算法仍是需求约束。复杂设计的生成与验证可能失败或阻塞，清单覆盖不等于功能验证成绩。

[`project-rtl/`](project-rtl/README.md)保留开源来源、许可证、锁定源码及历史参考验证资料。其`tasks.json`、`specs/`和固定TB仅用于来源审计与底层工具回归；`run.py`不再加载它们，也没有旧流程开关。维护这些历史材料时才需要下载上游快照及运行对应脚本，见[运行与验证](../docs/运行与验证.md)。
