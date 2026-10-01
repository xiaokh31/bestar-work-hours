# GitHub 操作指南（Windows PowerShell）

本仓库用于同步 Bestar 工时应用的代码和可分发文档。数据库、员工考勤文件、生成结果与本机环境不通过 GitHub 同步。应用本身不需要登录；这里的 GitHub 登录只用于开发者推送代码。

当前项目仓库：[xiaokh31/bestar-work-hours](https://github.com/xiaokh31/bestar-work-hours)，同步分支为 `main`。

## 1. 哪些文件提交，哪些忽略

| 类别 | 处理 | 原因 |
| --- | --- | --- |
| apps/ 下的源码、自动化测试、品牌资源 | 提交 | 构建与维护应用所必需；测试使用合成数据 |
| Dockerfile、compose*.yaml、vercel.json、scripts/ | 提交 | 本地与 Vercel 共用部署/验证实现 |
| package-lock.json、requirements*.lock | 提交 | 锁定依赖，支持复现 |
| .env.example 等示例 | 提交 | 只有占位符；正式密钥由各环境自行配置 |
| README、LICENSE、NOTICE、各应用 README/LICENSE/NOTICE | 提交 | 使用说明与许可证归属 |
| docs/DEPLOYMENT.md、REQUIREMENTS.md、ENGINE-MIGRATION.md、GITHUB-GUIDE.md | 提交 | 可供其他电脑直接使用的操作和技术说明 |
| AGENTS.md、HANDOFF.md | 忽略，仅本地保留 | 当前电脑的代理约定、路径与会话交接 |
| docs/SOURCE-MAP.md、IMPLEMENTATION-PLAN.md、verification/ | 忽略，仅本地保留 | 旧项目内部索引、开发过程与本机实测记录 |
| docs/private/、*.local.md、*.private.md | 忽略 | 私有说明及本机笔记的固定位置/命名 |
| .env、.env.smoke、其他真实 .env.*、.secrets/ | 忽略 | 数据库密码与服务密钥 |
| storage/、backups/、samples/private/ | 忽略 | 运行文件、员工记录、备份、临时脚本及截图 |
| *.xls、*.xlsx、*.xlsm、*.csv | 默认忽略 | 防止员工表格散落在其他目录后误传 |
| 正式脱敏模板 bestar-wage-template-v1.xls 及同名 JSON | 必须提交 | .gitignore 只为这一份 XLS 设置例外；缺少模板不能生成工时表 |
| *.dump、*.sql、*.bak、*.db、*.sqlite*、私钥文件 | 忽略 | 数据库与凭据不进入代码仓库 |
| node_modules/、.venv/、.next/、build/、dist/、缓存和测试输出 | 忽略 | 可重建产物，不随 Git 分发 |

不要忽略整个 docs/，也不要删除 LICENSE/NOTICE 或依赖锁文件。`.gitattributes` 统一文本换行，并保持正式 XLS 模板和 JSON manifest 的原始字节，避免模板哈希因 Windows 换行变化而失效。

`.gitignore` 对已经跟踪的文件不追溯生效。若发现已跟踪的本地文件，例如 HANDOFF.md，可用 `git rm --cached -- HANDOFF.md` 仅从索引移除，磁盘文件保留；随后提交规则和移除记录。此操作不会清除既有提交中的敏感内容；如果密钥已推送，应先撤销/更换密钥，再处理历史。参见 [GitHub 忽略文件说明](https://docs.github.com/en/get-started/git-basics/ignoring-files?platform=windows)。

## 2. 确认工具和 GitHub 身份

在 Windows PowerShell 中进入你实际的项目目录：

```powershell
Set-Location 'D:\works\github\bestar-work-hours'
git --version
gh --version
gh auth status
git config --get user.name
git config --get user.email
```

若 gh 已登录且账号正确，无需重新登录。未登录时使用 `gh auth login --hostname github.com --web`，按终端提示在浏览器授权；不要把 Token、密码或 SSH 私钥写进仓库 URL、文档或聊天。HTTPS Git 需要时可运行 `gh auth setup-git` 接入现有 CLI 登录；SSH 则使用已配置的密钥。参见 [GitHub CLI 登录说明](https://cli.github.com/manual/gh_auth_login)。

user.name 和 user.email 是提交署名，不是 GitHub 密码。只在未配置或需要改变署名时设置本仓库的值：

```powershell
git config user.name '你的提交署名'
git config user.email '你在 GitHub 验证的邮箱或 GitHub 提供的 noreply 邮箱'
```

## 3. 首次本地提交

当前目录已初始化时跳过 git init；以下命令不会重复创建仓库：

```powershell
if (-not (Test-Path -LiteralPath '.git')) { git init -b main }
git status --short --untracked-files=all
git check-ignore -v .env.smoke HANDOFF.md docs/verification/no-login-2026-10-01.md storage/example.xls
git add .
git diff --cached --stat
git diff --cached --name-only
git diff --cached --check
```

逐项查看暂存清单：不应出现本地文档、真实 .env、员工表格、运行数据或依赖目录；应包含 .env.example、正式模板与 JSON、源码、锁文件和部署说明。`check-ignore` 输出匹配规则意味着正确忽略；对正式模板或 .env.example 执行它时应无匹配（退出码 1），这表示它们允许提交。

确认后创建首次提交；如果本地已经有提交，不重复创建：

```powershell
git log -1 --oneline
# 仅当尚无首次提交时执行：
git commit -m 'Initial standalone work-hours application'
```

每条命令若报错，先处理错误再继续，不把失败当作已同步。`git add` 只暂存，`git commit` 只提交到本机；二者都不会上传 GitHub。

## 4. 关联你的远程仓库并推送

使用你提供或在 GitHub 创建的独立工时仓库地址。公司项目通常使用 Private；不要误用旧系统仓库。新建空仓库时不要预先添加 README、许可证或 .gitignore，以便接收本项目首个提交。参见 [将本地项目加入 GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

本项目已确定的远程地址如下；同步其他项目时再替换：

```powershell
$RemoteUrl = 'https://github.com/xiaokh31/bestar-work-hours.git'
git remote -v
git ls-remote $RemoteUrl
```

`ls-remote` 成功且没有任何引用，表示仓库为空；仓库不存在/权限错误则先修复地址或登录。若远程已有分支/提交，先核对内容并按下一节处理。

没有 origin 时添加；如果已经存在，先确认它正确，不要重复添加或盲目覆盖：

```powershell
git remote add origin $RemoteUrl
git remote -v
git push -u origin main
```

现有 origin 确实指错且已确认目标后才用 `git remote set-url origin $RemoteUrl`。命令说明见 [管理远程仓库](https://docs.github.com/en/get-started/git-basics/managing-remote-repositories)。

验证同步结果：

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
git status --short --branch
```

本地 HEAD 与 origin/main 的提交号相同、没有未提交改动，并且上游指向 origin/main，才表示当前代码已同步。GitHub 页面应能看到源码和操作指南，同时没有被忽略的本地文件。

### 远程已经有内容

先执行 `git fetch origin`，用 `git log --oneline --graph --decorate --all -20` 检查两边历史和默认分支。若只是同一历史中的新提交，可在本地干净时 `git pull --rebase origin main` 后推送。若两边历史独立或远程是另一个项目，先保留并整合原内容；不要用 `--force` 覆盖。存在冲突时检查具体文件，不自动选择整边内容。

## 5. 日常同步与另一台电脑

日常修改后，查看和提交真正需要的变化：

```powershell
git status --short
git diff --stat
git add .
git diff --cached --name-only
git diff --cached --check
git commit -m 'Describe the work-hours change'
git pull --rebase origin main
git push
```

有远程新增内容时先整合；没有变化时不需要空提交。上传失败不影响本机已有提交，修好网络/认证后重试即可。

另一台公司 Windows 电脑使用 `git clone https://github.com/xiaokh31/bestar-work-hours.git` 获取代码，随后按 [部署手册](DEPLOYMENT.md) 自建 `.env` 并启动 Docker。**克隆代码不会带回数据库中的工时记录**；需要迁移已有业务数据时，使用部署手册中的 PostgreSQL 备份与恢复流程。

GitHub 同步不等于 Vercel 发布，也不会备份 Docker volume。若另行将仓库接入自动部署，推送行为可能触发该平台配置的构建；发布配置单独管理。
