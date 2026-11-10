# TODO: OAuth Token 获取工具

> 创建日期：2026-04-12
> **更新日期：2026-04-16（v1.3 — 会话文档按实际实现口径再同步）**
> 基于 PRD v1.5：`docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`
> 基于 FD v1.2：`docs/FD/2026-04-12-OAuth-Token获取工具FD.md`
> 基于 TD v1.5：`docs/TD/2026-04-12-OAuth-Token获取工具TD.md`
> 基于 TDD v1.3：`docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md`
> 目标版本：v1.15.0
> 方案选型：**方案 B — 松耦合集成**（独立 Flask Blueprint，可启用/禁用）
> OAuth 流程：Authorization Code + PKCE（兼容导入模式：`tenant=consumers`、不支持 `client_secret`）
> 回调策略：Smart callback（localhost 自动 + 非 localhost 手动粘贴 URL）
> 配置持久化：服务端 Settings 表 + 环境变量双优先级链
> 测试文件：`tests/test_oauth_tool.py`（单文件，多 TestCase 分组）

> **v1.15.0 实施收口说明**
>
> 当前执行清单以兼容账号导入模式为准：Tenant 固定 `consumers`，`client_secret` 不再作为支持输入，相关保存/读取/验证任务均应调整为“固定空值 + 不兼容输入拒绝”。同时，Azure 应用注册应使用 `AzureADandPersonalMicrosoftAccount`：仅组织目录会在授权前报 `unauthorized_client`，仅个人账号会在当前 `/common` 验证链路中报 `AADSTS9002331`；若门户修改受支持账户类型时报 `api.requestedAccessTokenVersion is invalid`，需先在 Manifest 中将该值设为 `2`。
>
> 2026-04-16 会话回填：前端已落地新手快速指引（`guide-card` + 5 步 + 教程链接占位 + 折叠记忆），Scope UX 已调整为“前端默认 Graph 预设、后端 fallback 保持 IMAP 兼容预设”。

> 注：下方分阶段任务清单保留为最初实施拆解记录；当前会话已按兼容收口范围完成实现与文档同步，实际状态以 `WORKSPACE.md` 最新记录为准。

---

## 任务概览

| 阶段 | 任务数 | 状态 |
|------|-------:|------|
| Phase 0: 文档对齐收尾 | 2 | ✅ 已完成（会话收口） |
| Phase 1: 后端基础层（Config + Settings） | 4 | ✅ 已完成（会话收口） |
| Phase 2: Service 层核心（OAuth 核心逻辑） | 7 | ✅ 已完成（会话收口） |
| Phase 3: Service 层单元测试（TDD 先行） | 6 | ✅ 已完成（会话收口） |
| Phase 4: 后端路由层（Blueprint + Controller） | 6 | ✅ 已完成（会话收口） |
| Phase 5: API 集成测试 | 7 | ✅ 已完成（会话收口） |
| Phase 6: 前端实现 | 6 | ✅ 已完成（会话收口） |
| Phase 7: 联调与发布 | 5 | ✅ 已完成（会话收口） |

---

## Phase 0: 文档对齐收尾

> 目标：确保实现前所有文档引用一致，避免"文档写一套、代码做一套"。

### Task 0.1：验证 TDD URL 路径与 TD 一致

- [ ] TDD 中所有 API 路径使用 `/api/token-tool/*` 格式（已修正）
- [ ] 页面路径 `/token-tool`、回调 `/token-tool/callback` 保持不变

### Task 0.2：确认错误码策略

- [ ] 检查 TD §4.7 新增错误码（`OAUTH_STATE_MISMATCH`/`OAUTH_FLOW_EXPIRED`/`OAUTH_SCOPE_INVALID`）是否需要实现
- [ ] 若复用现有错误码，在 controller 中标注映射关系（如 `OAUTH_FLOW_EXPIRED` → `OAUTH_CODE_INVALID`）

---

## Phase 1: 后端基础层（Config + Settings）

> 目标：完成环境变量配置函数和 Settings 表 getter，为后续 Service/Controller 提供配置读取能力。
> 对应 TD §4.1 + §4.2

### Task 1.1：`outlook_web/config.py` — 新增 6 个环境变量函数

