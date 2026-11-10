# 一键更新功能实施任务 — AI 执行提示词

## 项目背景

你正在为 **Outlook Email Plus**（一个基于 Flask 的 Outlook 邮箱管理 Web 应用）实施一键更新功能的改进。该项目使用 Docker 部署，当前已具备基础的版本检测和 Watchtower 热更新功能。

**项目路径**: `E:\hushaokang\Data-code\EnsoAi\outlookEmail\dev`
**分支**: `dev`
**技术栈**: Python 3.11 + Flask + Gunicorn + SQLite + Docker + Watchtower
**当前版本**: v1.12.0

---

## 当前代码架构

### 后端结构
```
outlook_web/
├── __init__.py              # APP_VERSION = "1.12.0"
├── app.py                   # Flask create_app()
├── controllers/
│   ├── system.py            # api_version_check(), api_trigger_update(), api_test_watchtower()
│   └── settings.py          # api_get_settings(), api_update_settings(), api_test_telegram_proxy()
├── routes/
│   ├── system.py            # /api/system/version-check, /api/system/trigger-update, /api/system/test-watchtower
│   └── settings.py          # /api/settings, /api/settings/test-telegram-proxy
├── services/
│   └── telegram_push.py     # Telegram 推送（支持代理）
├── repositories/
│   └── settings.py          # settings_repo.get_setting(), set_setting()
├── security/
│   └── crypto.py            # encrypt_data(), decrypt_data(), is_encrypted()
└── db.py                    # SQLite 数据库
```

### 前端结构
```
templates/index.html         # 单页应用，设置页有 Tab（基础/临时邮箱/API安全/自动化）
static/js/main.js            # 所有前端逻辑
```

### Docker 配置
```
Dockerfile                   # Python 3.11-slim + Gunicorn
docker-compose.yml           # app + watchtower 两个服务
```

---

## 已完成的工作

1. **版本检测 API**: `GET /api/system/version-check` — 对比 GitHub latest release，10 分钟缓存
2. **一键更新 API**: `POST /api/system/trigger-update` — 调用 Watchtower HTTP API
3. **Watchtower 测试 API**: `POST /api/system/test-watchtower` — 测试连通性
4. **设置页面 Watchtower 配置**: URL + Token（加密存储），支持测试连通性
5. **GitHub 仓库地址修复**: `hshaokang/outlookemail-plus` → `ZeroPointSix/outlookEmailPlus`
6. **热更新验证通过**: v1.12.0 → v1.12.1 成功更新

---

## 实施进度

### ✅ Phase 1: BUG 修复 — 已完成 (Commit: 91a8f35)

#### ✅ 任务 1: 修复 Watchtower Token 为空时启动失败的问题

**实施方案**:
1. ✅ `.env.example` 中添加 `WATCHTOWER_HTTP_API_TOKEN` 模板和生成命令
2. ✅ `docker-compose.yml` 中为 `WATCHTOWER_HTTP_API_TOKEN` 提供默认 fallback token
3. ✅ 设置页面 Watchtower 配置区域增加首次配置引导文案
4. ✅ `api_deployment_info()` 检测 Watchtower 连通性，前端显示警告

**已修改文件**:
- `.env.example`: 添加 Token 配置说明和生成命令
- `docker-compose.yml`: 默认值 `default-watchtower-token-please-change-in-production`
- `templates/index.html`: 首次配置引导文案

#### ✅ 任务 2: 修复浏览器缓存旧 JS 文件的问题

**实施方案**:
1. ✅ `outlook_web/app.py` 中添加 `@app.after_request` hook
2. ✅ 带版本号参数的静态文件长期缓存 (1年 + immutable)
3. ✅ 不带版本号的短期缓存 (1小时 + must-revalidate)

**已修改文件**:
- `outlook_web/app.py`: 新增 `set_static_cache_control()` 函数

---

### ✅ Phase 2: UI 提示优化 — 已完成 (Commit: 91a8f35)

#### ✅ 任务 3: 镜像标签/构建模式检测与提示

**实施方案**:
1. ✅ 后端新增 API `GET /api/system/deployment-info`
2. ✅ 检测: 镜像名/本地构建/固定标签/Watchtower 连通性
3. ✅ 返回警告信息和 `can_auto_update` 状态
4. ✅ 前端 `templates/index.html` 添加 `deploymentWarnings` 占位符
5. ✅ 前端 `static/js/main.js` 调用 API 并渲染警告列表（支持中/英切换重渲染）

**已修改文件**:
- `outlook_web/controllers/system.py`: 新增 `api_deployment_info()` (177 行)
- `outlook_web/routes/system.py`: 注册路由
- `templates/index.html`: 添加警告容器
- `static/js/main.js`: 新增 `loadDeploymentInfo()` / `renderDeploymentWarnings()` 并在 `loadSettings()` 中触发

---

### ✅ Phase 3: 内置 Docker API 自更新 — 已完成 (Commit: 91a8f35)

#### ✅ 任务 4: 实现内置 Docker API 自更新功能

