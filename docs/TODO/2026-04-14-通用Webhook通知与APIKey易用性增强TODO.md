# TODO: 通用 Webhook 通知与 API Key 易用性增强

> 创建日期：2026-04-14  
> 更新日期：2026-04-15（v1.13 — 回填 v1.17.0 标签镜像补齐完成）  
> 基于 PRD v1.5：`docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`（路径待补）  
> 基于 FD v1.11：`docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`  
> 基于 TD v1.11：`docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`  
> 基于 TDD v1.10：`docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`  
> 联调检查：`docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强-PRD-FD-TD-TDD联调检查.md`  
> AI 执行提示词：按会话实时提供（不落库文档）  
> 目标版本：v1.17.x（待排期）

> 会话约束（必须保持）：
> 1. `webhook-test` 仅使用已保存配置（先保存，再测试）  
> 2. API Key 随机值由前端原生算法生成（`crypto.getRandomValues`），不新增后端生成接口  
> 3. 不引入新第三方库或新架构层

---

## 任务概览

| 阶段 | 任务数 | 状态 |
|---|---:|---|
| Phase 0: 文档与口径冻结 | 3 | ✅ 已完成 |
| Phase 1: Settings Repository/Controller 扩展 | 6 | ✅ 已完成（代码+测试验证） |
| Phase 2: Webhook Service 与路由接入 | 6 | ✅ 已完成（代码+测试验证） |
| Phase 3: 通知分发链路接入 webhook channel | 5 | ✅ 已完成（代码+测试验证） |
| Phase 4: 前端页面与交互实现 | 7 | ✅ 已完成（代码+契约测试验证） |
| Phase 5: i18n 与前端契约补齐 | 3 | ✅ 已完成（契约测试验证） |
| Phase 6: 测试实现与回归 | 8 | 🟨 自动化已完成，人工冒烟待补 |
| Phase 7: 联调收尾与发布准备 | 5 | 🟨 文档回填进行中 |

### 本次执行回填（2026-04-15）

- 已完成自动化验证（Webhook/API Key 相关 + 分批全量回归）：
  - `python -m unittest tests.test_settings_webhook -v` → **9 passed**
  - `python -m unittest tests.test_webhook_push -v` → **7 passed**
  - `python -m unittest tests.test_notification_dispatch -v` → **25 passed**
  - `python -m unittest tests.test_settings_webhook_frontend_contract -v` → **4 passed**
  - `python -m unittest tests.test_v190_frontend_contract -v` → **18 passed**
  - `python -m unittest tests.test_settings_tab_refactor_backend -v` → **14 passed**
  - `python -m unittest tests.test_settings_tab_refactor_frontend -v` → **12 passed**
  - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → **Ran 346, OK**
  - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → **Ran 89, OK**
  - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → **Ran 231, OK (skipped=7)**
  - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → **Ran 492, OK**
- 汇总：分批回归合计 **1158 tests（自动化）通过，skipped=7（既有跳过项）**。
- 备注：本轮未执行 UI 人工冒烟（Phase 6.8 仍待补齐）。

### 本次执行回填（2026-04-15，第二轮）

- 分批全量回归再次执行：
  - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → **Ran 346, OK**
  - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → **Ran 89, OK**
  - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → **Ran 231, OK (skipped=7)**
  - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → **Ran 492, OK**
- 汇总：本轮分批回归合计 **1158 tests 通过，skipped=7**（与前一轮一致）。
- Docker 构建前置检查：
  - `docker version` / `docker build` 当前失败：本机未连接 Docker Engine（`//./pipe/dockerDesktopLinuxEngine` 不存在）。
  - 结论：代码回归已确认通过，待 Docker Desktop/Engine 启动后再执行镜像构建验证。

### 本次执行回填（2026-04-15，Docker 环境恢复后）

- Docker 引擎恢复可用：`docker version` 返回 Client/Server `28.3.2`
- 镜像构建：
  - `docker build -t "outlook-email-plus:local-regression-20260415" .` → 成功