**文件**：`outlook_web/config.py`
**位置**：文件末尾（约 line 92 之后）

- [ ] `get_oauth_tool_enabled() -> bool` — 是否启用 Token 工具，默认 `True`
- [ ] `get_oauth_client_id_default() -> str` — 默认 Client ID
- [ ] `get_oauth_client_secret_default() -> str` — 默认 Client Secret
- [ ] `get_oauth_redirect_uri_default() -> str` — 默认 Redirect URI
- [ ] `get_oauth_scope_default() -> str` — 默认 Scope（后端 fallback：`offline_access https://outlook.office.com/IMAP.AccessAsUser.All`；前端首次展示 Graph 预设）
- [ ] `get_oauth_tenant_default() -> str` — 默认 Tenant（`consumers`）

**检查点**：
- [ ] 遵循现有 `_getenv()` + `env_true()` 模式
- [ ] 函数命名与 TD §4.1 一致

### Task 1.2：`outlook_web/repositories/settings.py` — 新增 6 个 OAuth Getter

**文件**：`outlook_web/repositories/settings.py`
**位置**：文件末尾

- [ ] `get_oauth_tool_client_id() -> str` — 优先级：Settings 表 > 环境变量
- [ ] `get_oauth_tool_client_secret() -> str` — 加密存储，getter 中调用 `decrypt_data()`
- [ ] `get_oauth_tool_redirect_uri() -> str` — 优先级：Settings 表 > 环境变量
- [ ] `get_oauth_tool_scope() -> str` — 优先级：Settings 表 > 环境变量
- [ ] `get_oauth_tool_tenant() -> str` — 优先级：Settings 表 > 环境变量
- [ ] `get_oauth_tool_prompt_consent() -> bool` — Settings 表 → 默认 `False`

**检查点**：
- [ ] `client_secret` 使用 `encrypt_data()` 加密后存储
- [ ] `get_oauth_tool_client_secret()` 返回解密后的值（调用 `decrypt_data()`）
- [ ] 优先级链正确：Settings 表非空值 > 环境变量默认值
- [ ] key 前缀统一为 `oauth_tool_`
- [ ] 共 6 个 getter（含 `prompt_consent`），与 TD §4.2 完全一致
- [ ] **不新增 batch save 函数** — 保存逻辑由 Controller `save_config()` 直接调用 `set_setting()` 实现（参照 TD §4.5）

### Task 1.3：`outlook_web/errors.py` — 补充错误码（可选）

**文件**：`outlook_web/errors.py`

- [ ] 评估是否需要新增 `OAUTH_STATE_MISMATCH`、`OAUTH_FLOW_EXPIRED`、`OAUTH_SCOPE_INVALID`
- [ ] 若新增：在英文字典（约 line 56 之后）和中文字典（约 line 102 之后）分别添加
- [ ] 若复用现有：在 Controller 代码中添加注释说明映射关系

### Task 1.4：验证 Phase 1 完整性

- [ ] 在 Python REPL 中导入所有新函数，确认无语法错误
- [ ] 设置环境变量 `OAUTH_TOOL_ENABLED=false`，验证 `get_oauth_tool_enabled()` 返回 `False`
- [ ] 设置环境变量 `OAUTH_CLIENT_ID=test`，验证优先级链

---

## Phase 2: Service 层核心（OAuth 核心逻辑）

> 目标：实现 `outlook_web/services/oauth_tool.py` — PKCE 生成、Scope 校验、FLOW_STORE、Token 交换、错误引导、JWT 解码。
> 对应 TD §4.6 完整伪代码。

### Task 2.1：PKCE 生成 — `generate_pkce()`

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `generate_pkce() -> Tuple[str, str]`
- [ ] `code_verifier`: `secrets.token_urlsafe(32)` — 长度 ≥ 43
- [ ] `code_challenge`: `base64url(SHA256(verifier))`，去除 `=` 填充
- [ ] 返回 `(code_verifier, code_challenge)`

