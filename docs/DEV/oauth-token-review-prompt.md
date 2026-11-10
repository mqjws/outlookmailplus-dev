# OAuth Token 获取工具 — 功能实现 & 回归审查提示词

> 版本: v1.0
> 创建日期: 2026-04-12
> 适用项目: OutlookMail Plus（outlookEmailPlus）
> 功能版本: v1.15.0
> 方案: 方案 B — 松耦合集成（独立 Flask Blueprint）
> 收口模式: 兼容账号导入模式（tenant=consumers, 无 client_secret）

---

## 提示词正文

你是一名高信噪比代码审查员。你的任务是对 **OAuth Token 获取工具** 的完整实现进行深度审查，重点检验**功能实现正确性**和**回归安全性**。

### 审查原则

1. **只报告真正重要的问题**：Bug、安全漏洞、逻辑错误、数据丢失风险、文档与代码不一致
2. **不报告**：风格偏好、格式问题、微小命名差异、"可以更好但不影响功能"的建议
3. **每个发现必须有**：文件路径 + 行号 + 问题说明 + 为什么重要 + 建议修复
4. **严重程度**：Must-Fix（合并前必须修复）/ Watch（建议修复但不阻塞合并）

---

### 权威文档（优先级从高到低）

以下文档是实现的唯一正确参考。当代码与文档不一致时，以文档为准报告偏差：

1. **TD**: `docs/TD/2026-04-12-OAuth-Token获取工具TD.md` v1.3 — 函数签名、参数、返回结构、伪代码
2. **TDD**: `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md` v1.1 — 测试用例 ID、断言条件
3. **TODO**: `docs/TODO/2026-04-12-OAuth-Token获取工具TODO.md` v1.1 — 任务分解与验收标准
4. **FD**: `docs/FD/2026-04-12-OAuth-Token获取工具FD.md` v1.0 — 接口契约、数据流
5. **PRD**: `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md` v1.3 — 业务需求

> **重要**: 所有文档顶部均有"v1.15.0 实施收口说明（兼容账号导入模式）"，该说明覆盖文档正文中关于"可变 tenant / 可选 client_secret / 单租户或机密客户端"的旧设计描述。以收口说明为准。

---

### 待审查文件清单

#### 核心后端（新增）
- `outlook_web/services/oauth_tool.py` — OAuth 核心逻辑（PKCE、FLOW_STORE、Scope 校验、Token 交换、错误引导、JWT 解码）
- `outlook_web/controllers/token_tool.py` — 控制器层（8 个函数 + 动态 404 守卫）
- `outlook_web/routes/token_tool.py` — Blueprint 定义（8 条路由）

#### 核心后端（修改）
- `outlook_web/config.py` — 新增 6 个 OAuth 环境变量函数（文件末尾）
- `outlook_web/repositories/settings.py` — 新增 6 个 OAuth getter（文件末尾）
- `outlook_web/app.py` — 条件 Blueprint 注册 + context_processor 注入 `OAUTH_TOOL_ENABLED`

#### 前端（新增）
- `static/js/features/token_tool.js` — 前端交互逻辑
- `templates/token_tool.html` — 独立页面模板（不继承 base）
- `templates/popup_result.html` — OAuth 回调结果页（极简内联样式）
- `static/css/token_tool.css` — 工具页样式

#### 前端（修改）
- `templates/index.html` — 侧边栏条件入口按钮

#### 测试
- `tests/test_oauth_tool.py` — 全部专项测试

#### 发布 & 文档
- `outlook_web/__init__.py` — 版本号
- `CHANGELOG.md` — 变更日志
- `README.md` / `README.en.md` — 项目介绍
- `WORKSPACE.md` — 操作记录
- `.env.example` — 环境变量文档
- `docker-compose.yml` — Docker 配置文档

---

### 关键技术约束（审查时必须检查）

#### 1. `update_account()` 必填参数陷阱
`outlook_web/repositories/accounts.py` 的 `update_account()` 签名为：
```python
def update_account(account_id, email_addr: str, password, client_id, refresh_token, group_id: int, remark: str, status="active", ...)
```
`email_addr`、`group_id`、`remark` 均为**必填非 Optional**。传 None 会导致 `if not email_addr` 返回 False。  
→ **审查点**: `save_to_account()` 的 update 模式必须先 `get_account_by_id()` 获取现有记录，将 email/group_id/remark 回传。

#### 2. `update_account_credentials()` 的 allowed set
```python
def update_account_credentials(account_id, **kwargs):
    allowed = {"client_id", "refresh_token", "imap_password", "access_token", "token_expiry"}
```
allowed set **不包含 "status"**。  
→ **审查点**: 如需恢复 `status="active"`，必须通过 `update_account()` 而非 `update_account_credentials()`。

