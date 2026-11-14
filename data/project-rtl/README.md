# Project RTL：32 个开源 IP

唯一任务入口 [`tasks.json`](tasks.json)（`project-rtl-32-v4`，格式 `project-rtl-v2`）。每个项目只保留一份有效需求说明；来源、参考验证与候选生成配置按项目集中记录。不按参数变体或翻译目标重复计数。

## 先看哪里

| 想做什么 | 路径 |
| --- | --- |
| 看模型需要实现什么 | `specs/<ID>.md`，共32份，不含参考实现或隐藏测试正文 |
| 选项目、查语言/编译/验证配置 | `tasks.json`，唯一任务清单 |
| 看原版源码、文档和许可 | `sources/<组织>/<仓库>/`；版本与哈希在 `sources.lock.json` |
| 看自编测试和CPU固件 | `tests/blackbox/` |
| 看上游TB的候选适配版本 | `tests/adapted/<ID>/`；原版仍在 `sources/` |
| 生成和查看运行报告、日志与回放源码 | 按[验收说明](../../docs/验收.md)生成到本地输出目录，不混入数据集 |

`tasks.json` 的 `tasks` 数组中，每项的 `specification` 指向唯一需求文件，`rtl_files` / `testbench_files` 定义原版验证输入，`generation` 集中记录候选TB、接口/参数及适配说明。需求、上游原件和测试仍校验SHA-256；目录简化不取消来源或验证约束。模型只读取需求正文，不接收整个清单。

| 语言 | 原生项目 | 可选生成目标 |
| --- | ---: | ---: |
| Verilog | 27 | 27 |
| SystemVerilog | 3 | 30 |
| Chisel | 2 | 2 |

数据为 **pilot**，没有冻结dev/test或模型能力成绩。支持三语言完整多文件生成、修复和回退；Chisel仅支持清单中的固定构造配置，不能直接承接全部Verilog任务。

## 项目清单

模块数为 Icarus 实际展开的“模块类型 / 实例”，含DUT顶层、不含测试环境。多个测试配置仍算一个案例。

| ID | 设计 | 模块类型 / 实例 | 上游仓库 |
| --- | --- | --- | --- |
| `aes` | AES-128/256寄存器、密钥扩展、加解密 | 7 / 7 | `secworks/aes` |
| `chacha` | ChaCha接口、轮函数、密钥流 | 3 / 6 | `secworks/chacha` |
| `sha1` | SHA-1接口、压缩核、消息调度 | 3 / 3 | `secworks/sha1` |
| `sha256` | SHA-224/256接口、压缩、常量与调度 | 4 / 4 | `secworks/sha256` |
| `sha512` | SHA-512系列接口、压缩、调度 | 5 / 5 | `secworks/sha512` |
| `blake2s` | BLAKE2s接口、控制、G函数 | 4 / 7 | `secworks/blake2s` |
| `md5` | MD5接口、迭代压缩、多块处理 | 2 / 2 | `secworks/md5` |
| `cmac` | CMAC接口、认证控制、完整AES依赖 | 8 / 8 | `secworks/cmac` |
| `prince` | PRINCE接口、加解密核 | 2 / 2 | `secworks/prince` |
| `poly1305` | Poly1305分块、乘累加、归约 | 5 / 8 | `secworks/poly1305` |
| `siphash` | SipHash接口、压缩、最终处理 | 2 / 2 | `secworks/siphash` |
| `xtea` | XTEA接口、多周期加解密 | 2 / 2 | `secworks/xtea` |
| `i2c_master` | Wishbone寄存器、字节/位控制器 | 3 / 6 | `freecores/i2c` |
| `spi_master` | Wishbone寄存器、分频、移位引擎 | 3 / 3 | `freecores/spi` |
| `triple_des` | 流水DES、轮函数、密钥与S-box | 12 / 439 | `freecores/des` |
| `keccak` | Keccak-512流接口、填充、置换 | 6 / 6 | `freecores/sha3` |
| `aes_opencores` | AES-128加密/解密双顶层 | 6 / 46 | `freecores/aes_core` |
| `picorv32_axi` | RV32IMC CPU、乘除法、AXI适配 | 5 / 5 | `YosysHQ/picorv32` |
| `wbuart32` | Wishbone UART、TX/RX、双FIFO | 4 / 5 | `ZipCPU/wbuart32` |
| `usb_host_device` | USB1.1 Host/Device、FIFO、SIE/CRC | 44 / 96 | `freecores/usbhostslave` |
| `uart_axis` | AXI-Stream全双工UART | 3 / 3 | `alexforencich/verilog-uart` |
| `axis_fifo_adapter` | AXI-Stream位宽转换和FIFO | 3 / 3 | `alexforencich/verilog-axis` |
| `sv_spi` | SystemVerilog SPI命令/读写控制器 | 3 / 6 | `pConst/basic_verilog` |
| `sv_uart_printer` | SystemVerilog格式化与UART发送 | 2 / 2 | `pConst/basic_verilog` |
| `chisel_uart_echo` | Chisel接收、缓冲、发送 | 5 / 5 | `schoeberl/chisel-examples` |
| `chisel_double_buffer_fifo` | Chisel四级双缓冲FIFO | 2 / 5 | `schoeberl/chisel-examples` |
| `systolic_matmul` | UINT8矩阵乘法、二维PE网格与调度 | 3 / 95 | `tms4517/2D-Systolic-Array-Multiplier` |
| `axis_packet_switch` | 多端口流路由、整帧仲裁、skid缓冲 | 4 / 13 | `alexforencich/verilog-axis` |
| `fp32_fma` | 浮点融合乘加、六种舍入、IEEE异常 | 14 / 26 | `bsg-external/HardFloat` |
| `axi_dma_engine` | 双向描述符DMA、非对齐/4KiB分割 | 3 / 3 | `alexforencich/verilog-axi` |
| `axi_scratchpad` | 双端口AXI共享RAM、仲裁、流水 | 4 / 7 | `alexforencich/verilog-axi` |
| `axis_async_bridge` | 异步帧FIFO、位宽转换、坏帧丢弃 | 3 / 6 | `alexforencich/verilog-axis` |