### Task 2.2：Scope 校验与规范化

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `validate_scope(scope_value: str) -> Tuple[str, Optional[str]]` — 返回 `(normalized_scope, error_or_none)`
  - 检查至少有一个 API scope（非 `offline_access`/`openid`/`profile`/`email`）
  - 检查 `.default` 不与命名 scope 混用
  - 检查不跨资源（`graph.microsoft.com` 与 `outlook.office365.com` 不能同时出现）
  - 合法 → `(normalized, None)`；不合法 → `(scope_value, "错误信息")`
- [ ] `normalize_scope(scope_value: str) -> str` — 自动补 `offline_access`（如果缺失）

### Task 2.3：OAUTH_FLOW_STORE 实现

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] 模块级变量：`OAUTH_FLOW_STORE: Dict[str, Dict]`、`OAUTH_FLOW_LOCK: Lock`、`OAUTH_FLOW_TTL = 20 * 60`
- [ ] `store_oauth_flow(state: str, flow_data: dict)` — 加锁写入，同时 prune 过期条目
- [ ] `get_oauth_flow(state: str) -> Optional[dict]` — 加锁读取，检查 TTL
- [ ] `discard_oauth_flow(state: str)` — 加锁删除
- [ ] `_prune_expired()` — 内部函数，清理超过 TTL 的条目（必须在 LOCK 内调用）
- [ ] 每条 flow 存储 `created_at = time.time()`

### Task 2.4：授权 URL 构建 — `start_oauth_flow()`

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `start_oauth_flow(oauth_config: Dict[str, Any]) -> Tuple[Optional[str], str]`
  - 成功返回 `(authorize_url, state)`，失败返回 `(None, error_message)`
- [ ] 调用 `validate_scope()` 校验 scope（失败 → 返回 `(None, error)`）
- [ ] 调用 `generate_pkce()` 获取 verifier/challenge
- [ ] 生成 `state = secrets.token_urlsafe(24)`
- [ ] 调用 `store_oauth_flow(state, ...)` 存储 flow 数据（含 verifier、scope、redirect_uri、client_id、tenant、client_secret）
- [ ] 构建 Microsoft authorize URL（含 `code_challenge`、`code_challenge_method=S256`、`state`、`response_type=code`）
- [ ] 支持 `prompt_consent` 时添加 `prompt=consent` 参数

### Task 2.5：Token 交换 — `exchange_code_for_tokens()`

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `exchange_code_for_tokens(code: str, oauth_config: Dict, verifier: str) -> Tuple[Optional[Dict], Any]`
  - 成功返回 `(token_data_dict, None)`，失败返回 `(None, error_info)`
- [ ] 构建 POST body：`grant_type=authorization_code`、`code`、`code_verifier`、`redirect_uri`、`client_id`、`scope`
- [ ] 如果有 `client_secret`，加入 body
- [ ] 调用 `requests.post(TOKEN_URL, data=body, timeout=15)`
- [ ] 成功（200）：提取 `access_token`、`refresh_token`、`scope`、`expires_in`，调用 `_extract_token_data()` 整理
- [ ] 失败：调用 `_parse_error_response()` + `map_error_guidance()` 返回 `{"message": ..., "guidance": ...}`
- [ ] 网络异常：捕获 `requests.RequestException` 返回友好错误
- [ ] TOKEN_URL: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
- [ ] **注意**：flow 的消费（`discard_oauth_flow`）由 Controller 层负责，非 Service 层

### Task 2.6：错误引导映射 — `map_error_guidance()`

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `map_error_guidance(error_code: str) -> str`
- [ ] 映射表（至少覆盖）:
  - `unauthorized_client` → Azure 注册/Redirect URI 引导
  - `invalid_grant` → 授权码过期/重试引导
  - `invalid_scope` → scope 配置检查引导
  - `invalid_client` → Client Secret 检查引导
  - 未知错误 → 通用引导
- [ ] 返回中文引导文本

### Task 2.7：JWT Payload 解码 — `decode_jwt_payload()`

**文件**：`outlook_web/services/oauth_tool.py`

- [ ] `decode_jwt_payload(token: str) -> dict`
- [ ] 拆分 JWT（`header.payload.signature`），取 payload 部分
- [ ] Base64url 解码（自动补齐 `=` 填充）
- [ ] JSON 解析返回 dict
- [ ] 任何异常返回空 dict `{}`

---

## Phase 3: Service 层单元测试（TDD 先行）

