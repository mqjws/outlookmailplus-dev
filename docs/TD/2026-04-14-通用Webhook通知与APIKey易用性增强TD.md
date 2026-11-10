# TD: 通用 Webhook 通知与 API Key 易用性增强

- 文档版本: v1.11
- 创建日期: 2026-04-14
- 更新日期: 2026-04-15（v1.11 — 回填 v1.17.0 标签镜像补齐完成）
- 文档类型: 技术细节设计
- 关联 PRD: `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`（路径待补）
- 关联 FD: `docs/FD/2026-04-14-通用Webhook通知与APIKey易用性增强FD.md`
- 关联 TDD: `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
- 关联 TODO: `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
- 目标版本: v1.17.x（待排期）

---

## 0. 当前状态与范围

当前处于文档阶段，本 TD 仅定义实现细节与接口契约。

本期范围：

1. 通知体系新增通用 Webhook 通道（全局配置）。
2. API 安全区新增 External API Key「随机生成 + 复制」能力。

---

## 1. 技术目标

1. **不改通知主架构**：在现有 `notification_dispatch` 上扩展 channel，不另起独立调度体系。
2. **不引入新第三方依赖**：
   - 后端继续使用现有 `requests`；
   - 前端随机 Key 使用浏览器原生 `crypto.getRandomValues`。
3. **测试口径稳定**：Webhook 测试接口只读取“已保存配置”，不接受临时覆盖参数。
4. **保存语义不变**：API Key 随机/复制仅操作输入框，必须手动保存才生效。

---

## 2. 现状基线（代码锚点）

### 2.1 设置路由与控制器

- 路由：`outlook_web/routes/settings.py`
  - 已有 `email-test` / `telegram-test` / `verification-ai-test`。
- 控制器：`outlook_web/controllers/settings.py`
  - `api_get_settings()` / `api_update_settings()` 已具备敏感字段脱敏与加密保存模式。

### 2.2 通知分发

- `outlook_web/services/notification_dispatch.py`
  - 当前 channel：`email`、`telegram`。
  - 已有统一游标与投递日志机制（按 channel 去重）。

### 2.3 前端设置页

- `templates/index.html`
  - 自动化 Tab 已有 Email、Telegram 卡片及测试按钮。
- `static/js/main.js`
  - 已有设置加载、保存、自动保存（按 Tab）与测试接口调用逻辑。

### 2.4 i18n

- `static/js/i18n.js` 已覆盖大量设置页文案，新增词条按现有 exactMap 机制扩充。

---

## 3. 核心技术决策

### 3.1 Schema 变更策略

**结论：不升级 DB schema，不修改 `DB_SCHEMA_VERSION`。**

理由：Webhook 配置走现有 `settings` 表 key-value 存储即可。

### 3.2 依赖与架构策略

**结论：不引入新库、不新建“独立基础架构层”。**

1. 后端 HTTP 调用继续使用已存在的 `requests`。
2. 前端随机 Key 使用浏览器原生 `crypto.getRandomValues` 直接算法生成。
3. 不新增消息队列/任务表/外部中间件。

### 3.3 Webhook 测试策略

**结论：`/api/settings/webhook-test` 仅使用已保存配置。**

与现有 Email/Telegram 测试口径保持一致（先保存，再测试）。

### 3.4 Key 生成策略

**结论：前端本地生成 64 位 URL-safe 字符串。**

- 字符集：`A-Z a-z 0-9 - _`
- 算法：`crypto.getRandomValues(Uint8Array)` 取模映射
- 不新增后端「生成 Key」接口

---

## 4. 后端设计

### 4.1 Settings Repository 扩展

文件：`outlook_web/repositories/settings.py`

新增 getter（建议）：

```python
def get_webhook_notification_enabled() -> bool
def get_webhook_notification_url() -> str
def get_webhook_notification_token() -> str          # 支持 enc: 自动解密
def get_webhook_notification_token_masked(...) -> str
```

读取规则：

1. `enabled`: `"true"/"false"` → bool
2. `url`: trim 后返回
3. `token`: 与 `telegram_bot_token/external_api_key` 同口径（解密失败返回空）

