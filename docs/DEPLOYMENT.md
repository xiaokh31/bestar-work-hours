# Windows 公司内网与 Vercel 部署

更新：2026-10-01。公司本地部署目标为 **Windows 电脑 + Docker Desktop + Linux 容器**。
命令在 Windows PowerShell 5.1 或 PowerShell 7 中执行。Windows 不需要安装本项目的 Python、Node.js 或 PostgreSQL；依赖随 Docker 镜像安装。
Vercel 继续作为另一部署目标，与本地共用业务代码。
应用无需登录和账户配置，打开后直接上传考勤表、计算复核工时、生成并下载 Excel。访问同一部署地址的人共用该部署中的工时记录。

## 一、本机使用与验证

首次使用按第三节创建 `.env` 并启动正式应用，上传自己的真实打卡表。项目不会预装员工记录。
生成的 Excel 只保留本次有效员工的表页及正式模板的 `ADJUSTMENTS` 辅助页；未使用的 `EMPLOYEE-xx` 占位页不会导出。

已在旧版 `http://localhost:3100` 上传真实表格的本机，请继续使用现有 `.env.smoke` 和 Compose 项目名 `bestar-hours-smoke`。
这些名称是历史遗留，当前数据库可包含真实业务数据；更换项目名会连接另一个 volume，不能当作数据迁移方式。
不要执行 `down -v`、重置数据库或再次运行旧版填充测试记录的脚本。正常更新和启动如下：

```powershell
Set-Location 'D:\works\github\bestar-work-hours'
docker compose --env-file .env.smoke -p bestar-hours-smoke up --build -d
docker compose --env-file .env.smoke -p bestar-hours-smoke ps
Invoke-RestMethod -Uri 'http://localhost:3100/api/health'
```

使用 `localhost`，不要混用 `127.0.0.1`：APP_ORIGIN 校验完整 origin。
需要将旧版已有业务数据迁移到其他电脑或新的部署配置时，按第六节备份恢复，同时核对记录数量和源文件 SHA-256。

开发者可在 Docker Desktop 已启动时单独运行回归验证：

```powershell
.\scripts\verify-docker.ps1
```

脚本自动定位 Docker CLI、检查 Linux 容器，然后在 `bestar-hours-test` 的独立网络、无宿主端口、tmpfs 数据库中运行引擎/API 测试。
结束后删除临时测试容器；不会启动、重启或写入日常使用的工时应用，也不会创建测试 Excel 到项目目录。
合成边界用例只在临时测试环境生成，不作为业务记录。旧的 `docker-verify.py`、`create-e2e-fixture.py` 已移除。
如果公司策略限制 PowerShell 脚本执行，请由 IT 按现行策略批准该本地脚本；本文不要求更改全局执行策略。

人工验收使用获准的真实打卡文件：核对员工数量、日期与工时，下载 Excel，在本机 Excel 中检查公式重算和打印预览。
不要为验证而修改真实打卡；确需复核修正时使用业务认可的理由，保留变更历史。

## 二、公司 Windows 电脑的准备

