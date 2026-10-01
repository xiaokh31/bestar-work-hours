# Bestar Work Hours Engine

独立 Python 3.14 工时引擎与窄 FastAPI 服务。保留 wage-attendance-v2、BIFF 编辑器、正式脱敏模板。
业务部署见根目录 docs/DEPLOYMENT.md。

## 验证

项目根目录优先执行 Docker + PostgreSQL 测试：

```powershell
docker compose -p bestar-hours-test -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from engine-tests
```

用户已授权本项目 `.venv`；在 apps/engine 下使用现有 Python 3.14：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes --only-binary=:all: -r requirements-build.lock -r requirements-test.lock
.venv/Scripts/python -m pip wheel --no-build-isolation --no-deps --wheel-dir dist .
.venv/Scripts/python -m pip install --force-reinstall --no-deps dist/bestar_work_hours_engine-0.1.0-py3-none-any.whl
.venv/Scripts/python -I -m pytest -q --import-mode=importlib tests
```

POSIX 路径为 `.venv/bin/python`。修改源码后须重建并安装 wheel，避免验证旧安装。
未设置 TEST_DATABASE_URL 时测试使用临时 SQLite；生产及 Vercel 只接受 PostgreSQL。
数据库集成测试仅允许名为 synthetic_test 的隔离数据库，每例使用独立随机 schema。

## 开发 CLI

```powershell
python -I -m bestar_work_hours inspect-template
python -I -m bestar_work_hours parse samples/private/attendance.xls --output storage/parsed.json
python -I -m bestar_work_hours generate samples/private/attendance.xls --output-dir storage/new-run
```

输出父目录须存在，JSON 文件及生成目录须全新。CLI 保留原始证据及生成 manifest，但不处理应用修正/删除；应用必须通过 API 导出。
纯引擎不依赖数据库或旧系统。HTTP 服务需 PostgreSQL 和内部服务连接密钥；不需要应用账户，通过 `python -m bestar_work_hours.service.manage migrate` 显式初始化。
`hash-password` 子命令交互读取两次密码，只输出 PBKDF2 哈希。

测试均为合成数据，不能代替真实样例、Excel 打开/打印预览或真实 Vercel 验收。
