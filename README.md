# Bestar Work Hours

独立员工工时应用：上传 legacy `.xls` 打卡表 → 解析与复核 → 修正/删除及审计 → 按正式模板生成 Excel → 下载。打开即用，不需要登录或账户管理。

**同一实现支持本地 Docker Compose 与 Vercel 两个部署目标。**
Next.js 保留原工时页面、品牌、配色、主题和中英文；Python 保留 `wage-attendance-v2` 与正式脱敏模板。
PostgreSQL 事务保存原件、有效明细、变更记录和生成文件。无旧目录或旧服务依赖。

Vercel 生产入口：[Bestar 工时应用](https://work-hours.bestarcca.com/)。使用独立云数据库，免登录；本机 Docker 数据不会自动同步到云端。

## Windows 本机验证

按[部署手册](docs/DEPLOYMENT.md)启动 Docker 应用，上传自己的真实打卡表。无需账号，不预装测试员工。导出只包含实际员工表页及模板辅助页。

`.\scripts\verify-docker.ps1` 仅执行隔离的临时回归测试，结束后清理测试环境，不向实际应用写入数据。已在 localhost:3100 使用旧配置的本机继续沿用原 Compose 项目与 volume，操作见部署手册第一节。

## 运行与验证

- [部署手册](docs/DEPLOYMENT.md)：Windows PowerShell 启动、公司内网访问、重启恢复、备份恢复、Vercel 配置。
- [GitHub 操作指南](docs/GITHUB-GUIDE.md)：首次同步、日常提交、忽略文件和换机克隆。
- [业务验收](docs/REQUIREMENTS.md)、[引擎开发](apps/engine/README.md)、[引擎迁移说明](docs/ENGINE-MIGRATION.md)。

本机交接、开发约定和详细运行证据保留在本地，不随 GitHub 仓库分发；上传范围由 `.gitignore` 管理。

在项目根目录执行隔离的合成测试：

```powershell
docker compose -p bestar-hours-test -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from engine-tests
```

2026-10-01：Docker 引擎/API 测试 52 项通过，覆盖未使用员工模板页的移除及公式、格式和打印设置保留。
Vercel 前后端已于 2026-10-01 实际发布，正式域名与云数据库联通、只读浏览器检查通过。云端真实文件上传至导出、真实业务工时对照、Excel 打开与打印预览仍需验收。
GitHub 同步只包含代码、可分发文档与正式脱敏模板，不含真实员工记录或数据库。同步代码不等于更新线上应用；当前通过 Vercel CLI 单独发布。