建议 settings key：

- `webhook_notification_enabled`
- `webhook_notification_url`
- `webhook_notification_token`

### 4.2 Settings API 扩展

文件：`outlook_web/controllers/settings.py`

#### 4.2.1 `api_get_settings()`

返回新增字段（safe_settings）：

```json
{
  "webhook_notification_enabled": false,
  "webhook_notification_url": "",
  "webhook_notification_token": "****abcd"
}
```

说明：token 仅返回脱敏值。

#### 4.2.2 `api_update_settings()`

支持新增入参：

- `webhook_notification_enabled`
- `webhook_notification_url`
- `webhook_notification_token`

校验规则：

1. `enabled=true` 时，`url` 必填。
2. `url` 必须为 `http://` 或 `https://`。
3. token 处理与现有敏感字段一致：
   - 输入脱敏占位符（`****`开头）视为未变更；
   - 空字符串表示清空；
   - 其余值加密保存。

建议新增错误码：

- `WEBHOOK_URL_REQUIRED`
- `WEBHOOK_URL_INVALID`

### 4.3 新增测试接口

#### 4.3.1 路由

文件：`outlook_web/routes/settings.py`

新增：

```python
bp.add_url_rule(
    "/api/settings/webhook-test",
    view_func=settings_controller.api_test_webhook,
    methods=["POST"],
)
```

#### 4.3.2 控制器

文件：`outlook_web/controllers/settings.py`

新增：

```python
@login_required
def api_test_webhook() -> Any:
    # 仅用已保存配置发送测试消息
```

行为：

1. 读取已保存 webhook 配置；
2. 缺配置时返回配置类错误；
3. 调用 webhook service 发送测试消息；
4. 成功返回 `success=true`；失败返回可读错误信息；
5. 写审计日志（不记录 token 明文）。

### 4.4 Webhook Service（新增）

建议新增文件：`outlook_web/services/webhook_push.py`

职责：

1. URL 校验（仅 http/https）。
2. 文本模板组装。
3. Webhook 发送（10s 超时 + 失败重试 1 次）。
4. 统一异常结构（供 settings test 与 dispatch 复用）。

建议结构：

```python
class WebhookPushError(Exception):
    code: str
    message: str
    message_en: str
    status: int
    details: Any

def send_webhook_message(*, url: str, token: str, text_body: str, timeout_sec: int = 10, retry: int = 1) -> None
def send_test_webhook_message() -> dict[str, Any]
def build_business_webhook_text(source: dict, message: dict) -> str
```

发送策略：

1. 先发一次；
2. 失败（异常或非 2xx）立即重试一次；
3. 重试后仍失败则抛错。

Header 规则：

- `Content-Type: text/plain; charset=utf-8`
- `X-Webhook-Token` 仅在 token 非空时附带

### 4.5 通知分发接入

文件：`outlook_web/services/notification_dispatch.py`

新增/调整：

1. 新增常量：

```python
CHANNEL_WEBHOOK = "webhook"
MAX_WEBHOOK_NOTIFICATIONS_PER_JOB = 50
```

2. 新增 runtime 读取：

```python
def _get_webhook_runtime_config() -> dict[str, str] | None
```

3. `_build_active_channels_for_source()` 追加 webhook channel：
   - 沿用 `_is_source_notification_enabled(source)` 参与规则；
   - 普通邮箱和临时邮箱都可触发（与现有通知口径一致）。

4. 新增发送函数：

```python
def send_business_webhook_notification(source: dict, message: dict, *, url: str, token: str) -> None
```

5. 发送失败处理复用现有 `_process_messages_for_channel()`：
   - 按 channel=`webhook` 写 delivery log，参与去重。

### 4.6 错误码映射扩展

文件：`outlook_web/errors.py`

建议补充中英文映射：

- `WEBHOOK_URL_REQUIRED`
- `WEBHOOK_URL_INVALID`
- `WEBHOOK_NOT_CONFIGURED`
- `WEBHOOK_TEST_SEND_FAILED`
- `WEBHOOK_SEND_FAILED`

