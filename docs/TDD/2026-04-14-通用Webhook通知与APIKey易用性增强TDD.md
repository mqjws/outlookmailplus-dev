# TDD: 通用 Webhook 通知与 API Key 易用性增强

- 文档版本: v1.10
- 创建日期: 2026-04-14
- 更新日期: 2026-04-15（v1.10 — 回填重打标签补镜像完成）
- 文档类型: 测试设计文档（TDD）
- 关联 PRD: `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`（路径待补）
- 关联 FD: `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
- 关联 TD: `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
- 关联 TODO: `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
- 目标版本: v1.17.x（待排期）

---

## 1. 文档目标

本 TDD 仅关注本需求的测试设计，不重复业务叙述。

本次测试要证明四件事：

1. Webhook 配置可以被正确保存/读取（含 token 脱敏与加密语义）。
2. Webhook 测试接口遵循“仅已保存配置”规则，返回稳定成功/失败语义。
3. 通知分发新增 `webhook` 通道后，不破坏 Email/Telegram 既有行为。
4. API Key 随机生成/复制交互满足安全与保存语义（不自动保存）。

---

## 2. 测试分层策略

| 层级 | 目标 | 建议测试文件 | 重点 |
|---|---|---|---|
| A. Settings/API | webhook 字段读写/校验/测试接口 | `tests/test_settings_webhook.py` | URL 校验、token 脱敏、webhook-test 口径 |
| B. Service | webhook 发送与重试策略 | `tests/test_webhook_push.py` | 2xx 判定、10s 超时、失败重试1次、header规则 |
| C. Dispatch | 新通道接入不破坏旧通道 | `tests/test_notification_dispatch.py`（增量） | active channel 构建、去重、并行通道共存 |
| D. Frontend 契约 | 页面字段与交互函数存在 | `tests/test_v190_frontend_contract.py` 或新增 `tests/test_settings_webhook_frontend_contract.py` | Webhook 卡片、按钮、main.js hooks、i18n 词条 |
| E. 手工冒烟 | UI 真实交互与粘贴复制体验 | 手工清单 | 随机/复制/覆盖确认/保存前后差异 |

执行顺序建议：A → B → C → D → E。

---

## 3. 测试原则

1. **不访问真实外部 webhook**：网络请求统一 mock。
2. **先保存再测试**：`/api/settings/webhook-test` 不接受临时配置覆盖。
3. **兼容不回退**：新增 webhook 后，Email/Telegram 现有用例必须全绿。
4. **不引入新库验证点**：随机 Key 仅验证前端使用原生能力和输出约束。

---

## 4. 关键测试矩阵

### 4.1 Webhook 配置矩阵

| 场景 | 入参 | 预期 |
|---|---|---|
| W-CFG-01 | `enabled=false` + 空 URL | 保存成功 |
| W-CFG-02 | `enabled=true` + 空 URL | 保存失败，`WEBHOOK_URL_REQUIRED` |
| W-CFG-03 | `enabled=true` + `https://...` | 保存成功 |
| W-CFG-04 | `enabled=true` + `http://...` | 保存成功 |
| W-CFG-05 | `enabled=true` + `ftp://...` | 保存失败，`WEBHOOK_URL_INVALID` |
| W-CFG-06 | token 非空 | 加密保存、读取脱敏 |
| W-CFG-07 | token 传脱敏占位符 | 视为未变更 |
| W-CFG-08 | token 传空字符串 | 清空 token |

### 4.2 Webhook 测试接口矩阵

| 场景 | 已保存配置 | 预期 |
|---|---|---|
| W-TEST-01 | 未启用或 URL 空 | 失败，`WEBHOOK_NOT_CONFIGURED` |
| W-TEST-02 | URL 正常 + 返回 200 | success=true |
| W-TEST-03 | 返回 500 后重试成功 | success=true（重试生效） |
| W-TEST-04 | 返回 500 且重试失败 | `WEBHOOK_TEST_SEND_FAILED` |
| W-TEST-05 | token 为空 | 请求头不含 `X-Webhook-Token` |
| W-TEST-06 | token 非空 | 请求头含 `X-Webhook-Token` |

### 4.3 Dispatch 通道矩阵

| 场景 | 通道开关 | 预期 |
|---|---|---|
| D-01 | 仅 Email 开 | 行为与历史一致 |
| D-02 | 仅 Telegram 开 | 行为与历史一致 |
| D-03 | 仅 Webhook 开 | 可发送 webhook |
| D-04 | Email + Webhook | 双通道都发送（按各自去重） |
| D-05 | Telegram + Webhook | 双通道都发送 |
| D-06 | 三通道全开 | 三通道并存不互斥 |

### 4.4 API Key 交互矩阵（前端）