**实施方案**:
1. ✅ 新建 `outlook_web/services/docker_update.py` (591 行)
   - 完整的 12 步自更新流程
   - 安全检查 (开关/docker.sock/白名单)
   - 回滚机制 (失败时保留旧容器)

2. ✅ 修改 `outlook_web/controllers/system.py`
   - `api_trigger_update()` 支持 `method` 参数 (watchtower / docker_api)
   - 分离 `_trigger_watchtower_update()` 和 `_trigger_docker_api_update()`
   - 审计日志记录

3. ✅ 修改 `outlook_web/controllers/settings.py`
   - GET: 返回 `update_method` 配置
   - PUT: 保存 `update_method` 配置并验证

4. ✅ 修改 `static/js/main.js`
   - `loadSettings()`: 加载 `update_method`
   - `saveSettings()`: 保存 `update_method`
   - `triggerUpdate()`: 自动识别更新方式,调整超时时间 (Docker API 120s vs Watchtower 10s)
   - 完善错误提示 (区分两种模式)

5. ✅ 修改 `templates/index.html`
   - 更新方式选择 (Radio: Watchtower / Docker API)
   - Docker API 安全警告面板
   - 动态切换配置区域显示/隐藏

6. ✅ 修改 `docker-compose.yml`
   - 添加 docker.sock 挂载说明 (默认注释)
   - 添加 `DOCKER_SELF_UPDATE_ALLOW` 环境变量

7. ✅ 修改 `requirements.txt`
   - 添加 `docker>=6.0.0` 依赖

**已修改/新增文件**:
- 新增: `outlook_web/services/docker_update.py` (591 行，经代码验证 2026-04-07)
- 修改: `outlook_web/controllers/system.py` (新增 150+ 行)
- 修改: `outlook_web/controllers/settings.py` (新增 20 行)
- 修改: `static/js/main.js` (重构 triggerUpdate, 新增 70+ 行)
- 修改: `templates/index.html` (新增更新方式 UI, 70+ 行)
- 修改: `docker-compose.yml`, `.env.example`, `requirements.txt`

---

## 代码验证记录 (2026-04-07)

> 以下通过实际代码验证确认文档描述与代码一致

| 验证项 | 文档描述 | 代码实际 | 状态 |
|--------|----------|----------|------|
| `docker_update.py` 行数 | 839 行 | **591 行** | ⚠️ 已修正 |
| `api_version_check()` | 版本检测 + 10 分钟缓存 | ✅ 存在于 system.py:353 | ✅ |
| `api_trigger_update()` | 支持 method 参数 | ✅ 存在于 system.py:402 | ✅ |
| `_trigger_watchtower_update()` | Watchtower 更新 | ✅ 存在于 system.py:438 | ✅ |
| `_trigger_docker_api_update()` | Docker API 更新 | ✅ 存在于 system.py:500 | ✅ |
| `api_deployment_info()` | 部署信息检测 | ✅ 存在于 system.py:561 | ✅ |
| `api_test_watchtower()` | Watchtower 连通性测试 | ✅ 存在于 system.py:732 | ✅ |
| 路由注册 | 4 个新端点 | ✅ routes/system.py 全部注册 | ✅ |
| `update_method` 设置 | GET/PUT 支持 | ✅ settings.py:351/1013 | ✅ |
| 静态文件缓存控制 | Cache-Control 头 | ✅ app.py:124 `set_static_cache_control()` | ✅ |
| GitHub 仓库地址 | ZeroPointSix/outlookEmailPlus | ✅ system.py:368 | ✅ |
| Docker compose 配置 | Token 默认值 + docker.sock | ✅ docker-compose.yml | ✅ |
| .env.example | Watchtower + Docker API 模板 | ✅ .env.example 完整 | ✅ |

---

### ✅ Phase 4: A2 方案 — 按需 helper job 容器（dev 分支，Commit: 待提交）

**背景**：Phase 3 的 Docker API 自更新实测发现"自杀问题"——容器在内部 stop 自己后，后台线程也被杀死，后续 create/rename/cleanup 步骤无法完成。

**方案**：A2（按需 helper job 容器）

- app 容器通过 Docker API 临时创建 updater 容器
- updater 容器执行完整更新流程（pull→create→stop旧→start新→healthcheck→rename→cleanup）
- updater 容器退出后 auto_remove 自动清理
- 用户视角：平时 1 容器，更新时短暂 2 容器，最终恢复 1 容器

**关键改动**：

| 文件 | 改动 |
|------|------|
| `outlook_web/services/docker_update_helper.py` | **新增**（69 行）— updater 容器入口模块 |
| `outlook_web/services/docker_update.py` | 新增 `get_container_info()` / `spawn_update_helper_container()`；增强 `validate_image_name()` 支持 digest/registry port；增强 volumes 解析支持 named volume；`self_update()` 新增 `target_container_id` 参数；步骤顺序调整为"先 stop 旧再 start 新"；失败时恢复旧容器 |
| `outlook_web/controllers/system.py` | `healthz()` 新增 `boot_id`+`version`；`_trigger_docker_api_update()` 改为调用 `spawn_update_helper_container()`；`api_deployment_info()` 增加上下文感知警告 |
| `static/js/main.js` | `waitForRestart()` boot_id 检测；Docker API 超时 180s；部署警告渲染 |
| `templates/index.html` | `#deploymentWarnings` 容器 |
| `tests/test_error_and_trace.py` | 适配 healthz 新字段 |
| `tests/test_smoke_contract.py` | 适配 healthz 新字段 |
| `docker-compose.docker-api-test.yml` | **新增** Docker API 测试 compose |