---

## 5. 前端设计

### 5.1 HTML（自动化 Tab）

文件：`templates/index.html`

在 Email/Telegram 卡片同区域新增 Webhook 卡片，建议字段 ID：

| 字段 | ID |
|---|---|
| 启用 Webhook 通知 | `webhookNotificationEnabled` |
| Webhook URL | `webhookNotificationUrl` |
| Webhook Token | `webhookNotificationToken` |
| 测试按钮 | `btnTestWebhookNotification` |

### 5.2 main.js（设置加载/保存）

文件：`static/js/main.js`

#### 5.2.1 loadSettings

新增读取并回填：

- `data.settings.webhook_notification_enabled`
- `data.settings.webhook_notification_url`
- `data.settings.webhook_notification_token`（脱敏值）

#### 5.2.2 saveSettings

新增写入 `settings` payload：

- `webhook_notification_enabled`
- `webhook_notification_url`
- `webhook_notification_token`（遵循 masked 占位不覆盖规则）

#### 5.2.3 autoSaveSettings(tabName==='automation')

自动保存分支补充 webhook 三字段，保持与其它 automation 字段一致。

### 5.3 Webhook 测试函数

新增：

```javascript
async function testWebhookNotification() {
  // POST /api/settings/webhook-test
}
```

按钮行为对齐 Email/Telegram：

1. 点击后按钮禁用 + loading 文案；
2. 请求结束恢复按钮；
3. 成功 toast；失败 `handleApiError`。

### 5.4 API Key 随机生成/复制函数

文件：`static/js/main.js`

新增函数（建议）：

```javascript
function generateExternalApiKey() {
  // 若已有值先 confirm
  // 使用 crypto.getRandomValues 生成 64 位 URL-safe
}

async function copyExternalApiKey() {
  // 复制 settingsExternalApiKey 当前值
}
```

随机算法建议：

```javascript
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
const bytes = new Uint8Array(64);
crypto.getRandomValues(bytes);
const key = Array.from(bytes, b => ALPHABET[b % ALPHABET.length]).join('');
```

要求：

1. 不调用后端生成接口；
2. 不引入第三方 JS 库；
3. 仅更新输入框，不自动触发保存。

### 5.5 i18n 词条补充

文件：`static/js/i18n.js`

新增中英映射（至少）：

- `Webhook 通知`
- `启用 Webhook 通知`
- `Webhook URL`
- `Webhook Token（可选）`
- `测试 Webhook`
- `Webhook 测试成功`
- `Webhook 测试失败`
- `随机生成`
- `当前已存在 API Key，是否覆盖？`

---

## 6. 接口契约（草案）

### 6.1 GET `/api/settings`（增量字段）

```json
{
  "success": true,
  "settings": {
    "webhook_notification_enabled": false,
    "webhook_notification_url": "",
    "webhook_notification_token": ""
  }
}
```

### 6.2 PUT `/api/settings`（增量字段）

请求体可包含：

```json
{
  "webhook_notification_enabled": true,
  "webhook_notification_url": "https://example.com/hook",
  "webhook_notification_token": "optional-token"
}
```

### 6.3 POST `/api/settings/webhook-test`

请求体：`{}`（忽略传入配置，统一读取已保存项）

成功：

```json
{
  "success": true,
  "message": "Webhook 测试消息已发送"
}
```

失败：

```json
{
  "success": false,
  "error": {
    "code": "WEBHOOK_TEST_SEND_FAILED",
    "message": "Webhook 发送失败",
    "message_en": "Failed to send webhook message"
  }
}
```

---

## 7. 安全与可观测性

1. Token 仅加密存储与脱敏回显，不写入日志。
2. URL 可记录用于排障（建议只记录 host/path，避免敏感 query）。
3. Webhook 发送失败通过：
   - 设置测试接口返回；
   - 通知分发失败日志（delivery log + 应用日志）可见。

---

## 8. 兼容性与回滚

### 8.1 兼容性

1. 不影响现有 Email/Telegram 逻辑。
2. 不修改已有 settings key 语义。
3. 不做 DB migration，升级风险较低。