“完整”指所选可移植IP配置，不是整个FPGA工程或板卡软件。PicoRV32虽只有一个RTL文件，仍有完整多模块层次；Chisel教学IP与USB/CPU不具有同等复杂度。I²C测试实例化两个控制器，USB/OpenCores AES各有两个公开顶层；脉动阵列95实例是N=3/4/8三个DUT总和，异步桥6实例是两个DUT总和。

## 整理与保留原则

原来的 `public/` 和 `contracts/` 合并为 `specs/`，沿用完整生成契约，不再维护两套说明。两个任务清单合并为 `tasks.json`；`sources.lock.json` 仍独立负责27个上游仓库的提交、归档及原文件哈希。候选适配与自编测试集中到 `tests/`，区别由子目录明确标注。

原始源码、有效需求、测试逻辑和 [LICENSES.md](LICENSES.md) 保留；适配TB的说明头更新为新入口。旧入库说明、旧清单和历史运行记录不再随项目保留。回归继续锁定原有28项参考任务语义，不依赖历史归档；运行证据按需重新生成。各上游保留原版权，不统一视为MIT。

## 验证与覆盖边界

参考验证检查固定输入哈希、实际DUT层次、全部成功标记/次数及完整stdout/stderr无失败。每项另在可信测试侧强制错误输出；只有明确失败信息或错误退出才算对照有效，编译失败或单纯超时不算。候选链还检查仅候选编译、接口/参数和隐藏测试隔离，见[项目级生成](../../docs/项目级生成.md)。

验收入口：参考32项（`artifacts/project-rtl/reference/summary.json`），候选回放27/30/2项（`artifacts/project-rtl/candidate/<语言>/summary.json`），路径相对于仓库根目录。均要求正向与错误输出对照，模型调用0。生成产物不随Git分发，首次检出需按[验收说明](../../docs/验收.md)自行生成并核验，不能仅凭文档认定验证通过。每项只有一个预定错误对照，不是对所有项目做全0/全1/全X，更不是形式证明。