- 容器验证：
  - 首次 `-p 5055:5000` 失败（端口占用/权限）
  - 清理失败容器后改用 `-p 18080:5000` 启动成功
  - 容器 `oep-regression-20260415` 状态 `healthy`
  - `GET http://127.0.0.1:18080/healthz` → `200`

### 本次执行回填（2026-04-15，Docker 运行态复核）

- `docker ps`：`oep-regression-20260415` 处于 `Up ... (healthy)`
- `docker inspect`：`Health=healthy`
- `docker images`：`outlook-email-plus:local-regression-20260415` 存在（image id `acc8f048a48e`）

### 本次执行回填（2026-04-15，main 分支启动 + 全量回归）

- 分支合并：`Buggithubissue` 已本地 fast-forward 合并到 `main`（未 push）。
- 按会话要求先停旧服务：停止 5000 端口进程 PID `37460`。
- 在 `main` 后台启动：`python web_outlook_app.py`（PID `41184`）。
- 健康检查：`GET http://127.0.0.1:5000/healthz` → `200`。
- 分批全量回归（main）：
  - `test_[a-f]*` → **Ran 346, OK**
  - `test_[g-l]*` → **Ran 89, OK**
  - `test_[m-r]*` → **Ran 231, OK (skipped=7)**
  - `test_[s-z]*` → **Ran 492, OK**
- 汇总：**1158 tests 通过，skipped=7**。

### 本次执行回填（2026-04-15，发布续推前核对）

- 主发布工作树：`E:/hushaokang/Data-code/outlookEmail`，分支状态 `main...origin/main [ahead 3]`。
- 当前未提交改动为 `v1.17.0` 版本口径文件：
  - `CHANGELOG.md`
  - `README.md`
  - `README.en.md`
  - `docs/DEVLOG.md`
  - `outlook_web/__init__.py`
  - `tests/test_version_update.py`
- 对照工作树：`Buggithubissue` 当前 `ahead 1` 且干净，不含本轮未提交版本改动。
- 运行态复核：5000 端口无监听，`/healthz` 连接失败（当前本地服务未运行）。

### 本次执行回填（2026-04-15，发布后质量门禁修复）

- 已确认推送后流水线状态：
  - `Create GitHub Release`（tag）成功；
  - `Code Quality`（main）失败；
  - `Build and Push Docker Image`（main/tag）失败（quality-gate 阻断）；
  - `Python Tests`（main）成功；`SonarCloud Scan`（main）成功。
- 本地修复执行：
  - `python -m black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
  - `python -m isort --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
  - `python -m black --check ...` + `python -m isort --check-only ...` 均通过。
- 修复后分批全量回归：
  - `test_[a-f]*` → **Ran 346, OK**
  - `test_[g-l]*` → **Ran 89, OK**
  - `test_[m-r]*` → **Ran 231, OK (skipped=7)**
  - `test_[s-z]*` → **Ran 492, OK**
- 汇总：**1158 tests 通过，skipped=7**。

### 本次执行回填（2026-04-15，发布确认与监控收口）

- 发布确认：`v1.17.0` 已在 GitHub Release 正式发布并显示为 `Latest`。
- 发布页：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`
- 修复提交链路（`f3d2208`）最终状态：
  - `Code Quality` ✅
  - `Python Tests` ✅
  - `Build and Push Docker Image` ✅
  - `SonarCloud Scan` ✅
- 文档收口提交链路（`05871bf`）附加监控：`SonarCloud Scan`（run `24450875717`）✅

### 本次执行回填（2026-04-15，双仓镜像核对）

- 核对仓库：GHCR + DockerHub。
- `main`：两仓存在且 digest 一致：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`。
- `latest`：两仓存在且 digest 一致：`sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`。
- `v1.17.0`：两仓当前均不存在（not found），与 tag 工作流初次失败事实一致。

### 本次执行回填（2026-04-15，重打标签补镜像）

- 已按会话决策执行 `v1.17.0` 重打标签到 `f3d2208`：
  - 删除远端旧 tag；
  - 推送新 tag；
  - 触发新一轮 tag workflows。
