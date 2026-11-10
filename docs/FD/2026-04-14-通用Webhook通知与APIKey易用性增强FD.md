# FD: 通用 Webhook 通知与 API Key 易用性增强

- 文档版本: v1.11
- 创建日期: 2026-04-14
- 更新日期: 2026-04-15（v1.11 — 回填 v1.17.0 双仓标签镜像补齐完成）
- 关联 PRD: `docs/PRD/2026-04-14-通用Webhook通知与APIKey易用性增强PRD.md`（路径待补）
- 关联 TD: `docs/TD/2026-04-14-通用Webhook通知与APIKey易用性增强TD.md`
- 关联 TDD: `docs/TDD/2026-04-14-通用Webhook通知与APIKey易用性增强TDD.md`
- 关联 TODO: `docs/TODO/2026-04-14-通用Webhook通知与APIKey易用性增强TODO.md`
- 当前范围: 功能设计（系统行为、页面交互、接口契约、数据流），不展开具体代码实现

---

## 1. 功能定义

本期交付两项能力：

1. 在现有通知体系中新增**通用 Webhook 通道**（非企业微信专属）。
2. 在 API 安全设置中增强 External API Key 的**随机生成 + 复制**交互。

### 1.1 设计边界

**本期包含**：

- 全局单 Webhook 通道配置（URL / Token / 开关）。
- Webhook 测试发送能力。
- 纯文本 POST 投递与最小消息模板。
- External API Key 的 64 位 URL-safe 随机生成与复制能力。

**本期不包含**：

- 企业微信/飞书/钉钉平台定制模板。
- 每账号单独 webhook URL。
- 队列化重试与复杂退避。

---

## 2. 页面与交互设计

### 2.1 设置页位置

#### 2.1.1 Webhook 卡片位置

- 放置位置：`自动化 Tab` 的通知区（与 Email/Telegram 同层）。
- 卡片标题建议：`📡 Webhook 通知`。
- 无现成地址时推荐先到 `https://webhook.site/` 生成临时 URL，再回到此卡片配置。

#### 2.1.2 API Key 交互位置

- 放置位置：`API 安全 Tab` 的 `对外开放 API Key` 输入框右侧（或同组操作区）。
- 操作按钮：`随机生成`、`复制`。

### 2.2 Webhook 配置字段

| 字段 | 类型 | 说明 |
|---|---|---|
| 启用 Webhook 通知 | checkbox | 总开关 |
| Webhook URL | text | 支持 `http://` 和 `https://` |
| Webhook Token | password/text | 可选；有值时通过请求头下发 |
| Webhook 超时（ms） | number（只读展示或隐藏） | V1 固定 10000（10s） |

> 说明：V1 超时与重试策略固定，不在 UI 暴露可调参数。

### 2.3 Webhook 测试交互

卡片内提供按钮：`测试 Webhook`。

行为：

1. 点击后调用测试接口发送一条测试消息。
2. 成功：前端 toast/状态提示成功。
3. 失败：前端显示失败原因（便于排障）。

### 2.4 API Key 增强交互

#### 2.4.1 随机生成

1. 点击 `随机生成`。
2. 若输入框已有内容，弹出二次确认。
3. 确认后生成 `64` 位 URL-safe 字符串并写入输入框。

#### 2.4.2 复制

1. 点击 `复制`。
2. 复制当前输入框值到剪贴板。
3. 成功/失败均给出明确反馈。

#### 2.4.3 保存语义

- 生成与复制不会自动触发设置保存。
- 仍需点击设置页保存按钮后生效。

---

## 3. 系统行为设计

### 3.1 Webhook 通道接入原则

1. Webhook 作为通知通道扩展，沿用现有通知分发口径。
2. 与 Email/Telegram 并列，不改变既有账号通知参与语义。
3. 去重与游标仍由现有通知状态机制承载。

### 3.2 投递协议

| 项 | 约束 |
|---|---|
| Method | `POST` |
| Content-Type | `text/plain; charset=utf-8` |
| 成功判定 | HTTP 2xx |
| 超时 | 10s |
| 重试 | 失败后重试 1 次 |
| 鉴权头 | `X-Webhook-Token`（仅 Token 非空时附带） |

### 3.3 文本模板（V1）

消息体采用纯文本，按固定字段顺序组织，至少包含：

1. 来源邮箱
2. 来源类型（普通邮箱/临时邮箱）
3. 文件夹
4. 发件人
5. 主题
6. 时间
7. 正文摘要（按现有正文截断策略处理）

---

## 4. 数据与配置契约

### 4.1 Settings 建议键（V1）