#### 3. `load_accounts()` 而非 `get_all_accounts()`
系统中**不存在** `get_all_accounts()` 函数。正确函数名为 `load_accounts()`（line 47）。  
→ **审查点**: `get_account_list()` 控制器必须调用 `load_accounts()`。

#### 4. 收口模式约束
- Tenant 固定 `consumers`
- `client_secret` 禁用（页面和接口均按空值处理）
- 默认 Scope 为 IMAP 兼容预设
- `prepare / config / save` 接口需拒绝不兼容配置

#### 5. Scope Chip 安全
动态 scope 值**不得**拼入 inline `onclick`。必须使用 DOM API 创建 + 事件委托。  
→ **审查点**: `buildScopeChip()` 使用 `document.createElement()` + `textContent`；事件通过 `data-scope` + 容器级 `click` 监听。

#### 6. client_secret 读取策略
`get_oauth_tool_client_secret()` 必须区分三种情况：
1. 明文值（历史遗留）→ 直接返回
2. `enc:` 前缀且解密成功 → 返回解密值
3. `enc:` 前缀但解密失败 → 返回空串（不泄露损坏密文）

---

### 八维度审查清单

#### ① TD 一致性（功能实现正确性 — 最高优先级）

逐函数比对代码与 TD 定义：

**TD §4.1 config.py — 6 个环境变量函数**:
| 函数 | 环境变量 | 默认值 |
|------|---------|--------|
| `get_oauth_tool_enabled()` | `OAUTH_TOOL_ENABLED` | `True` |
| `get_oauth_client_id_default()` | `OAUTH_CLIENT_ID` | `""` |
| `get_oauth_client_secret_default()` | `OAUTH_CLIENT_SECRET` | `""` |
| `get_oauth_redirect_uri_default()` | `OAUTH_REDIRECT_URI` | `""` |
| `get_oauth_scope_default()` | `OAUTH_SCOPE` | `"offline_access https://graph.microsoft.com/.default"` |
| `get_oauth_tenant_default()` | `OAUTH_TENANT` | `"consumers"` |

**TD §4.2 settings.py — 6 个 OAuth getter**:
| 函数 | Settings key | 优先级链 |
|------|-------------|---------|
| `get_oauth_tool_client_id()` | `oauth_tool_client_id` | Settings → env → `""` |
| `get_oauth_tool_client_secret()` | `oauth_tool_client_secret` | Settings(自动解密) → env → `""` |
| `get_oauth_tool_redirect_uri()` | `oauth_tool_redirect_uri` | Settings → env → `""` |
| `get_oauth_tool_scope()` | `oauth_tool_scope` | Settings → env → default scope |
| `get_oauth_tool_tenant()` | `oauth_tool_tenant` | Settings → env → `"consumers"` |
| `get_oauth_tool_prompt_consent()` | `oauth_tool_prompt_consent` | Settings → `False` |

**TD §4.4 routes — 8 条路由**:
| 方法 | 路径 | 控制器函数 | endpoint |
|------|------|-----------|----------|
| GET | `/token-tool` | `render_page` | (默认) |
| POST | `/api/token-tool/prepare` | `prepare_oauth` | (默认) |
| GET | `/token-tool/callback` | `handle_callback` | (默认) |
| POST | `/api/token-tool/exchange` | `exchange_token` | (默认) |
| POST | `/api/token-tool/save` | `save_to_account` | (默认) |
| GET | `/api/token-tool/accounts` | `get_account_list` | (默认) |
| GET | `/api/token-tool/config` | `get_config` | (默认) |
| POST | `/api/token-tool/config` | `save_config` | `save_config` |

**TD §4.5 controllers — 8 个函数**:
- `render_page()` — `@login_required`
- `prepare_oauth()` — `@login_required`, 校验 client_id + redirect_uri, 调用 `start_oauth_flow()`, session 存 state
- `handle_callback()` — **无** `@login_required`, 渲染 `popup_result.html`
- `exchange_token()` — `@login_required`, session state 校验 + FLOW_STORE 双验证, 调用 `exchange_code_for_tokens()`, 成功/失败均清理 flow
- `save_to_account()` — `@login_required`, update/create 两种 mode, 调用 `test_refresh_token_with_rotation()` 验证 token
- `get_account_list()` — `@login_required`, 调用 `load_accounts()`, 只返回 `{id, email, status, account_type}`
- `get_config()` — `@login_required`, 调用 6 个 settings getter
- `save_config()` — `@login_required`, client_secret 使用 `encrypt_data()` 加密存储