> 目标：按 TDD 文档 §4.2~§4.7 编写 Service 层单元测试，确保 29 个用例全部通过。
> **TDD 原则**：先写测试 → 再确认 Phase 2 实现正确 → 红→绿→重构。

### Task 3.1：测试文件骨架 + 基类

**文件**：`tests/test_oauth_tool.py`

- [ ] 创建测试文件
- [ ] 实现 `OAuthToolTestBase`（setUpClass、setUp、helpers）
- [ ] 确认 `import_web_app_module()` 正常加载

### Task 3.2：PKCE 测试（4 个用例）

- [ ] `test_generate_pkce_verifier_length` — S-PKCE-01
- [ ] `test_generate_pkce_verifier_charset` — S-PKCE-02
- [ ] `test_generate_pkce_challenge_is_s256` — S-PKCE-03
- [ ] `test_generate_pkce_uniqueness` — S-PKCE-04

### Task 3.3：Scope 测试（7 个用例）

- [ ] `test_validate_scope_graph_default_ok` — S-SCOPE-01
- [ ] `test_validate_scope_imap_ok` — S-SCOPE-02
- [ ] `test_validate_scope_no_api_scope` — S-SCOPE-03
- [ ] `test_validate_scope_mixed_default_and_named` — S-SCOPE-04
- [ ] `test_validate_scope_cross_resource` — S-SCOPE-05
- [ ] `test_normalize_scope_auto_adds_offline_access` — S-SCOPE-06
- [ ] `test_normalize_scope_no_duplicate` — S-SCOPE-07

### Task 3.4：FLOW_STORE 测试（6 个用例）

- [ ] `test_flow_store_crud` — S-FLOW-01
- [ ] `test_flow_store_ttl_not_expired` — S-FLOW-02
- [ ] `test_flow_store_ttl_expired` — S-FLOW-03（Mock `time.time()`）
- [ ] `test_flow_store_cleanup_removes_expired_only` — S-FLOW-04
- [ ] `test_flow_store_thread_safety` — S-FLOW-05（多线程）
- [ ] `test_flow_store_get_nonexistent_key` — S-FLOW-06

### Task 3.5：错误引导 + JWT 测试（7 个用例）

- [ ] `test_map_unauthorized_client` — S-ERR-01
- [ ] `test_map_invalid_grant` — S-ERR-02
- [ ] `test_map_invalid_scope` — S-ERR-03
- [ ] `test_map_unknown_error` — S-ERR-04
- [ ] `test_decode_jwt_extracts_fields` — S-JWT-01
- [ ] `test_decode_jwt_invalid_format` — S-JWT-02
- [ ] `test_decode_jwt_missing_padding` — S-JWT-03

### Task 3.6：Token 交换 Service 测试（5 个用例）

- [ ] `test_exchange_token_success` — S-EXCH-01（Mock `requests.post`）
- [ ] `test_exchange_token_invalid_grant` — S-EXCH-02
- [ ] `test_exchange_token_network_timeout` — S-EXCH-03
- [ ] `test_exchange_token_validates_state` — S-EXCH-04
- [ ] `test_exchange_token_consumes_flow` — S-EXCH-05

**Phase 3 验收标准**：
- [ ] `python -m pytest tests/test_oauth_tool.py -v -k "Pkce or Scope or FlowStore or ErrorGuidance or JwtDecode or TokenExchange"` — 29 passed

---

## Phase 4: 后端路由层（Blueprint + Controller）

> 目标：实现 Blueprint 定义、8 个 Controller 函数、app.py 条件注册。
> 对应 TD §4.3 + §4.4 + §4.5

### Task 4.1：`outlook_web/routes/token_tool.py` — Blueprint 定义

**文件**：`outlook_web/routes/token_tool.py`

- [ ] `create_blueprint() -> Blueprint`
- [ ] 8 个路由注册（参照 TD §4.4）:
  - `GET /token-tool` → `render_page`
  - `POST /api/token-tool/prepare` → `prepare_oauth`
  - `GET /token-tool/callback` → `handle_callback`
  - `POST /api/token-tool/exchange` → `exchange_token`
  - `POST /api/token-tool/save` → `save_to_account`
  - `GET /api/token-tool/accounts` → `get_account_list`
  - `GET /api/token-tool/config` → `get_config`
  - `POST /api/token-tool/config` (endpoint=`save_config`) → `save_config`

