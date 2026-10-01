# Bestar Work Hours

独立员工工时应用：上传 legacy `.xls` 打卡表 → 解析与复核 → 修正/删除及审计 → 按正式模板生成 Excel → 下载。打开即用，不需要登录或账户管理。

**同一实现支持本地 Docker Compose 与 Vercel 两个部署目标。**
Next.js 保留原工时页面、品牌、配色、主题和中英文；Python 保留 `wage-attendance-v2` 与正式脱敏模板。
PostgreSQL 事务保存原件、有效明细、变更记录和生成文件。无旧目录或旧服务依赖。

## Windows 本机验证

在项目根目录的 PowerShell 执行 `.\scripts\verify-docker.ps1`，仅需已运行的 Docker Desktop（Linux 容器）。脚本运行测试并启动 http://localhost:3100，完成后保留服务供人工验证。无需账号；公司内网部署步骤见部署手册。

## 运行与验证

- [部署手册](docs/DEPLOYMENT.md)：Windows PowerShell 启动、公司内网访问、重启恢复、备份恢复、Vercel 配置。
- [GitHub 操作指南](docs/GITHUB-GUIDE.md)：首次同步、日常提交、忽略文件和换机克隆。
- [业务验收](docs/REQUIREMENTS.md)、[引擎开发](apps/engine/README.md)、[引擎迁移说明](docs/ENGINE-MIGRATION.md)。

本机交接、开发约定和详细运行证据保留在本地，不随 GitHub 仓库分发；上传范围由 `.gitignore` 管理。

在项目根目录执行隔离的合成测试：

```powershell
docker compose -p bestar-hours-test -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from engine-tests
```

2026-10-01：Docker 引擎/API 测试 47 项通过；完整 Compose 构建运行、浏览器合成闭环已通过。
真实/获准脱敏样例、Excel 打开与打印预览、实际 Vercel 发布仍待验收，不能据此声称全部完成。
GitHub 同步只包含代码、可分发文档与正式脱敏模板，不含真实员工记录或数据库。同步代码不等于发布应用；Vercel 部署仍需单独操作。