| 场景 | 操作 | 预期 |
|---|---|---|
| K-01 | 点击随机生成（空输入） | 生成 64 位 URL-safe |
| K-02 | 点击随机生成（已有值） | 弹覆盖确认 |
| K-03 | 覆盖确认=取消 | 保持原值 |
| K-04 | 覆盖确认=确认 | 生成新值 |
| K-05 | 点击复制 | 复制当前输入框值 |
| K-06 | 生成后不点保存刷新页面 | 值不持久化 |

---

## 5. A 层：Settings/API 测试设计

建议新建：`tests/test_settings_webhook.py`

关键用例：

1. `test_get_settings_contains_webhook_fields`
2. `test_update_settings_webhook_enabled_requires_url`
3. `test_update_settings_webhook_rejects_invalid_scheme`
4. `test_update_settings_webhook_accepts_http_and_https`
5. `test_update_settings_webhook_token_encrypted_and_masked`
6. `test_update_settings_webhook_token_placeholder_keeps_existing`
7. `test_update_settings_webhook_token_empty_clears_value`
8. `test_webhook_test_uses_saved_settings_only`
9. `test_webhook_test_returns_not_configured_when_missing`

断言重点：

- `_json_error` code/message/status 与约定一致。
- token 不以明文回传。

---

## 6. B 层：Webhook Service 测试设计

建议新建：`tests/test_webhook_push.py`

关键用例：

1. `test_send_webhook_message_success_on_2xx`
2. `test_send_webhook_message_retries_once_then_success`
3. `test_send_webhook_message_retries_once_then_fail`
4. `test_send_webhook_message_timeout_uses_10_seconds`
5. `test_send_webhook_message_without_token_omits_header`
6. `test_send_webhook_message_with_token_sets_header`
7. `test_build_business_webhook_text_contains_minimum_fields`

mock 策略：

- patch `requests.post`
- 校验调用次数（1 或 2）与 timeout=10。

---

## 7. C 层：通知分发增量测试设计

文件：`tests/test_notification_dispatch.py`（增量添加）

关键增量用例：

1. `test_build_active_channels_includes_webhook_when_enabled`
2. `test_build_active_channels_excludes_webhook_when_disabled`
3. `test_run_notification_dispatch_job_email_and_webhook_coexist`
4. `test_run_notification_dispatch_job_telegram_and_webhook_coexist`
5. `test_run_notification_dispatch_job_three_channels_coexist`

断言重点：

- webhook channel 只在配置可用时出现。
- 旧用例不需改行为断言。

---

## 8. D 层：前端契约测试设计

建议新建：`tests/test_settings_webhook_frontend_contract.py`

检查点：

1. `templates/index.html` 包含以下 ID：
   - `webhookNotificationEnabled`
   - `webhookNotificationUrl`
   - `webhookNotificationToken`
   - `btnTestWebhookNotification`
2. `static/js/main.js` 包含：
   - webhook 字段加载逻辑
   - webhook 字段保存逻辑（含 automation auto-save）
   - `testWebhookNotification()` 函数
   - `generateExternalApiKey()` / `copyExternalApiKey()` 函数
3. `static/js/i18n.js` 包含新增文案词条。

---

## 9. E 层：手工冒烟清单

1. 打开设置页自动化 Tab，确认 Webhook 卡片显示。
2. 输入 URL + token，保存后重新打开设置，token 脱敏显示。
3. 点击测试按钮：
   - 配置正确时提示成功；
   - 停掉下游接收端时提示失败原因。
4. API 安全 Tab：
   - 点击随机生成生成 64 位；
   - 有值时出现覆盖确认；
   - 点击复制成功；
   - 不保存刷新后值回退，保存后持久化。

### 9.1 无本地接收端时的手工测试替代

若当前环境没有可用 webhook 接收服务，手工冒烟可采用在线调试平台：

1. 使用 `https://webhook.site/` 临时 URL 做成功链路验证；
2. 使用 Beeceptor/Pipedream 等可控响应平台做失败链路验证（返回 5xx）；
3. 核对请求头/请求体：
   - `Content-Type: text/plain; charset=utf-8`
   - 有 token 时带 `X-Webhook-Token`，无 token 时不带。

补充执行顺序（按本会话约束）：

1. 先在设置页保存 webhook URL/token；
2. 再点击 `测试 Webhook`（仅使用已保存配置）；
3. 如需本地服务配合联调，仅使用后台独立进程启动（`Start-Process`/独立进程），不使用前台阻塞命令。

### 9.2 webhook.site 逐步联调指引（会话实操版）

1. 打开 `https://webhook.site/` 并复制临时 URL；
2. 回到本系统 `设置 -> 自动化 Tab -> Webhook 通知`：
   - 勾选启用；
   - 填写 URL；
   - 可选填写 token；
   - 点击“保存设置”；