### Task 4.2：`outlook_web/controllers/token_tool.py` — 页面渲染 + 配置读写

**文件**：`outlook_web/controllers/token_tool.py`

- [ ] `render_page()` — 渲染 `token_tool.html`（不检查动态开关，开关仅在 Blueprint 注册阶段生效）
- [ ] `get_config()` — `@login_required`，读取配置并脱敏 client_secret 返回
- [ ] `save_config()` — `@login_required`，接收 JSON，逐字段调用 `set_setting()` 保存（`client_secret` 先 `encrypt_data()`）

### Task 4.3：`outlook_web/controllers/token_tool.py` — OAuth 流程

- [ ] `prepare_oauth()` — `@login_required`，接收参数 → 调用 `service.start_oauth_flow()` → 返回 auth_url
- [ ] `handle_callback()` — 渲染 `popup_result.html`，将 `code`/`state` 参数传入模板
- [ ] `exchange_token()` — `@login_required`，接收 state + code → 从 `get_oauth_flow()` 获取 flow → 调用 `service.exchange_code_for_tokens()` → 成功后 `discard_oauth_flow()` → 返回结果

### Task 4.4：`outlook_web/controllers/token_tool.py` — 账号操作

- [ ] `save_to_account()` — `@login_required`
  - 接收 `account_id`(可选)、`email`(可选)、`client_id`、`refresh_token`
  - Mock `test_refresh_token_with_rotation()` 验证 token 有效性
  - 有 `account_id` → `get_account_by_id()` → `update_account()`（回传必填字段）
  - 无 `account_id` → `add_account()`
- [ ] `get_account_list()` — `@login_required`
  - 调用 `load_accounts()` → 提取 4 个非敏感字段（`id`、`email`、`status`、`account_type`）
  - 仅返回 `account_type` 为 `outlook` 或 `None` 的账号

### Task 4.5：`outlook_web/app.py` — 条件注册 Blueprint

**文件**：`outlook_web/app.py`

- [ ] 新增 import: `from outlook_web import config as app_config`
- [ ] 条件注册（约 line 150 之后）:
  ```python
  if app_config.get_oauth_tool_enabled():
      from outlook_web.routes import token_tool
      app.register_blueprint(token_tool.create_blueprint())
  ```
- [ ] Context Processor 扩展:
  ```python
  "OAUTH_TOOL_ENABLED": app_config.get_oauth_tool_enabled(),
  ```

### Task 4.6：动态开关 vs 静态注册决策

> **关键**：TDD §7.2 指出 Blueprint 条件注册在 `create_app()` 阶段，后续无法动态改变。
> 需要在 Controller 层添加动态开关检查以支持测试。

- [ ] `render_page()` 中添加: `if not app_config.get_oauth_tool_enabled(): abort(404)`
- [ ] 或评估是否 Controller 统一前置检查（decorator 或 `before_request`）

---

## Phase 5: API 集成测试

> 目标：按 TDD §4.8~§4.13 编写 API 集成测试，确保 28 个用例全部通过。

### Task 5.1：prepare 端点测试（5 个用例）

- [ ] `test_prepare_returns_auth_url` — A-PREP-01
- [ ] `test_prepare_invalid_scope_rejected` — A-PREP-02
- [ ] `test_prepare_missing_client_id` — A-PREP-03
- [ ] `test_prepare_requires_login` — A-PREP-04
- [ ] `test_prepare_stores_flow` — A-PREP-05

### Task 5.2：exchange 端点测试（5 个用例）

- [ ] `test_exchange_success` — A-EXCH-01（完整 prepare → exchange 链路）
- [ ] `test_exchange_missing_state` — A-EXCH-02
- [ ] `test_exchange_expired_flow` — A-EXCH-03
- [ ] `test_exchange_missing_code` — A-EXCH-04
- [ ] `test_exchange_requires_login` — A-EXCH-05

### Task 5.3：config 端点测试（5 个用例）

