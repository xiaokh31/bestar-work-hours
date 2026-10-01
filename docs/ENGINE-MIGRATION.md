# 工时引擎迁移记录

更新：2026-10-01。来源为只读旧项目提交 `1608420b6f5cd160624012b105cb5069261aa569`。

保留原 attendance.py、generator.py、legacy_xls.py、template.py 的计算与 BIFF 行为；只调整包命名、模板资源定位、归属说明及 manifest 的跨平台 LF 换行。
`service/persisted.py` 仅提取持久化行适配，未引入旧 worker/batch/队列。
正式模板及 manifest 字节保持一致：

- XLS SHA-256：`f9e11d6f2c6f45b0453f8346df2ff8347f2e6f5c8b7505a642367f1dade4206c`
- JSON SHA-256：`0abffe356f8ecb5ea0d88da8420a6039461935d66da7088ee5a0d855021b99d3`
- 16 名员工容量、17 张表、284 条公式、58 组合并、107 个 XF；相关公式、周末底色和打印结构有回归检查。

Python 统一使用 3.14（本机和 Docker 实测 3.14.5），便于保持本地/Vercel 一致。
依赖精确版本及 PyPI 制品 SHA-256 位于 requirements*.lock；仅安装锁定制品。
wheel 含正式模板，独立子进程测试使用 `python -I`，无旧项目路径依赖。

原件、完整解析 rawRows/未知值/warning/error 持久化；人工修正保留 rawCellValues，审计保存修正前后快照。
API 导出从有效持久化明细生成，原始文件、模板和既有生成文件不会被覆盖。
独立 CLI 仅用于验证原始源文件，不处理应用历史修正/删除。

初次宿主测试发现 Windows CRLF 与正式 LF manifest 的差异，已显式写 LF 并通过复测。
Docker 内现有引擎/API 测试 47 项通过（含 PostgreSQL 和 SQLite 合成测试）。
初始静态检查与后续详细验证记录保存在本地，不随仓库分发；当前应用无需登录。
全部 fixture 明确标注为合成数据；未复制旧 samples 中真实员工数据。
Apache-2.0 许可和归属见 LICENSE、NOTICE。