3. 点击“测试 Webhook”；
4. 回到 webhook.site 页面确认：
   - 收到请求；
   - method=`POST`；
   - `Content-Type: text/plain; charset=utf-8`；
   - 配置 token 时包含 `X-Webhook-Token`；
5. （可选）将 URL 换成 Beeceptor/Pipedream 的 `500` 响应端点，验证失败提示与重试行为。

---

## 10. 回归清单

1. 既有 Email 测试接口不受影响。
2. 既有 Telegram 测试接口不受影响。
3. 既有 settings 保存（其他字段）不受影响。
4. `tests/test_notification_dispatch.py` 原用例保持通过。

---

## 11. 建议执行命令

```bash
# 新增相关
python -m unittest tests.test_settings_webhook -v
python -m unittest tests.test_webhook_push -v
python -m unittest tests.test_settings_webhook_frontend_contract -v

# 受影响核心回归
python -m unittest tests.test_notification_dispatch -v
python -m unittest tests.test_v190_frontend_contract -v

# 最终全量（按仓库习惯可分批）
python -m unittest discover -s tests -v
```

---

## 12. 通过标准

1. 关键矩阵（配置/测试接口/通道并存/前端交互）全部通过。
2. Webhook 新增用例通过，且 Email/Telegram 回归无新增失败。
3. API Key 交互满足“安全随机 + 不自动保存”要求。

---

## 13. 执行回填（2026-04-15）

### 13.1 定向测试结果

- `python -m unittest tests.test_settings_webhook -v` → **Ran 9, OK**
- `python -m unittest tests.test_webhook_push -v` → **Ran 7, OK**
- `python -m unittest tests.test_notification_dispatch -v` → **Ran 25, OK**
- `python -m unittest tests.test_settings_webhook_frontend_contract -v` → **Ran 4, OK**
- `python -m unittest tests.test_v190_frontend_contract -v` → **Ran 18, OK**
- `python -m unittest tests.test_settings_tab_refactor_backend -v` → **Ran 14, OK**
- `python -m unittest tests.test_settings_tab_refactor_frontend -v` → **Ran 12, OK**

### 13.2 分批回归结果（规避单命令超时）

- `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → **Ran 346, OK**
- `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → **Ran 89, OK**
- `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → **Ran 231, OK (skipped=7)**
- `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → **Ran 492, OK**

汇总：分批自动化回归合计 **1158 tests 通过，skipped=7（既有跳过项）**。

### 13.3 结论

1. Webhook 配置/测试/分发链路与 API Key 随机/复制契约在自动化层面验证通过。
2. 新增能力未破坏既有 Settings/Notification/Frontend 关键契约。
3. 仍建议补做手工冒烟（UI 交互体验、复制权限与浏览器兼容）后再进入发布收尾。

### 13.4 会话手工联调进展回填（2026-04-15）

- 用户已提供 webhook.site 临时 URL：`https://webhook.site/00766721-eaaf-4a3b-9821-60575812158c`。
- 本地服务已按后台独立进程启动并通过健康检查：
  - 启动方式：`Start-Process`（独立进程）
  - 进程 PID：`37460`
  - 健康检查：`GET /healthz` 返回 `200`
- 运行日志可见已执行 Webhook 测试链路：
  - 首次未配置返回 `WEBHOOK_NOT_CONFIGURED`（400）
  - 保存配置后 `POST /api/settings/webhook-test` 返回 `200`
- 已通过 webhook.site API 核对成功请求明细：
  - method=`POST`
  - `Content-Type: text/plain; charset=utf-8`
  - body 为业务文本模板字段
  - 当前 token 为空，header 中未出现 `X-Webhook-Token`（符合预期）
- 仍待补失败链路（Beeceptor/Pipedream 返回 5xx）以完成手工冒烟收口。

### 13.5 第二轮分批全量回归（2026-04-15）

- `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → **Ran 346, OK**
- `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → **Ran 89, OK**
- `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → **Ran 231, OK (skipped=7)**
- `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → **Ran 492, OK**
- 汇总：第二轮分批回归再次得到 **1158 tests 通过，skipped=7**。

### 13.6 Docker 构建与容器验证（2026-04-15）

- 已执行：
  - `docker version --format "Client={{.Client.Version}} Server={{.Server.Version}}"`
  - `docker build -t "outlook-email-plus:local-regression-20260415" .`
  - `docker run -d --name "oep-regression-20260415" -p 18080:5000 "outlook-email-plus:local-regression-20260415"`
  - `GET http://127.0.0.1:18080/healthz`
- 结果：
  - Docker Client/Server 均可用（28.3.2）；
  - 镜像构建成功（image id `acc8f048a48e`）；
  - 容器运行成功并处于 `healthy`；
  - `/healthz` 返回 `200`。
