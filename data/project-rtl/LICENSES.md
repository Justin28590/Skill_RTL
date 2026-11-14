# 上游许可索引

此数据集不对上游代码重新许可。原始文件、版权声明、免责声明和许可证均保持不变；使用、修改和分发时应遵守对应文件的具体条款。下表为索引，不代替完整许可或逐文件审查，尤其不能把全部案例统一标成 MIT。

| 来源 | 主要 RTL 许可 / 原文位置 |
| --- | --- |
| `secworks/aes`, `chacha`, `sha1`, `sha256`, `sha512`, `blake2s`, `md5`, `cmac`, `prince`, `poly1305`, `xtea` | BSD-2-Clause；各目录 `LICENSE` 及源文件头 |
| `secworks/siphash` | BSD-2-Clause；`sources/secworks/siphash/LICENSE.txt` |
| `YosysHQ/picorv32` | ISC；`sources/YosysHQ/picorv32/COPYING`；第三方 ISA 测试还保留各自的原文件声明 |
| `ZipCPU/wbuart32` | GPL-3.0-or-later，见 `sources/ZipCPU/wbuart32/LICENSE` 和 RTL 文件头 |
| `freecores/sha3` | Apache-2.0；`sources/freecores/sha3/LICENSE` 和 RTL 文件头 |
| `freecores/spi` | LGPL-2.1-or-later；`sources/freecores/spi/rtl/verilog/spi_top.v` 等文件头 |
| `freecores/usbhostslave` | LGPL-2.1-or-later；`sources/freecores/usbhostslave/RTL/wrapper/usbHost.v`、`usbSlave.v` 等文件头 |
| `freecores/i2c` | 上游自定义宽松声明，要求保留版权与免责声明；`rtl/verilog/i2c_master_top.v` 等文件头 |
| `freecores/des` | 上游自定义宽松声明，要求保留版权与免责声明；`rtl/verilog/perf_opt/des3.v` 等文件头 |
| `freecores/aes_core` | 上游自定义宽松声明，要求保留版权与免责声明；`rtl/verilog/aes_cipher_top.v` 等文件头 |
| `alexforencich/verilog-uart`, `alexforencich/verilog-axis`, `alexforencich/verilog-axi` | MIT；各目录`COPYING`，作者Alex Forencich；包含流交换、异步帧FIFO、DMA和双端口存储依赖 |
| `bsg-external/HardFloat`（固定Release 1导入） | BSD-3-Clause；`sources/bsg-external/HardFloat/COPYING.txt`及每个源文件头，Copyright 2019 The Regents of the University of California；保留全部声明 |
| `tms4517/2D-Systolic-Array-Multiplier` | MIT；`sources/tms4517/2D-Systolic-Array-Multiplier/LICENSE`，Copyright (c) 2023 Tej Sanghavi；原始RTL不改，Icarus兼容副本仍适用此许可 |
| `pConst/basic_verilog` | CC BY-SA 4.0；`sources/pConst/basic_verilog/README.md`的Licensing节，作者Konstantin Pavlov；[许可全文](https://creativecommons.org/licenses/by-sa/4.0/legalcode) |
| `schoeberl/chisel-examples` | BSD-2-Clause；`sources/schoeberl/chisel-examples/LICENSE`，Martin Schoeberl；UART头部另保留DTU署名 |

新增pConst构建副本/公开接口摘录属于派生件，仍按CC BY-SA 4.0分发并保留作者署名：显式补齐parameter关键字，SPI依赖的复位端口旧名nrst映射为anrst；原件不修改。回放和日志中的源码副本不改变适用许可。Chisel兼容性修改仅为旧CLI emitter删除及构造期assert→require，仍保留BSD版权声明。

完整仓库快照还包含文档、测试程序、脚本、图片等资产，它们可能适用独立声明；不要仅凭主要 RTL 的许可推断所有资产的许可。公开需求与接口摘录在 `specs/`，来源与上述项目一致，完整版权声明随相应 `sources/` 原件一起保留。数据集自编的验证文件位于 `tests/blackbox/`，不会冒称上游原版测试。