- [ ] `test_config_save_and_load` — A-CFG-01
- [ ] `test_config_secret_encrypted_in_db` — A-CFG-02
- [ ] `test_config_load_returns_masked_secret` — A-CFG-03
- [ ] `test_config_env_override` — A-CFG-04
- [ ] `test_config_requires_login` — A-CFG-05

### Task 5.4：save 端点测试（6 个用例）

- [ ] `test_save_update_existing_account` — A-SAVE-01
- [ ] `test_save_create_new_account` — A-SAVE-02
- [ ] `test_save_validates_refresh_token` — A-SAVE-03
- [ ] `test_save_nonexistent_account_id` — A-SAVE-04
- [ ] `test_save_preserves_account_fields` — A-SAVE-05（**关键**: 验证 update_account 必填参数回传）
- [ ] `test_save_requires_login` — A-SAVE-06

### Task 5.5：Blueprint 开关测试（3 个用例）

- [ ] `test_token_tool_page_accessible_when_enabled` — A-BP-01
- [ ] `test_token_tool_disabled_returns_404` — A-BP-02（Mock `get_oauth_tool_enabled`）
- [ ] `test_token_tool_api_disabled_returns_404` — A-BP-03

### Task 5.6：账号列表测试（4 个用例）

- [ ] `test_accounts_list_returns_non_sensitive_fields` — A-LIST-01
- [ ] `test_accounts_list_excludes_sensitive_fields` — A-LIST-02
- [ ] `test_accounts_list_empty` — A-LIST-03
- [ ] `test_accounts_list_requires_login` — A-LIST-04

### Task 5.7：全量测试验证

- [ ] `python -m pytest tests/test_oauth_tool.py -v` — 57 passed（29 单元 + 28 集成）
- [ ] 回归测试: `python -m pytest tests -q --ignore=tests/test_import_and_fetch.py --ignore=tests/test_live_credentials.py --ignore=tests/test_tc01_real.py --ignore=tests/test_banner_show.py --ignore=tests/test_acceptance.py --ignore=tests/manual_acceptance_settings_tab.py --ignore=tests/e2e_version_update.py` — 无新增失败

---

## Phase 6: 前端实现

> 目标：实现独立页面模板、回调页、JS 逻辑、CSS 样式、侧边栏入口。
> 对应 TD §5.1~§5.4

### Task 6.1：`templates/token_tool.html` — 独立页面模板

**文件**：`templates/token_tool.html`

- [ ] 独立模板（不继承 base，与 `login.html` 同模式）
- [ ] 包含配置表单区域（Client ID、Tenant ID、Scope、Redirect URI、Client Secret）
- [ ] Scope 预设按钮（Graph 邮件 / IMAP）
- [ ] 授权启动按钮
- [ ] Token 结果展示区
- [ ] 账号选择/写入区
- [ ] 手动粘贴回调 URL 输入区
- [ ] 引入 `static/js/features/token_tool.js` + `static/css/token_tool.css`
- [ ] Meta 标签注入 CSRF token: `<meta name="csrf-token" content="{{ csrf_token() }}">`
- [ ] 静态资源版本号: `?v={{ APP_VERSION }}`

### Task 6.2：`templates/popup_result.html` — 回调结果页

**文件**：`templates/popup_result.html`

- [ ] 显示授权结果（成功/失败）
- [ ] 成功时：显示"请复制以下 URL 粘贴到主页面"提示
- [ ] 提供一键复制当前 URL 按钮
- [ ] 失败时：显示 Microsoft 返回的错误信息

### Task 6.3：`static/js/features/token_tool.js` — 前端逻辑

**文件**：`static/js/features/token_tool.js`

- [ ] 配置保存/加载（`fetch('/api/token-tool/config', ...)`）
- [ ] Scope 预设按钮事件（填充 Graph / IMAP scope）
- [ ] 授权启动（`fetch('/api/token-tool/prepare', ...)` → `window.open(auth_url)`）
- [ ] 手动粘贴 URL 换取 Token（`fetch('/api/token-tool/exchange', ...)`）
- [ ] Token 结果展示（access_token 截断显示 + refresh_token 完整 + JWT 解码信息）
- [ ] 账号列表加载（`fetch('/api/token-tool/accounts', ...)`）
- [ ] 写入账号（`fetch('/api/token-tool/save', ...)`）
- [ ] CSRF token 从 meta 标签读取，附加到所有 POST 请求头