使用公司支持的 Windows 桌面系统和 Docker Desktop，启用 BIOS/UEFI 虚拟化。
新安装一般选择 WSL 2 后端；已能运行 Linux 容器的 Docker Desktop 后端可以保持现状。
本项目的 Linux 镜像在 Windows 宿主上运行，**无需切换为 Windows containers 或改写 Dockerfile**。
Docker Desktop 不支持 Windows Server 版本；如果将来改用 Windows Server，需要另行选择容器主机方案。
系统支持条件与后端说明见 [Docker Windows 安装文档](https://docs.docker.com/desktop/setup/install/windows-install/) 和 [WSL 2 后端文档](https://docs.docker.com/desktop/features/wsl/)。

从开始菜单打开 Docker Desktop，等待引擎就绪，然后检查：

```powershell
docker version
docker compose version
docker info --format '{{.OSType}}'
```

第三条应输出 `linux`，第一条应同时出现 Client 和 Server。
若当前终端找不到 Docker，重新打开终端；全用户安装也可临时补全当前窗口的 PATH：

```powershell
$env:PATH = 'C:\Program Files\Docker\Docker\resources\bin;' + $env:PATH
```

若使用其他安装路径，应换为自己的 Docker CLI 所在目录。只补 docker.exe 的绝对路径而不补 PATH，拉取镜像时可能找不到 docker-credential-desktop。
首次构建需要下载镜像和锁定依赖；公司网络使用代理时，在 Docker Desktop 的代理设置中配置，由引擎访问镜像仓库。

## 三、Windows 正式部署：首次启动

以下示例均从 `D:\works\github\bestar-work-hours` 执行。目录不同就调整 Set-Location；路径含空格时保留引号。
固定使用项目名 `bestar-work-hours`，避免换目录后意外连接一个新的空 volume。

### 1. 创建数据库和服务连接配置

```powershell
Set-Location 'D:\works\github\bestar-work-hours'
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
docker build --target runtime -t bestar-work-hours-api .\apps\engine
docker run --rm bestar-work-hours-api python -c "import secrets; print(secrets.token_hex(32))"
notepad .env
```

随机数命令执行两次，分别作为 POSTGRES_PASSWORD 和 API_SERVICE_SECRET，不重复使用。它们是服务运行配置，浏览器无需输入。
编辑 `.env`：

- POSTGRES_PASSWORD：随机十六进制，避免数据库 URL 转义问题。
- API_SERVICE_SECRET：另一段至少 32 字符的随机值。
- APP_ORIGIN=http://localhost:3000、WEB_PORT=3000、WEB_BIND_ADDRESS=127.0.0.1：先本机验证。

`.env` 已被忽略；不要将它连同运行数据、备份或真实员工文件提交到仓库。
已有数据库时，不要仅通过修改 POSTGRES_PASSWORD 来“重置”数据库密码；该值用于初始化和应用连接，现有数据库用户密码不会随之改变。

### 2. 启动与健康检查

```powershell
docker compose --env-file .env -p bestar-work-hours config --quiet
docker compose --env-file .env -p bestar-work-hours up --build -d
docker compose --env-file .env -p bestar-work-hours ps --all
Invoke-RestMethod -Uri 'http://localhost:3000/api/health'
```

顺序是数据库健康 → migrate 完成 schema 初始化 → API 健康 → Web。
migrate 显示 Exited (0) 属于正常结果；database/api 应 healthy，web 应 running。
健康接口应显示 status=ok、database.status=up。打开 `http://localhost:3000`，直接进入工时页。
`config --quiet` 只检查配置，不把解析后的秘密打印到终端。

## 四、同事通过公司内网访问（需要时再配置）

当前本机验证不会打开局域网端口。正式内网部署按实际访问地址修改 `.env`，例如以下 **192.168.1.50 是示例，必须换为部署电脑的内网固定 IP**：

```dotenv
WEB_BIND_ADDRESS=192.168.1.50
WEB_PORT=3000
APP_ORIGIN=http://192.168.1.50:3000
```

绑定指定内网网卡后，本机和同事都使用 `http://192.168.1.50:3000`，不再用 localhost。
修改后重建容器配置：

```powershell
docker compose --env-file .env -p bestar-work-hours up -d
```

确需开放该端口时，让 IT 在管理员 PowerShell 创建限定公司网段的入站规则（下例为同子网、Domain/Private 配置文件）：

```powershell
New-NetFirewallRule -DisplayName 'Bestar Work Hours TCP 3000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 -Profile Domain,Private -RemoteAddress LocalSubnet
```

不关闭 Windows 防火墙，不暴露数据库 5432 或 API 8000。规则需与实际网段、端口和公司策略匹配；本文的脚本不会自动创建规则。
同事电脑可用 `Test-NetConnection 192.168.1.50 -Port 3000` 检查连通性。

真实员工数据部署宜接入公司现有 HTTPS 反向代理和内部域名，例如 APP_ORIGIN=https://hours.company.example；反代转发到本机或内网 Web 端口。
如果反代就在本机，可继续保持 WEB_BIND_ADDRESS=127.0.0.1。
应用只使用语言和主题偏好 Cookie，不创建登录会话。APP_ORIGIN 不带尾随 `/`，并须与浏览器最终访问地址完全一致。

## 五、Windows 重启、日常运行与更新

在 Docker Desktop 设置中启用 “Start Docker Desktop when you sign in”，参见 [Docker Desktop 设置](https://docs.docker.com/desktop/settings-and-maintenance/settings/)。
电脑重启后先完成 Windows 登录，等待 Docker Desktop 引擎就绪，再检查容器。
`restart: unless-stopped` 会在引擎恢复后恢复此前运行的长期服务；手动 stop 过的服务要重新 up。
这不是“无人登录也保证运行”的 Windows 服务部署。运行期间应避免公司电脑进入睡眠。

```powershell
Set-Location 'D:\works\github\bestar-work-hours'
docker compose --env-file .env -p bestar-work-hours up -d
docker compose --env-file .env -p bestar-work-hours ps
docker compose --env-file .env -p bestar-work-hours logs --tail 100 api web
```

正常暂停用 `docker compose --env-file .env -p bestar-work-hours stop`；保留持久数据。
更新前先备份，再使用 `up --build -d`。不要对有业务数据的项目执行 `down -v` 或删除 Docker Desktop 的数据 volume。
当前为 schema v2。已有 v1 在 migrate 中自动移除旧登录会话和登录限流表，考勤原件、明细、变更记录和导出不变。旧 MANAGER_USERNAME/MANAGER_PASSWORD_HASH 可从配置中移除，已不再读取。

## 六、Windows 备份与恢复

源文件、XLS、工时和变更记录均在 PostgreSQL 命名 volume 中。
代码位于 D: 并不意味着数据库保存在项目文件夹；Docker Desktop 管理容器磁盘与 volume。
**只复制项目目录不能迁移数据库**。不用 NTFS 文件夹直接替代 PostgreSQL 的数据目录；通过数据库备份迁移。

PowerShell 下以 pg_dump 文件 + docker cp 备份，避免 Windows PowerShell 5.1 文本重定向破坏二进制 dump：

```powershell
Set-Location 'D:\works\github\bestar-work-hours'
New-Item -ItemType Directory -Force -Path '.\backups' | Out-Null
$BackupFile = Join-Path (Get-Location).Path ('backups\work-hours-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump')
docker compose --env-file .env -p bestar-work-hours exec -T database pg_dump -U bestar -d work_hours -Fc -f /tmp/work-hours-backup.dump
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed' }
docker compose --env-file .env -p bestar-work-hours cp database:/tmp/work-hours-backup.dump $BackupFile
if ($LASTEXITCODE -ne 0) { throw 'Copying backup to Windows failed' }
Get-Item -LiteralPath $BackupFile
```

`/tmp/...` 是 Linux **容器内部**路径；宿主保存的是 Windows `$BackupFile` 路径。
备份含员工数据，按公司规则保存到受控的异机位置；同电脑磁盘副本不能覆盖整机故障。

恢复演练先进入一个全新库，不覆盖当前业务库：

```powershell
$BackupFile = 'D:\works\github\bestar-work-hours\backups\替换为实际备份文件.dump'
$RestoreDatabase = 'work_hours_restore_' + (Get-Date -Format 'yyyyMMddHHmmss')
docker compose --env-file .env -p bestar-work-hours cp $BackupFile database:/tmp/restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Copying restore file failed' }
docker compose --env-file .env -p bestar-work-hours exec -T database createdb -U bestar $RestoreDatabase
if ($LASTEXITCODE -ne 0) { throw 'Creating an empty restore database failed' }
docker compose --env-file .env -p bestar-work-hours exec -T database pg_restore -U bestar -d $RestoreDatabase --exit-on-error /tmp/restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Database restore failed' }
```

核对原件 SHA、行、revision、审计和导出。新电脑灾难恢复时：配置相同项目代码及匹配的凭据，先仅启动 database，恢复到空 work_hours 库，核对后再 up 完整应用。
恢复 v1 备份后先运行 migrate 升级到 v2，再启动完整应用。已做过合成备份恢复演练；详细本机证据不随仓库分发。

## 七、Windows 常见问题

| 现象 | 处理 |
| --- | --- |
| docker 无法识别 / credential helper not found | 重开 PowerShell，或补 Docker resources\bin 到当前 PATH |
| Cannot connect / named pipe 错误 | 打开 Docker Desktop，等待引擎启动；检查当前 context 与 Linux 容器模式 |
| no matching manifest for windows | 切回 Linux containers，本项目不是 Windows 容器镜像 |
| 3000/3100 端口已占用 | 用 `Get-NetTCPConnection -LocalPort 3000,3100 -ErrorAction SilentlyContinue` 检查；不要关闭未知进程；正式配置同时改 WEB_PORT 和 APP_ORIGIN |
| 上传或修改 403 | 浏览器 URL 的协议/主机/端口须与 APP_ORIGIN 一致；环境变化后重新 up |
| 同事无法访问，本机正常 | 检查 WEB_BIND_ADDRESS、实际内网 IP、防火墙和网络配置文件；不要开放数据库/API |
| 数据库 password authentication failed | 核对既有 volume 对应的原密码；不要删 volume 来重置密码 |
| 电脑重启后页面打不开 | Windows 登录后确认 Docker Desktop 已启动，再 `up -d`；检查休眠策略 |
| 上传同一文件失败 | SHA-256 判重属于正常行为；已删除批次的原件也不会重新导入 |


## Vercel：两个项目

需要用户自己的 Vercel 及托管 PostgreSQL 环境。本项目不会自动创建收费资源或发布。
使用同区域数据库；连接串包含提供方要求的 TLS 参数（例如 sslmode=require）。生产与 Preview 用不同数据库及密钥。

| 设置 | Python API 项目 | Web 项目 |
| --- | --- | --- |
| Root Directory | apps/engine | apps/web |
| 框架 | FastAPI | Next.js |
| 运行时 | Python 3.14（pyproject/.python-version） | Node 24.x（package.json engines） |
| 入口/构建 | app.py 的 app；框架自动构建 | npm ci / npm run build，默认输出设置 |
| 配置 | vercel.json，maxDuration 60 | Route Handler maxDuration 60 |
| 持久数据 | 外部 PostgreSQL | 不写本地文件 |

API 环境变量：DATABASE_URL、API_SERVICE_SECRET（至少 32 字符）、APP_ENV=production。
Web 环境变量：API_ORIGIN（API 项目的固定 HTTPS origin，无尾随 `/`）、相同 API_SERVICE_SECRET、APP_ORIGIN（Web 的实际 HTTPS origin）。
这些秘密不使用 NEXT_PUBLIC_ 前缀。无需配置经理账号、密码哈希或会话。

部署顺序：

1. 准备 PostgreSQL，记录备份与恢复方式。Preview 不连接生产数据。
2. 在受控本地终端以 API 环境变量配置一个忽略的 `.env.api`，使用同一 API 镜像执行一次迁移：
   `docker run --rm --env-file .env.api bestar-work-hours-api python -m bestar_work_hours.service.manage migrate`。
   不要在日志/命令行输出数据库连接密码。
3. 部署 API；检查 /health，数据库须 up。不要把迁移放入请求或模块导入。
4. 配置并部署 Web。API_ORIGIN 指向该环境的 API。
5. 若 API 开启 Vercel Deployment Protection，由项目所有者创建官方 Automation Bypass Secret，放入 Web 的 API_DEPLOYMENT_BYPASS_SECRET；服务端用 `x-vercel-protection-bypass` 请求头发送。服务之间的 API_SERVICE_SECRET 检查仍生效，浏览器使用不需要应用账号。
6. 核对 Web 直接访问、上传/去重、解析、修正/删除、免登录 Excel 下载、跨站修改拒绝、冷启动后历史保留、跨版本回滚。

Python/FastAPI 的入口与运行时依据 [FastAPI 官方部署说明](https://vercel.com/docs/frameworks/backend/fastapi) 和 [Python Runtime](https://vercel.com/docs/functions/runtimes/python)。
受保护 API 的服务间访问依据 [Protection Bypass for Automation](https://vercel.com/docs/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation)。

## 平台容量与失败处理

Vercel 文档的函数请求/响应体上限是 4.5 MB，见 [Function limits](https://vercel.com/docs/functions/limitations)。
应用统一限定原始 XLS ≤3 MB、multipart 实际请求 ≤3.2 MB、JSON/导出 ≤4 MB；本地也采用相同规则。
XLS 首表最多 2048 行、64 列；工资模板最多 16 名员工。超过限制返回明确错误，不产出不完整工资表。
解析/生成同步完成，Web 上游超时 55 秒；目标环境的最大真实样例性能尚待测量。
生成失败保留历史，过期 revision 拒绝发布/下载。请求超时后先刷新列表和生成历史，再决定是否重试。
PostgreSQL 使用短连接 NullPool；云数据库可按供应商支持情况使用连接池 URL。

## 开发与自动化

宿主 Python 的项目 .venv 已得到用户授权，步骤见 apps/engine/README.md；不安装全局依赖。

```powershell
docker compose -p bestar-hours-test -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from engine-tests
```

测试栈数据库使用 tmpfs 和明确合成凭据，与业务环境隔离；52 项测试包含 PostgreSQL 与 SQLite。
Web：在 apps/web 执行 npm ci、npm run typecheck、npm run build。
浏览器测试需要本机 Edge（Windows）或 Playwright Chromium（其他系统），执行 `npm --prefix apps/web run test:e2e`。
默认 TEST_WEB_URL=http://localhost:3100，可设为当前实际部署地址；只读取已有记录与下载文件，不上传、修正、删除或生成业务数据。
没有导入记录时仅检查空页面、免登录、主题和语言；真实业务验收需另行核对真实文件。
默认关闭 screenshot、video 和 trace，避免把员工明细写入测试产物；下载内容只在内存检查。
所有运行数据、dump、截图、trace 和环境文件均被 Git 忽略；真实数据不得改为测试 fixture 或提交到 GitHub。