- Secworks 12项使用上游顶层自检TB；CMAC的AES依赖来自同一锁定快照。
- SPI覆盖8次传输、1/8/16/32/64/128位、边沿/位序/IRQ/自动片选；用Verilog-2005避免上游`int`标识符冲突。
- I²C覆盖寄存器、写入、重复起始、ACK/NACK、拉伸及`a5/5a`读回；后续未写地址的`xx`不算正确数据。错误对照先明确比较失败、后超时，不是把超时当证据。
- Triple-DES有8个流水已知答案；OpenCores AES有284组加密答案及解密检查。Keccak有7条消息，采用旧Keccak-512填充，**不是FIPS SHA3-512**。
- PicoRV32运行原AXI TB及45份ISA汇编套件，启用RV32IMC和`+axi_test`；固定xorshift64初值88172645463325252。不是完整上游C固件/IRQ验证。候选层另核对64次独立AXI算术/load-store结果，不只信软件打印。
- Wishbone UART两个方向各独立验证256字节、FIFO回绕/寄存器/中断；主要为8N1，未覆盖全部奇偶/break/RTS/CTS。USB为独立host/device套件的12项检查，未采用另一套存在重复参数问题的combined-role TB。
- UART AXI验证独立双向字节；FIFO adapter验证8→32打包、边带和背压；SV SPI主要验证mode0写、全0/全1读；串口打印验证两条记录。Chisel UART独立解码，FIFO覆盖填满、1000周期背压、排空和复位。
- 脉动阵列检查120组矩阵/3560元素，交换器检查4入2出192帧；FMA为3432组独立有理数答案，DMA为24读+24写描述符，共享RAM为33写突发/576读拍，异步桥两套时钟各48帧（41好/7坏）。具体配置见[计算与互连案例](../../docs/计算与互连案例.md)。不声称完整NPU/FPU/NoC、缓存一致性、穷尽IEEE一致性或物理CDC签核。

## 兼容性改动（仅构建/回放副本）

原始RTL/TB始终按锁定哈希检查，不修改；所有归一化在report披露，不放宽正常模型源码策略。

- HardFloat参考固定Release 1、8/24精度和RISC-V NaN特化。候选回放将`.vi`头改为`.vh`，generate内部wire链等价改为父作用域数组，顶层占位默认3/3改为8/24以便独立编译；不改算术。
- DMA、共享RAM、异步桥、FIFO adapter仅在候选回放删除无效参数诊断；交换器另删除配置打印。参考原件保留这些诊断。
- 脉动阵列显式化端口类型、将`int unsigned`写成等宽无符号`logic [31:0]`、诊断移入`initial`，两个packed边界连接用wire连续赋值；不改算法/时序。候选回放另移除无效N诊断。
- pConst为Icarus重复typed parameter关键字，SPI将依赖旧复位端口`.nrst`映射为同提交的`.anrst`；保留Konstantin Pavlov署名与CC BY-SA 4.0要求。
- Chisel不运行上游build.sbt；移除未用旧CLI emitter，将FIFO构造断言改为Scala `require`。固定构造为`uart.Echo(800,100)`、`fifo.DoubleBufferFifo(UInt(8.W),8)`，不改硬件逻辑。
- USB原文件清单按实际大小写解析，候选回放另移除两条非综合`$display`。候选TB适配另见`tasks.json`各项目的`generation.testbench_adaptations`，不能冒称逐字节原版TB。

## 复现与维护

```bash
python3 scripts/project_dataset.py --check-data
python3 scripts/project_dataset.py --stats
python3 run.py --check-data

# 新目录，不覆盖现有证据
python3 scripts/project_dataset.py --verify-reference --output /tmp/rtl-reference-new
python3 scripts/verify_project_replay.py --negative-controls --compact --output /tmp/rtl-candidate-new

# 以下为显式维护操作；下载会联网
python3 scripts/project_dataset.py --download
python3 scripts/build_project_firmware.py --output /tmp/rtl-firmware-new
python3 scripts/prepare_project_generation.py
```

三语言全量复现见[验收说明](../../docs/验收.md)。固件重建需要LLVM18；候选适配层和接口元数据再生需要Icarus与固定Chisel工具链。`prepare_project_generation.py`不再重写需求，`specs/`是唯一受审阅的需求来源。数据扩充脚本保留可复现入口，见[计算与互连案例](../../docs/计算与互连案例.md)。修改契约、测试或验证器后必须重跑相关证据，不能只更新旧报告哈希。

参考验证只运行审阅且锁定的原件，不是未信任代码沙箱。Chisel缺缓存时可能访问Maven；工具缺失不自动安装、不伪报通过。保存的绝对路径记录执行位置，迁移后可核对哈希或重新运行。

## 实验限制

15/32项属密码/散列/认证，领域分布不均；AES/CMAC共享源码，AES和SHA家族、同仓库项目须保守分组切分，防止泄漏。公开契约和有限TB仍需独立领域审查，参考回放成功不保证盲生成成功。MD5/SHA-1/DES/XTEA仅用于硬件测试，不是密码安全推荐。测试临时最小夹具不作为实验案例。