### 8.2 回滚

1. 前端隐藏/移除 Webhook 卡片与 API Key 新按钮。
2. 后端移除 webhook channel 挂载与测试接口路由。
3. settings 中新增 key 可保留，不影响运行。

---

## 9. 实施顺序建议

1. `settings.py`（repo/controller/route）补齐 webhook 配置与测试接口。
2. 新增 `webhook_push.py` 并联通 controller 测试发送。
3. `notification_dispatch.py` 接入 `CHANNEL_WEBHOOK`。
4. `index.html + main.js + i18n.js` 完成页面与 API Key 交互。
5. 补充 TDD 与 TODO，并执行回归。

---

## 10. 验收前技术检查清单

- [x] Webhook URL 校验仅允许 http/https
- [x] enabled=true 时 URL 空值会被拦截
- [x] token 为空时不发送 `X-Webhook-Token`
- [x] token 非空时发送 `X-Webhook-Token`
- [x] 发送超时 10s + 重试 1 次
- [x] API Key 随机值长度 64 且 URL-safe
- [x] 已有值时随机生成前有确认
- [x] 随机/复制不触发自动保存

### 10.1 无 webhook 地址时的联调执行口径（补充）

1. 优先使用 `https://webhook.site/` 生成一次性 URL 做成功链路验证；
2. 失败链路使用 Beeceptor/Pipedream 返回 `500`；
3. 联调路径固定为 `设置 -> 自动化 Tab -> Webhook 通知`；
4. 如需本地服务配合联调，仅允许后台独立进程方式启动（`Start-Process`/独立进程），不使用前台阻塞命令。

### 10.2 会话实测回填（2026-04-15）

1. 后台启动：`Start-Process` 独立进程，PID `37460`；
2. 健康检查：`GET /healthz` 返回 `200`；
3. 日志验证：
   - 未配置时 `POST /api/settings/webhook-test` 返回 `400`（`WEBHOOK_NOT_CONFIGURED`）；
   - 保存配置后 `POST /api/settings/webhook-test` 返回 `200`；
4. 接收端核对：已确认 method/header/body（POST + text/plain + 业务文本字段）；当前 token 为空，未发送 `X-Webhook-Token` 符合预期。

### 10.3 第二轮分批全量回归与 Docker 前置校验（2026-04-15）

1. 分批全量回归：
   - `test_[a-f]*` → Ran 346, OK
   - `test_[g-l]*` → Ran 89, OK
   - `test_[m-r]*` → Ran 231, OK (skipped=7)
   - `test_[s-z]*` → Ran 492, OK
   - 汇总：**1158 tests 通过，skipped=7**；
2. Docker 构建与运行校验：
   - `docker version` 已恢复可用（Client/Server 均为 28.3.2）；
   - `docker build -t "outlook-email-plus:local-regression-20260415" .` 成功；
   - 首次 `docker run ... -p 5055:5000` 失败（端口占用/权限）；
   - 清理失败容器后，`docker run -d --name "oep-regression-20260415" -p 18080:5000 ...` 成功；
    - 容器状态：`healthy`，端口映射 `18080->5000`；
    - 容器内服务 `/healthz` 验证通过（HTTP 200）。

### 10.4 main 分支本地启动与全量回归复核（2026-04-15）

1. 分支与现场处理：
   - `Buggithubissue` 已本地 fast-forward 合并到 `main`（未 push）；
   - 按会话要求先停止原有 5000 端口进程（PID `37460`）；
   - 在 `main` 重新后台启动 `web_outlook_app.py`（PID `41184`）。
2. 健康检查：
   - `GET http://127.0.0.1:5000/healthz` → `200`；
   - 返回体：`{"boot_id":"1776240270869-41184","status":"ok","version":"1.16.0"}`。
3. main 分支分批全量回归：
   - `test_[a-f]*` → Ran 346, OK
   - `test_[g-l]*` → Ran 89, OK
   - `test_[m-r]*` → Ran 231, OK (skipped=7)
   - `test_[s-z]*` → Ran 492, OK
    - 汇总：**1158 tests 通过，skipped=7**。