| Key | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `webhook_notification_enabled` | bool(string) | `false` | Webhook 通道总开关 |
| `webhook_notification_url` | string | `""` | 目标 URL |
| `webhook_notification_token` | string(encrypted) | `""` | 可选鉴权 Token |

> 说明：Token 与现有敏感设置保持一致，采用加密存储 + 脱敏回显口径。

### 4.2 设置接口扩展（概念）

- `GET /api/settings`：返回 webhook 字段（Token 脱敏回显）。
- `POST /api/settings`：支持保存 webhook 开关/URL/Token。

### 4.3 测试接口（新增）

- `POST /api/settings/webhook-test`
- 行为：使用已保存配置发送测试消息。
- 响应：
  - 成功：`success=true`
  - 失败：`success=false` + 可读错误信息

---

## 5. 数据流（概要）

### 5.1 正常通知流

```
新邮件到达
  → 通知分发层判定来源与参与资格
  → 选择启用通道（Email / Telegram / Webhook）
  → Webhook 组装纯文本 payload
  → POST 到 webhook URL（可选 X-Webhook-Token）
  → 2xx 记成功；失败重试 1 次后记失败日志
```

### 5.2 Webhook 测试流

```
设置页点击「测试 Webhook」
  → 调用 /api/settings/webhook-test
  → 使用当前已保存配置发测试消息
  → 前端展示成功/失败及错误原因
```

### 5.3 API Key 交互流

```
点击随机生成
  → 若已有值则确认
  → 生成 64 位 URL-safe 串并写入输入框
点击复制
  → 复制输入框值
点击保存设置
  → 持久化 external_api_key
```

---

## 6. 错误与提示口径

### 6.1 Webhook 配置校验

建议覆盖：

1. 开启时 URL 不能为空。
2. URL 格式非法（非 http/https）时报错。
3. 测试发送超时/连接失败时返回可读错误。

### 6.2 前端提示

1. `测试成功` / `测试失败：{reason}`
2. `内容已复制到剪贴板` / `复制失败，请手动复制`
3. 覆盖确认文案：`当前已存在 API Key，是否覆盖？`

---

## 7. 验收清单

### 7.1 Webhook

- [ ] 自动化 Tab 可见 Webhook 卡片与测试按钮。
- [ ] 保存后可稳定读取 webhook 配置。
- [ ] Webhook 发送为 `text/plain; charset=utf-8`。
- [ ] Token 非空时请求头带 `X-Webhook-Token`；空时不带。
- [ ] 非 2xx 或超时场景，能看到失败信息并落日志。

### 7.2 API Key

- [ ] API 安全 Tab 显示 `随机生成/复制` 按钮。
- [ ] 随机值为 64 位 URL-safe。
- [ ] 已有值时生成前弹确认。
- [ ] 不自动保存；需手动保存后才持久化。

### 7.3 无自建接收端时的联调方案（补充）

当用户没有现成 webhook 服务时，建议按以下三步完成可视化联调：

1. 打开 `https://webhook.site/`，获取临时 URL；
2. 在 `设置 -> 自动化 Tab -> Webhook 通知` 保存该 URL（可选填 token）；
3. 点击“测试 Webhook”，在接收页核对：
   - method=POST；
   - `Content-Type: text/plain; charset=utf-8`；
   - body 字段完整；
   - 若已配置 token，则存在 `X-Webhook-Token`。

失败路径测试建议：

- 使用 Beeceptor/Pipedream 返回固定 `500`，确认前端失败提示与后端重试行为符合预期。

会话实操建议（当前用户场景）：

1. 先在 webhook.site 生成 URL；
2. 进入 Webhook 卡片保存 URL/token；
3. 再点击测试按钮；
4. 结果核对后回填 WORKSPACE 与测试记录。

会话进展回填（2026-04-15）：

- 当前测试 URL：`https://webhook.site/00766721-eaaf-4a3b-9821-60575812158c`
- 执行状态：已完成“保存 + 测试发送 + webhook.site 请求细节核对（POST/text/plain/body）”；失败链路待补
- 回归状态：第二轮分批全量回归再次通过（1158 tests，skipped=7）
- Docker 状态：镜像构建成功并已完成容器健康验证（`18080->5000`，`/healthz`=200，container healthy）

会话进展回填（2026-04-15，main 分支）：

- 分支状态：`Buggithubissue` 变更已本地合并到 `main`（fast-forward，未 push）
- 服务状态：按后台独立进程重新在 `main` 启动 `web_outlook_app.py`（PID `41184`），`GET /healthz` 返回 `200`
- 回归状态：在 `main` 再次执行分批全量回归并通过：
  - `test_[a-f]*` → Ran 346, OK
  - `test_[g-l]*` → Ran 89, OK
  - `test_[m-r]*` → Ran 231, OK (skipped=7)
  - `test_[s-z]*` → Ran 492, OK
  - 汇总：**1158 tests 通过，skipped=7**