---

### ✅ Phase 5: 安全策略强化（策略A — 禁止本地构建镜像触发更新）

**时间**：2026-04-07

**目标**：彻底禁止本地构建镜像触发 Docker API 更新，仅允许官方远程镜像更新。

**实施内容**：

1. **镜像白名单收紧**：
   - 移除 `outlook-email-plus`（无 namespace）白名单项
   - 仅保留 `guangshanshui/outlook-email-plus` 官方镜像前缀

2. **新增本地构建检测**：
   - `validate_image_for_update()`：镜像白名单 + RepoDigests 检测双重校验
   - `_looks_like_local_image_ref()`：基于 namespace 的启发式本地镜像检测
   - `_has_repo_digests()`：通过 Docker API 检查镜像 RepoDigests（本地 build 镜像为空）

3. **API 层前置校验**：
   - `_trigger_docker_api_update()` 在触发阶段提前获取容器镜像并校验
   - 校验失败返回 403/500，避免等到 spawn updater 内部才失败

4. **部署信息展示优化**：
   - `api_deployment_info()` 不再依赖 `DOCKER_SELF_UPDATE_ALLOW` 环境变量
   - 只要 docker.sock 可用就通过 Docker API 获取真实镜像名

**修改文件**：

| 文件 | 改动 |
|------|------|
| `outlook_web/services/docker_update.py` | 白名单收紧；新增 `validate_image_for_update()`, `_looks_like_local_image_ref()`, `_has_repo_digests()`；`get_container_info()` 获取 RepoDigests；`spawn_update_helper_container()` 和 `self_update()` 调用新校验函数；**Bug修复**：`_looks_like_local_image_ref()` 改为 namespace 白名单判断 |
| `outlook_web/controllers/system.py` | `_trigger_docker_api_update()` API 层镜像校验；`api_deployment_info()` 获取镜像名逻辑优化 |
| `docker-compose.docker-api-test.yml` | 镜像名改为 `guangshanshui/outlook-email-plus:latest`（形成负向用例） |
| `docs/DEV/manual-acceptance-checklist.md` | **新增**：人工验收清单（4 个测试用例 + 验收标准 + 快速测试脚本） |

**验收状态**：待 Docker 容器内实际测试

**补充：验收前代码层发现并修复的一个误判点**：
- 旧逻辑用 substring 检测 `"test"` 会误判 `"latest"`（包含 `test` 子串）
- 已改为：优先通过 Docker API 获取镜像 `RepoDigests` 判断；tag 判断改为精确匹配（避免误判）

---

## 参考文件清单

实施时需要参考/修改的文件：

| 文件 | 用途 |
|------|------|
| `outlook_web/__init__.py` | 版本号 |
| `outlook_web/controllers/system.py` | 版本检测、更新触发、Watchtower 测试、部署信息、healthz |
| `outlook_web/controllers/settings.py` | 设置读写（含 Watchtower 配置） |
| `outlook_web/routes/system.py` | 路由注册 |
| `outlook_web/services/docker_update.py` | Docker API 自更新服务（975 行） |
| `outlook_web/services/docker_update_helper.py` | updater 容器入口（69 行） |
| `outlook_web/repositories/settings.py` | 设置数据库操作 |
| `outlook_web/security/crypto.py` | 加密/解密/脱敏 |
| `outlook_web/app.py` | 静态文件缓存控制 |
| `static/js/main.js` | 前端逻辑（triggerUpdate, waitForRestart, testWatchtower, loadDeploymentInfo 等） |
| `templates/index.html` | UI（版本更新 Banner, Watchtower 配置, deploymentWarnings） |
| `docker-compose.yml` | Docker 编排配置（本地开发） |
| `docker-compose.docker-api-test.yml` | Docker API 模式测试配置 |
| `docker-compose.hotupdate-test.yml` | Watchtower 模式测试配置 |
| `requirements.txt` | Python 依赖（含 docker>=6.0.0） |
| `Dockerfile` | 镜像构建 |
| `.env.example` | 环境变量模板 |

---

## 注意事项

1. **不要修改 `main` 分支**，只在 `dev` 分支上开发
2. **遵循现有代码风格**: 中文注释、类型注解、错误处理模式
3. **敏感信息处理**: Token 使用 `encrypt_data()` 加密存储，GET 时脱敏返回
4. **向后兼容**: 环境变量配置作为数据库配置的 fallback
5. **测试**: 每个阶段完成后提供验证方法
6. **A2 模式关键约束**: app 容器必须挂载 docker.sock + 设置 DOCKER_SELF_UPDATE_ALLOW=true