- 当前进展：
  - `Create GitHub Release`（run `24451870230`）✅
  - `Build and Push Docker Image`（run `24451870226`）⏳（queued/in_progress）
- 待办：Docker workflow 完成后复核 GHCR + DockerHub 的 `v1.17.0` 标签是否补齐。

### 本次执行回填（2026-04-15，重打标签补镜像完成）

- `Build and Push Docker Image`（run `24451870226`）已成功完成。
- 双仓 `v1.17.0` 标签已补齐，digest 一致：
  - `sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
- 结论：Release + 双仓镜像链路全部闭环。

---

## Phase 0: 文档与口径冻结

### Task 0.1 冻结关键口径
- [x] 再次确认三条硬约束：
  - [x] `webhook-test` 仅已保存配置
  - [x] API Key 前端算法生成
  - [x] 不引入新库/新架构

### Task 0.2 文档引用完整性检查
- [x] PRD/FD/TD/TDD/TODO 互相引用完整。
- [x] 联调检查文档路径在 TODO 头部已声明。

### Task 0.3 执行边界声明
- [x] 确认本期不做平台模板（企业微信/飞书/钉钉专属格式）。
- [x] 确认本期不做每账号独立 webhook URL。

---

## Phase 1: Settings Repository/Controller 扩展

### Task 1.1 `settings.py` 新增 webhook getter
**文件**：`outlook_web/repositories/settings.py`

- [x] `get_webhook_notification_enabled() -> bool`
- [x] `get_webhook_notification_url() -> str`
- [x] `get_webhook_notification_token() -> str`（enc 自动解密）
- [x] `get_webhook_notification_token_masked(...) -> str`

### Task 1.2 `api_get_settings()` 返回 webhook 字段
**文件**：`outlook_web/controllers/settings.py`

- [x] `safe_settings` 补 `webhook_notification_enabled`
- [x] `safe_settings` 补 `webhook_notification_url`
- [x] `safe_settings` 补 `webhook_notification_token`（脱敏）

### Task 1.3 `api_update_settings()` 接收与校验 webhook 字段
**文件**：`outlook_web/controllers/settings.py`

- [x] 解析 `webhook_notification_enabled`
- [x] 解析 `webhook_notification_url`
- [x] 解析 `webhook_notification_token`
- [x] 校验：enabled=true 时 URL 必填
- [x] 校验：URL 仅允许 `http/https`
- [x] token 存储遵循 masked placeholder 语义（未变更/清空/加密保存）

### Task 1.4 错误码补充
**文件**：`outlook_web/errors.py`

- [x] `WEBHOOK_URL_REQUIRED`
- [x] `WEBHOOK_URL_INVALID`
- [x] `WEBHOOK_NOT_CONFIGURED`
- [x] `WEBHOOK_TEST_SEND_FAILED`
- [x] `WEBHOOK_SEND_FAILED`

### Task 1.5 审计日志补充
**文件**：`outlook_web/controllers/settings.py`

- [x] 保存 webhook 配置时补 audit（不记录 token 明文）
- [x] 测试 webhook 时补 audit（成功/失败语义）

### Task 1.6 Phase 1 验证
- [x] `GET /api/settings` 能读到 webhook 字段。
- [x] `PUT /api/settings` 能正确处理 URL 校验与 token 脱敏语义。

---

## Phase 2: Webhook Service 与路由接入

### Task 2.1 新建 webhook service
**文件**：`outlook_web/services/webhook_push.py`

- [x] 定义 `WebhookPushError`
- [x] 定义 URL 校验函数（仅 http/https）
- [x] 定义 `build_business_webhook_text(...)`

### Task 2.2 实现发送函数（含重试）
**文件**：`outlook_web/services/webhook_push.py`

- [x] `send_webhook_message(...)`
- [x] timeout 固定 10s
- [x] 失败后重试 1 次
- [x] 2xx 视为成功
- [x] token 为空时不发送 `X-Webhook-Token`

### Task 2.3 实现测试发送函数
**文件**：`outlook_web/services/webhook_push.py`

- [x] `send_test_webhook_message()`
- [x] 读取已保存 webhook 配置
- [x] 配置缺失时抛 `WEBHOOK_NOT_CONFIGURED`

### Task 2.4 settings 路由增加 webhook-test
**文件**：`outlook_web/routes/settings.py`

- [x] 新增 `/api/settings/webhook-test` → `api_test_webhook`

### Task 2.5 settings controller 增加 `api_test_webhook`
**文件**：`outlook_web/controllers/settings.py`

- [x] 调用 webhook service 测试发送
- [x] 统一返回 success/error 结构
- [x] 仅使用已保存配置（忽略请求体配置）

### Task 2.6 Phase 2 验证
- [x] webhook-test 成功场景返回 success=true。
- [x] webhook-test 失败场景返回稳定错误码与 message。

---

## Phase 3: 通知分发链路接入 webhook channel

### Task 3.1 通道常量与限额
**文件**：`outlook_web/services/notification_dispatch.py`

- [x] 新增 `CHANNEL_WEBHOOK = "webhook"`
- [x] 新增 `MAX_WEBHOOK_NOTIFICATIONS_PER_JOB`

### Task 3.2 runtime 配置解析
**文件**：`outlook_web/services/notification_dispatch.py`

- [x] 新增 `_get_webhook_runtime_config()`
- [x] enabled + url 可用时返回 runtime，否则返回 None

### Task 3.3 active channel 构建接入 webhook
**文件**：`outlook_web/services/notification_dispatch.py`

- [x] `_build_active_channels_for_source()` 加入 webhook
- [x] 继续沿用 `_is_source_notification_enabled(source)` 规则

### Task 3.4 webhook 发送函数接入
**文件**：`outlook_web/services/notification_dispatch.py`

- [x] `send_business_webhook_notification(...)`
- [x] 调用 `webhook_push.send_webhook_message(...)`

### Task 3.5 Phase 3 验证
- [x] Email/Telegram/Webhook 并存时各通道行为正常。
- [x] 去重与游标机制对 webhook 生效。

---

## Phase 4: 前端页面与交互实现

### Task 4.1 自动化 Tab 增加 Webhook 卡片
**文件**：`templates/index.html`

- [x] 新增 `webhookNotificationEnabled`
- [x] 新增 `webhookNotificationUrl`
- [x] 新增 `webhookNotificationToken`
- [x] 新增 `btnTestWebhookNotification`

### Task 4.2 settings 加载逻辑扩展
**文件**：`static/js/main.js`

- [x] `loadSettings()` 回填 webhook 字段

### Task 4.3 保存逻辑扩展
**文件**：`static/js/main.js`

- [x] `saveSettings()` payload 增加 webhook 字段
- [x] token masked placeholder 逻辑与现有敏感字段一致

### Task 4.4 auto-save 扩展
**文件**：`static/js/main.js`

- [x] `autoSaveSettings('automation')` 增加 webhook 字段同步

### Task 4.5 新增测试按钮函数
**文件**：`static/js/main.js`

- [x] `testWebhookNotification()`
- [x] 成功/失败提示与按钮状态恢复逻辑完整

### Task 4.6 新增 API Key 随机生成函数
**文件**：`static/js/main.js`

- [x] `generateExternalApiKey()`
- [x] 使用 `crypto.getRandomValues` 生成 64 位 URL-safe
- [x] 已有值时覆盖确认
- [x] 不自动保存

### Task 4.7 新增 API Key 复制函数
**文件**：`static/js/main.js`

- [x] `copyExternalApiKey()`
- [x] 成功/失败 toast

---

## Phase 5: i18n 与前端契约补齐

### Task 5.1 i18n 词条补齐
**文件**：`static/js/i18n.js`

- [x] Webhook 卡片标题与字段文案
- [x] 测试成功/失败文案
- [x] 随机生成/覆盖确认文案

### Task 5.2 前端契约测试补齐
**文件**：`tests/test_settings_webhook_frontend_contract.py`（建议新增）

- [x] index.html 字段 ID 断言
- [x] main.js 函数/关键字符串断言
- [x] i18n 词条断言

### Task 5.3 现有前端契约回归
**文件**：`tests/test_v190_frontend_contract.py`

- [x] 确认新增内容不破坏现有断言

---

## Phase 6: 测试实现与回归

### Task 6.1 Settings/API 自动化测试
- [x] 新建并通过 `tests/test_settings_webhook.py`

### Task 6.2 Webhook Service 自动化测试
- [x] 新建并通过 `tests/test_webhook_push.py`

### Task 6.3 Dispatch 增量测试
- [x] 在 `tests/test_notification_dispatch.py` 增加 webhook 场景

### Task 6.4 前端契约测试
- [x] `tests/test_settings_webhook_frontend_contract.py` 通过

### Task 6.5 核心受影响回归
- [x] `tests/test_notification_dispatch.py`
- [x] `tests/test_v190_frontend_contract.py`

### Task 6.6 Settings 回归
- [x] `tests/test_settings_tab_refactor_backend.py`
- [x] `tests/test_settings_tab_refactor_frontend.py`

### Task 6.7 全量回归（按仓库策略分批）
- [x] `python -m unittest discover -s tests -v`（已分批执行）

### Task 6.8 人工冒烟
- [ ] Webhook 卡片配置/测试（成功链路已完成，失败链路待补）
- [ ] API Key 随机/复制/覆盖确认/保存语义

#### 6.8.1 webhook.site 联调执行清单（当前会话）
- [x] 在 `https://webhook.site/` 生成临时 URL（用户侧已提供）
- [x] 打开 `设置 -> 自动化 Tab -> Webhook 通知` 并保存 URL/token（token 可选）
- [x] 点击“测试 Webhook”（仅使用已保存配置）
- [x] 在 webhook.site 核对 `POST` / `Content-Type` / body / `X-Webhook-Token`（当前 token 为空，符合“不发送该头”）
- [ ] 用 Beeceptor/Pipedream 返回 `5xx` 验证失败提示与重试