- 备注：首次尝试映射 `5055` 端口失败（端口占用/权限），已清理失败容器并改用 `18080` 成功运行。

### 13.7 Docker 运行态核对（2026-04-15）

- 容器：`oep-regression-20260415`
- 镜像：`outlook-email-plus:local-regression-20260415`
- 端口：`18080->5000`
- 状态：`Up ... (healthy)`
- `docker inspect`：`Health=healthy`

### 13.8 main 分支分批全量回归复核（2026-04-15）

- 分支与运行态：
  - `Buggithubissue` 已本地 fast-forward 合并到 `main`（未 push）；
  - 按会话要求在 `main` 重启后台服务，当前 PID `41184`；
  - `GET /healthz` 返回 `200`（`boot_id=1776240270869-41184`）。
- main 再次执行分批全量回归：
  - `python -m unittest discover -s tests -v -p "test_[a-f]*.py"` → **Ran 346, OK**
  - `python -m unittest discover -s tests -v -p "test_[g-l]*.py"` → **Ran 89, OK**
  - `python -m unittest discover -s tests -v -p "test_[m-r]*.py"` → **Ran 231, OK (skipped=7)**
  - `python -m unittest discover -s tests -v -p "test_[s-z]*.py"` → **Ran 492, OK**
- 汇总：**1158 tests 通过，skipped=7**（与前序两轮结果一致）。

### 13.9 发布续推前现场核对（2026-04-15）

- 工作树确认：发布工作树为 `main`（`E:/hushaokang/Data-code/outlookEmail`），状态 `ahead 3` 且存在 `v1.17.0` 版本口径未提交改动。
- 交叉对照：`Buggithubissue` 工作树仅 `ahead 1` 且干净，不含本轮版本改动。
- 运行态确认：`5000` 端口无监听，`/healthz` 连接失败，说明当前无本地服务驻留进程。
- 结论：测试结论不变（自动化回归仍以 1158/7 为准），发布续推需在 main 工作树继续执行版本提交与发布链路。

### 13.10 发布后质量门禁修复回归（2026-04-15）

- 背景：`v1.17.0` 初次推送后 `Code Quality` 失败，`Build and Push Docker Image`（main/tag）被 quality-gate 阻断。
- 修复动作：
  - 执行 `black` 全仓格式化；
  - 执行 `isort --profile black`；
  - 执行 `black --check` + `isort --check-only`，结果均通过。
- 回归复核：
  - `test_[a-f]*` → **Ran 346, OK**
  - `test_[g-l]*` → **Ran 89, OK**
  - `test_[m-r]*` → **Ran 231, OK (skipped=7)**
  - `test_[s-z]*` → **Ran 492, OK**
- 汇总：**1158 tests 通过，skipped=7**（修复前后结果一致）。

### 13.11 v1.17.0 发布与链路收口确认（2026-04-15）

- 发布状态：`v1.17.0` Release 已发布并标记为 `Latest`。
- 发布页面：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`。
- 发布后修复链路（提交 `f3d2208`）已验证四项主工作流全绿：
  - `Code Quality` / `Python Tests` / `Build and Push Docker Image` / `SonarCloud Scan` 均为 success。
- 会话监控收口提交（`05871bf`）触发的 `SonarCloud Scan` 亦为 success，说明当前主干状态稳定。

### 13.12 双仓镜像标签可用性核对（2026-04-15）

- 核对命令：`docker buildx imagetools inspect`（GHCR 与 DockerHub 双仓）。
- 结果：
  - `main`：两仓均存在，digest 一致（`sha256:8aef74...9218`）；
  - `latest`：两仓均存在，digest 一致（`sha256:8aef74...9218`）；
  - `v1.17.0`：两仓均 `not found`。
- 结论：双仓主线镜像同步正常，版本标签镜像仍待补齐。

### 13.13 重打 v1.17.0 标签补镜像进展（2026-04-15）

- 标签调整：`v1.17.0` 已重打到 `f3d2208`（CI 全绿提交）。
- 工作流状态：
  - `Create GitHub Release`（run `24451870230`）✅ success；
  - `Build and Push Docker Image`（run `24451870226`）⏳ queued/in_progress。
- 备注：待 Docker workflow 完成后再进行 GHCR/DockerHub 的 `v1.17.0` 标签存在性复核。

### 13.14 重打标签补镜像完成复核（2026-04-15）

- workflow：`Build and Push Docker Image`（run `24451870226`）已 success。
- 镜像标签复核：
  - GHCR `v1.17.0` 存在，digest=`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
  - DockerHub `v1.17.0` 存在，digest=`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
- 结论：`v1.17.0` 双仓版本标签镜像已补齐且一致。