**TD §4.6 services — 核心函数**:
| 函数 | 签名 | 关键行为 |
|------|------|---------|
| `store_oauth_flow(state, flow_data)` | `str, Dict → None` | Lock + _prune_expired |
| `get_oauth_flow(state)` | `str → Optional[Dict]` | Lock + _prune_expired, 返回 copy |
| `discard_oauth_flow(state)` | `str → None` | Lock + pop |
| `_prune_expired()` | `→ None` | 清理 > 20min 条目 |
| `generate_pkce()` | `→ Tuple[str, str]` | `token_urlsafe(64)` → SHA-256 → base64url 无 padding |
| `start_oauth_flow(oauth_config)` | `Dict → Tuple[Optional[str], str]` | 成功=(url, state), 失败=(None, error) |
| `exchange_code_for_tokens(code, oauth_config, verifier)` | `→ Tuple[Optional[Dict], Any]` | 成功=(data, None), 失败=(None, error) |
| `validate_scope(scope_value)` | `str → Tuple[str, Optional[str]]` | 合法=(normalized, None), 非法=(value, error) |
| `normalize_scope(scope_value)` | `str → str` | 去重+排序+自动加 `offline_access` |
| `map_error_guidance(error_detail)` | `str → str` | ERROR_GUIDANCE_MAP 匹配 |
| `decode_jwt_payload(token)` | `str → Optional[dict]` | 无验签，自动补 Base64 padding |

#### ② 安全链路

- [ ] PKCE: `secrets.token_urlsafe(64)` → SHA-256 → base64url（无 `=` padding）
- [ ] State: `secrets.token_urlsafe(24)`, 存入 session + FLOW_STORE, 双重校验
- [ ] Flow 一次性消费: `discard_oauth_flow()` + `session.pop()` 在 exchange 后执行（成功/失败均执行）
- [ ] FLOW_STORE: Lock + 20min TTL + 每次访问触发 `_prune_expired()`
- [ ] `handle_callback()` 无 `@login_required`（正确：OAuth 重定向端点）
- [ ] `client_secret` 条件携带: `if oauth_config.get("client_secret"): payload["client_secret"] = ...`
- [ ] `prompt=consent` 条件携带: `if oauth_config.get("prompt_consent"): params["prompt"] = "consent"`
- [ ] CSRF: POST 端点通过 `X-CSRFToken` header; GET callback 不受 CSRF 影响

#### ③ 数据写入链路

- [ ] update 模式: `get_account_by_id()` → `update_account_credentials(client_id=, refresh_token=)` → `update_account(email_addr=existing["email"], group_id=existing["group_id"], remark=existing["remark"], status="active")`
- [ ] create 模式: `add_account(email_addr=, password="", client_id=, refresh_token=, account_type="outlook", provider="outlook")`
- [ ] Token 轮换: `test_refresh_token_with_rotation()` 返回 `(valid, error, new_rt)`; `if new_rt: refresh_token = new_rt`
- [ ] 验证在写入之前执行
- [ ] `get_account_list()` 过滤: `account_type in ("outlook", None)`
- [ ] `get_account_list()` 只返回非敏感字段: `{id, email, status, account_type}`

#### ④ 前后端契约一致性

| 端点 | 后端响应结构 | 前端读取路径 |
|------|------------|-------------|
| `/api/token-tool/prepare` | `{"success": true, "data": {"authorize_url": "..."}}` | `data.data?.authorize_url` |
| `/api/token-tool/exchange` | `{"success": true, "data": {token fields}}` | `data.data` → `renderTokenResult()` |
| `/api/token-tool/exchange` error | `{"error": {"message": "...", "details": "..."}}` | `data.error?.message` + `data.error?.details` |
| `/api/token-tool/config` GET | `{"success": true, "data": {6 config fields}}` | `data.data.client_id` 等逐字段 |
| `/api/token-tool/config` POST | `{"success": true, "message": "配置已保存"}` | `data.message` |
| `/api/token-tool/accounts` | `{"success": true, "data": [{id, email, status, account_type}]}` | `data.data.map(...)` |
| `/api/token-tool/save` | `{"success": true, "data": {...}}` | `data.success` 标志 |

- [ ] HTML 模板中的 DOM ID 与 JS 中的 `getElementById` / `querySelector` 匹配
- [ ] Jinja2 模板变量 `{{ OAUTH_TOOL_ENABLED }}` 与 `app.py` context_processor 注入一致

#### ⑤ XSS / 注入 / 信息泄露