> 无自建 webhook 接收端时，优先使用 `webhook.site` 验证成功链路；
> 失败链路用 Beeceptor/Pipedream 等返回 5xx 的平台验证重试与错误提示。
> 推荐配置入口：`设置 -> 自动化 Tab -> Webhook 通知`；先保存，再点击测试。
> 本地联调需要服务运行时，仅允许后台独立进程启动（`Start-Process`/独立进程），禁止前台阻塞命令。

---

## Phase 7: 联调收尾与发布准备

### Task 7.1 文档回填
- [x] 在 TDD 中回填执行结果。
- [x] 在 TODO 中勾选完成项并记录关键命令。

### Task 7.2 变更说明
- [x] 更新 `CHANGELOG.md` 对应版本段落（功能 + 测试结论）。

### Task 7.3 兼容性复核
- [x] 确认未引入新依赖。
- [x] 确认未做 schema 升级。

### Task 7.4 风险复核
- [x] 下游 JSON-only 场景保留已知风险说明。

### Task 7.5 交付就绪确认
- [x] PRD/FD/TD/TDD/TODO/WORKSPACE 六链路一致。

---

## 建议执行命令（开发阶段）

```bash
# 新增测试
python -m unittest tests.test_settings_webhook -v
python -m unittest tests.test_webhook_push -v
python -m unittest tests.test_settings_webhook_frontend_contract -v

# 核心回归
python -m unittest tests.test_notification_dispatch -v
python -m unittest tests.test_v190_frontend_contract -v

# 全量
python -m unittest discover -s tests -v
```

---

## 通过标准

1. 关键能力（Webhook 配置/测试/分发 + API Key 随机/复制）全部达标。
2. 既有 Email/Telegram/Settings 相关功能回归无新增失败。
3. 与会话 PRD 约束保持一致：
   - `webhook-test` 仅已保存配置；
   - API Key 前端算法生成；
   - 不引入新库/新架构。