会话进展回填（2026-04-15，发布续推前核对）：

- 工作树核对：当前发布工作树为 `E:/hushaokang/Data-code/outlookEmail`（`main...origin/main [ahead 3]`）。
- 差异核对：`Buggithubissue` 工作树当前仅 `ahead 1` 且干净，不含本轮 `v1.17.0` 未提交版本改动。
- 运行态核对：`5000` 端口当前无监听，`GET /healthz` 连接失败（说明此前后台进程已退出）。
- 发布口径：后续按 `RELEASE.md` 的 Python/Docker/GitHub Release 流程继续推进，不使用 Tauri/Cargo/NPM 路径。

会话进展回填（2026-04-15，发布后质量门禁修复）：

- `v1.17.0` 已完成提交/tag/push/Release 创建，但初次 CI 出现 `Code Quality` 失败并阻断 `Build and Push Docker Image`（main/tag）。
- 失败根因：`black --check` 不通过（日志显示多文件需格式化）。
- 会话已执行修复：
  - `python -m black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
  - `python -m isort --profile black outlook_web tests web_outlook_app.py outlook_mail_reader.py start.py`
  - `black --check` + `isort --check-only` 均通过。
- 修复后分批回归再次通过：
  - `test_[a-f]*` → Ran 346, OK
  - `test_[g-l]*` → Ran 89, OK
  - `test_[m-r]*` → Ran 231, OK (skipped=7)
  - `test_[s-z]*` → Ran 492, OK
  - 汇总：**1158 tests 通过，skipped=7**。

会话进展回填（2026-04-15，发布状态确认）：

- 已确认 `v1.17.0` 发布状态：`GitHub Release` 为 `Latest`、非草稿、非预发布。
- 发布页：`https://github.com/ZeroPointSix/outlookEmailPlus/releases/tag/v1.17.0`
- 发布时间：`2026-04-15T10:29:25Z`
- 本轮会话对发布后修复链路的监控已收口：`Code Quality / Python Tests / Build and Push Docker Image / SonarCloud Scan` 均在修复提交链路达到 success。

会话进展回填（2026-04-15，双仓 Docker 镜像状态核对）：

- 已核对仓库：
  - GHCR：`ghcr.io/zeropointsix/outlook-email-plus`
  - DockerHub：`docker.io/guangshanshui/outlook-email-plus`
- `main` 标签：两仓均存在，且 digest 一致：
  - `sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
- `latest` 标签：两仓均存在，且 digest 一致：
  - `sha256:8aef74b93a816e3aa8020d1c20767715a5c51e1373f8c8f58f5d692092869218`
- `v1.17.0` 标签：两仓当前均不存在（tag 推送当时 workflow 失败导致未产出版本标签镜像）。

会话进展回填（2026-04-15，v1.17.0 重打标签补镜像）：

- 已按会话确认将 `v1.17.0` 从旧目标提交重打到已验证全绿提交 `f3d2208`。
- 执行动作：
  - 本地重打 tag：`git tag -fa v1.17.0 f3d2208 -m "v1.17.0 (retag for CI-green image publish)"`
  - 删除远端旧 tag：`git push origin :refs/tags/v1.17.0`
  - 推送新 tag：`git push origin v1.17.0`
- 触发结果：
  - `Create GitHub Release`（tag）已 success；
  - `Build and Push Docker Image`（tag）已触发，当前处于排队/执行中（待最终完成后再核对双仓 `v1.17.0` 标签）。

会话进展回填（2026-04-15，v1.17.0 双仓标签镜像补齐完成）：

- `Build and Push Docker Image`（tag run `24451870226`）已 `success`。
- 双仓 `v1.17.0` 标签均已存在，且 digest 一致：
  - GHCR：`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
  - DockerHub：`sha256:e485e28b6e5ca5fbb83a0a9f38dc173316bfd166cb874a07b0250471021bfdb4`
- 结论：`v1.17.0` 版本发布与双仓镜像现已完整闭环。

---

## 8. 风险与后续

1. 下游若仅收 JSON，需接入方做文本转发适配。
2. 若后续出现多平台格式需求，再扩展模板层（本期不做）。
3. 已进入 TD 阶段，后续按 TDD/TODO 继续收敛测试矩阵与执行拆分。
4. 若当前环境无法搭建本地接收端，优先使用在线 webhook 调试平台完成验收。