### 10.5 发布续推前现场核对（2026-04-15）

1. 工作树状态：
   - 发布主工作树：`E:/hushaokang/Data-code/outlookEmail`；
   - 分支：`main...origin/main [ahead 3]`；
   - 未提交变更集中在 `v1.17.0` 版本口径文件（`CHANGELOG/README/DEVLOG/__init__/version tests`）。
2. 交叉核对：
   - `Buggithubissue` 工作树状态为 `ahead 1` 且工作区干净；
   - 不包含上述 `v1.17.0` 未提交改动，确认发布应在 main 工作树继续。
3. 运行态：
   - `5000` 端口当前无监听；
   - `GET http://127.0.0.1:5000/healthz` 连接失败；
   - 结论：此前后台服务已退出，本轮先记录状态，不做额外启停动作。
4. 发布流程约束：
   - 按 `RELEASE.md` 执行 Python/Docker/GitHub Release 链路（提交→tag→push→Release/Actions 监控）。

### 10.6 发布后质量门禁修复（2026-04-15）

1. 推送后 CI 结果：
   - `Create GitHub Release`（tag）成功；
   - `Code Quality`（main）失败；
   - `Build and Push Docker Image`（main/tag）失败（受 quality-gate 阻断）。
2. 失败根因：
   - `black --check` 未通过；日志显示多处文件需格式化（包含 webhook 相关代码与测试文件）。
3. 本地修复执行：
   - `python -m black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
   - `python -m isort --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
   - `python -m black --check ...` + `python -m isort --check-only ...` 均通过。
4. 修复后回归复核：
   - `test_[a-f]*` → Ran 346, OK
   - `test_[g-l]*` → Ran 89, OK
   - `test_[m-r]*` → Ran 231, OK (skipped=7)
   - `test_[s-z]*` → Ran 492, OK
   - 汇总：**1158 tests 通过，skipped=7**。

### 10.7 v1.17.0 发布状态核对（2026-04-15）

1. Release 结果：
   - `v1.17.0` 已发布且为 `Latest`；
   - 非草稿、非预发布；
   - 发布页：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`。
2. 发布后修复链路结果（提交 `f3d2208`）：
   - `Code Quality` ✅
   - `Python Tests` ✅
   - `Build and Push Docker Image` ✅
   - `SonarCloud Scan` ✅
3. 额外监控收口：
   - 文档收口提交 `05871bf` 触发的新一轮 `SonarCloud Scan`（run `24450875717`）已完成 `success`。

### 10.8 双仓镜像构建状态核对（2026-04-15）

1. 核对目标仓库：
   - GHCR：`ghcr.io/zeropointsix/outlook-email-plus`
   - DockerHub：`docker.io/guangshanshui/outlook-email-plus`
2. `main` 与 `latest` 标签：
   - 两仓均可拉取 manifest，且 index digest 一致：
     - `sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
3. `v1.17.0` 标签：
   - 两仓查询结果均 `not found`；
   - 与历史状态一致：tag 流水线初次失败导致版本标签镜像未生成。

### 10.9 v1.17.0 重打标签补镜像（2026-04-15）

1. 执行原因：
   - 先前 `v1.17.0` 标签镜像未生成（tag workflow 初次失败）。
2. 执行动作：
   - `v1.17.0` tag 重打至 `f3d2208`（四项主工作流全绿提交）；
   - 删除远端旧 tag 并推送新 tag。
3. 触发结果：
   - `Create GitHub Release`（run `24451870230`）已 success；
   - `Build and Push Docker Image`（run `24451870226`）已触发，当前处于 queued/in_progress（待完成后复核双仓 `v1.17.0`）。

### 10.10 v1.17.0 标签镜像补齐完成（2026-04-15）

1. 工作流结果：
   - `Build and Push Docker Image`（run `24451870226`）✅ success。
2. 双仓复核：
   - GHCR `v1.17.0` digest：`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
   - DockerHub `v1.17.0` digest：`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
   - 结论：双仓一致，版本标签镜像补齐成功。