### Task 6.4：`static/css/token_tool.css` — 页面样式

**文件**：`static/css/token_tool.css`

- [ ] 与现有主题风格一致（参考 `login.html` 样式）
- [ ] 响应式布局
- [ ] 配置表单、结果展示、账号选择区域布局

### Task 6.5：`templates/index.html` — 侧边栏入口

**文件**：`templates/index.html`

- [ ] 在侧边栏添加"Token 工具"入口链接
- [ ] 使用 `{{ OAUTH_TOOL_ENABLED }}` 条件渲染（开关关闭时不显示）
- [ ] 点击使用 `window.open('/token-tool', ...)` 打开新窗口

### Task 6.6：前端手动验收

- [ ] M-01: localhost 完整 OAuth 流程
- [ ] M-02: Docker 部署手动粘贴
- [ ] M-03: 配置保存/加载
- [ ] M-04: Scope 预设按钮
- [ ] M-05: 写入已有账号
- [ ] M-06: 创建新账号
- [ ] M-07: 开关关闭
- [ ] M-08: 错误引导

---

## Phase 7: 联调与发布

> 目标：全量测试通过、文档更新、版本发布准备。

### Task 7.1：全量测试

- [ ] `python -m pytest tests/test_oauth_tool.py -v` — 57 passed
- [ ] 回归测试（排除 live 用例）— 无新增失败
- [ ] Docker 构建验证: `docker build -t test-oauth-tool .`

### Task 7.2：文档更新

- [ ] `CHANGELOG.md` — 新增 v1.15.0 记录
- [ ] `README.md` / `README.en.md` — 新增功能说明
- [ ] `.env.example`（如有）— 新增 `OAUTH_TOOL_ENABLED`、`OAUTH_CLIENT_ID` 等变量

### Task 7.3：Docker 配置更新

- [ ] `docker-compose.yml` — 新增环境变量示例（注释形式）
- [ ] `Dockerfile` — 确认无额外依赖需要安装

### Task 7.4：WORKSPACE.md 操作记录

- [ ] 记录完整实施过程到 WORKSPACE.md

### Task 7.5：版本发布

- [ ] 版本号更新: `outlook_web/__init__.py` → v1.15.0
- [ ] 更新 `tests/test_version_update.py` 版本断言
- [ ] Git tag + Push
- [ ] CI 验证通过

---

## 依赖关系

```
Phase 0 ──────────────────────────────────────────────────────┐
                                                               ↓
Phase 1 (Config + Settings) ───────────────────────────┬──→ Phase 4 (Blueprint + Controller)
                                                       │              ↓
Phase 2 (Service 核心) ──→ Phase 3 (Service 测试) ─────┘       Phase 5 (API 集成测试)
                                                                       ↓
                                                               Phase 6 (前端实现)
                                                                       ↓
                                                               Phase 7 (联调发布)
```

**关键路径**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7

**可并行**:
- Phase 1 + Phase 2 可部分并行（config 先完成后 service 可开始）
- Phase 6.1~6.4（前端模板/JS/CSS）可在 Phase 4 完成后与 Phase 5 并行
- Phase 3 与 Phase 4 部分可交替推进（TDD 红绿循环）

---

## 风险提醒

| 风险 | 影响 | 缓解 | 关联 Phase |
|------|------|------|-----------|
| `update_account()` 必填参数 | save 更新时传 None 导致 return False | 先 `get_account_by_id()` 获取再回传 | Phase 4 Task 4.4 |
| Blueprint 条件注册不可动态关闭 | 测试中无法 mock 开关 | Controller 层添加动态检查 | Phase 4 Task 4.6 |
| `requests.post` Mock 路径 | Mock 失效导致真实网络调用 | 实现确定后统一校准 TDD 伪代码 | Phase 3 |
| FLOW_STORE 测试间污染 | 前一个测试的 state 影响后续 | 每个用例使用 UUID 前缀 key | Phase 3 Task 3.4 |
| Microsoft OAuth 端点超时 | 用户长时间等待 | `timeout=15` + 友好错误提示 | Phase 2 Task 2.5 |

---

**文档结束**