- [ ] Scope Chip: 使用 `document.createElement()` + `textContent`（非 innerHTML）
- [ ] Scope Chip 事件: `data-scope` 属性 + 容器事件委托（非 inline onclick）
- [ ] `showStatus()`: 使用 `escapeHtml()` 处理 message 和 detail
- [ ] `loadAccountOptions()`: 使用 `escapeHtml()` 处理 id/email/status
- [ ] `popup_result.html`: Jinja2 自动转义 `{{ error_code }}`、`{{ error_description }}`、`{{ guidance }}`
- [ ] Token 结果面板: 使用 `.value = ...` 设值（input/textarea），非 innerHTML
- [ ] 账号列表 API 不返回 refresh_token / password / imap_password

#### ⑥ 测试覆盖有效性（回归安全性 — 最高优先级）

**TDD 定义的测试类**（共 13 个 TestCase）:

| 类名 | TDD 用例 ID 前缀 | 预期用例数 |
|------|-----------------|-----------|
| `OAuthToolPkceTests` | S-PKCE-01~04 | 4 |
| `OAuthToolScopeTests` | S-SCOPE-01~07 | 7 |
| `OAuthToolFlowStoreTests` | S-FLOW-01~06 | 6 |
| `OAuthToolErrorGuidanceTests` | S-ERR-01~04 | 4 |
| `OAuthToolJwtDecodeTests` | S-JWT-01~03 | 3 |
| `OAuthToolTokenExchangeTests` | S-EXCH-01~05 | 5 |
| `OAuthToolApiPrepareTests` | A-PREP-01~05 | 5 |
| `OAuthToolApiExchangeTests` | A-EXCH-01~05 | 5 |
| `OAuthToolApiConfigTests` | A-CFG-01~05 + 加固 2 | 7 |
| `OAuthToolApiSaveTests` | A-SAVE-01~06 | 6 |
| `OAuthToolApiBlueprintTests` | A-BP-01~03 | 3 |
| `OAuthToolApiAccountListTests` | A-LIST-01~04 | 4 |

**总计**: TDD 基线 57 + 审查后加固 2 = **59 个测试**

审查要点:
- [ ] 每个 TDD 用例 ID 有对应测试函数
- [ ] 安全关键分支（state 校验、FLOW_STORE TTL、PKCE S256）有直接测试
- [ ] 错误路径有专项测试（不只 happy path）
- [ ] `test_config_load_supports_legacy_plaintext_secret` — 覆盖明文配置兼容
- [ ] `test_config_load_hides_unreadable_encrypted_secret` — 覆盖损坏密文隐藏
- [ ] 全局回归: `python -m pytest tests/ -v` 全部通过，零新增失败

#### ⑦ 开关与注册

- [ ] `get_oauth_tool_enabled()` 读取 `OAUTH_TOOL_ENABLED` env var，默认 `True`
- [ ] `app.py` 中 `if config.get_oauth_tool_enabled(): app.register_blueprint(...)`
- [ ] `_ensure_oauth_tool_enabled()` 在每个控制器函数中检查开关（动态 404）
- [ ] `index.html` 中 `{% if OAUTH_TOOL_ENABLED %}` 控制侧边栏按钮显示
- [ ] 关闭状态下: 页面 404 + API 404 + 侧边栏无按钮

#### ⑧ 发布与文档一致性

- [ ] `__init__.py` 中 `__version__ = "1.15.0"`
- [ ] `CHANGELOG.md` 中 `[v1.15.0]` 列出 OAuth 新功能 + 修复 + 加固
- [ ] `README.md` 中"当前稳定版本"为 `v1.15.0`，含 OAuth Token 工具介绍
- [ ] `README.en.md` 同步更新
- [ ] `.env.example` 含 6 个 OAuth env vars（注释形式）
- [ ] `docker-compose.yml` 含 OAuth env vars（注释形式）
- [ ] `WORKSPACE.md` 含开发记录

---

### 输出格式

#### 审查概况表

| 维度 | 数据 |
|---|---|
| 审查文件 | X 个 |
| 专项测试 | XX passed |
| 全局回归 | XXX passed, X skipped |
| 版本 | v1.15.0 |

#### 结论

- **Must-Fix**: X 条
- **Watch Items**: X 条
- **结论**: Merge-Ready / Merge-Blocked

#### 逐条问题

对每个问题：
```
### M-N / W-N · 问题标题 (CRITICAL/HIGH/MEDIUM/LOW)
- **级别**: Must-Fix / Watch
- **文件**: `path/to/file`
- **位置**: 行号 / 函数名
- **问题说明**: 具体描述
- **为什么重要**: 影响分析
- **建议修复**: 修复方案
```

#### 八维度详细结果

对每个维度，以 ✅ / ❌ / ⚠️ 标注检查结果。
