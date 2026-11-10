# FD: OAuth Token 获取工具

- 文档版本: v1.2
- 创建日期: 2026-04-12
- 更新日期: 2026-04-16（v1.2 — 会话文档按实际实现口径再同步）
- 关联 PRD: `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`
- 关联 TD: `docs/TD/2026-04-12-OAuth-Token获取工具TD.md`
- 当前范围: 功能设计,定义系统行为、接口契约、数据流、前后端交互

> **v1.15.0 实施收口说明（兼容账号导入模式）**
>
> 当前功能设计已收敛为“兼容账号导入模式”：
> - Tenant 固定 `consumers`
> - `client_secret` 禁用且不参与流程
> - 前端默认推荐 Graph Scope（系统邮件读取主链路）；后端环境变量 fallback 保持 IMAP 兼容 Scope
> - `prepare / config / save` 接口均需拒绝不兼容输入
> - Azure 应用注册应使用 **Accounts in any identity provider or organizational directory and personal Microsoft accounts**；仅组织目录应用会命中 `unauthorized_client`，仅个人账号应用会在当前 `/common` 验证链路中命中 `AADSTS9002331`
> - 若门户修改受支持账户类型时报 `api.requestedAccessTokenVersion is invalid`，应先在 Manifest 中将 `api.requestedAccessTokenVersion` 设为 `2`
> - 2026-04-16 已实现：`guide-card`（HTML 原生 details）+ 本地折叠状态记忆 + 教程链接占位
>
> 下文若仍出现可变 tenant、可选 `client_secret` 或机密客户端场景描述，均视为历史方案背景，不再代表当前实现契约。

---

## 1. 功能定义

### 1.1 核心功能

在系统内提供一个独立的 OAuth Token 获取工具,以**浏览器新窗口**形式打开,用户可交互式登录 Microsoft 账号,获取 `refresh_token`,并一键写入系统账号。

1. **独立窗口**: 从主界面侧边栏点击打开,`window.open()` 方式,不影响主页面 SPA 状态
2. **OAuth2 + PKCE**: Authorization Code Flow with PKCE (S256)，兼容模式固定禁用 `client_secret`
3. **智能回调**: 优先自动回调,远程部署场景降级为手动粘贴回调 URL
4. **一键写入**: 获取 token 后可写入已有账号或创建新账号
5. **配置持久化**: OAuth 参数保存到服务端 Settings 表,跨设备同步

### 1.2 功能边界

**本期包含**:
- ✅ 独立 Blueprint (`token_tool`)，环境变量开关控制注册
- ✅ 独立 Jinja2 模板 (`token_tool.html`)
- ✅ OAuth2 Authorization Code + PKCE 完整流程
- ✅ 弹窗模式 + 手动粘贴降级
- ✅ Token 结果展示 + 一键复制
- ✅ 写入已有账号 / 创建新账号
- ✅ Scope chips UI + 预设按钮
- ✅ Azure 注册指引折叠卡片
- ✅ 常见错误中文引导
- ✅ 兼容模式约束校验（固定 `tenant=consumers`）
- ✅ 配置持久化到 Settings 表

**本期不包含**:
- ❌ 批量 token 获取向导
- ❌ Token 到期预警
- ❌ IMAP Token 获取快捷模式
- ❌ 内置默认 client_id

---

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  独立窗口 (token_tool.html)                                   │
│  - window.open('/token-tool') 从主页面打开                     │
│  - 独立的 Jinja2 模板,不依赖 index.html                       │
│  - 原生 JS (static/js/features/token_tool.js)                │
└────────────────────┬────────────────────────────────────────┘
                     │ fetch API
┌────────────────────▼────────────────────────────────────────┐
│  Route Layer (routes/token_tool.py)                          │
│  - GET  /token-tool             渲染工具页面                   │
│  - POST /api/token-tool/prepare 生成授权URL                   │
│  - GET  /token-tool/callback    自动回调处理                   │
│  - POST /api/token-tool/exchange 手动粘贴换取                  │
│  - POST /api/token-tool/save    写入系统账号                   │
│  - GET  /api/token-tool/accounts 获取可写入账号列表             │
│  - GET  /api/token-tool/config  获取保存的配置                  │
│  - POST /api/token-tool/config  保存配置                      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Controller Layer (controllers/token_tool.py)                │
│  - prepare_oauth()        构建授权参数,调用 Service            │
│  - handle_callback()      处理回调,提取 code & state          │
│  - exchange_token()       手动粘贴 URL 换取                   │
│  - save_to_account()      写入账号（新增/更新）                 │
│  - get_account_list()     返回可选账号列表                     │
│  - get_config/save_config 配置 CRUD                          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Service Layer (services/oauth_tool.py)                      │
│  - generate_pkce()         PKCE code_verifier + challenge    │
│  - start_oauth_flow()      构建授权 URL + 存储 flow state     │
│  - complete_oauth_callback() state 校验 + code→token 换取     │
│  - exchange_code_for_tokens() 向 Microsoft 发 POST 请求       │
│  - validate_scope()        Scope 合法性校验                    │
│  - normalize_scope()       Scope 标准化 + 自动补 offline_access│
│  - decode_jwt_payload()    不验签解码 JWT（展示用）              │
│  - map_error_guidance()    错误码→中文引导映射                  │
│  - OAUTH_FLOW_STORE        内存状态存储（线程安全 + TTL）        │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Repository Layer                                            │
│  - accounts.py         账号 CRUD（复用现有）                   │
│  - settings.py         配置读写（复用现有）                    │
│  已有能力:                                                    │
│  - graph.py            test_refresh_token_with_rotation()    │
│  - crypto.py           encrypt_data() / decrypt_data()       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
outlook_web/
├── routes/
│   └── token_tool.py           # Blueprint 路由定义（新增）
├── controllers/
│   └── token_tool.py           # 控制器（新增）
├── services/
│   └── oauth_tool.py           # OAuth 核心逻辑（新增）
templates/
│   └── token_tool.html         # 独立页面模板（新增）
static/
├── js/features/
│   └── token_tool.js           # 前端逻辑（新增）
├── css/
│   └── token_tool.css          # 页面样式（新增,可选独立或合入 main.css）
```

---

## 3. 数据流

### 3.1 标准 OAuth 流程（本地部署）

```
用户 ──→ Token 工具页面 ──→ 点击「登录 Microsoft」
                │
                ▼
        POST /api/token-tool/prepare
        Body: { client_id, client_secret, redirect_uri, scope, tenant, prompt_consent }
                │
                ▼
        Service: start_oauth_flow()
        1. validate_scope(scope)
        2. generate_pkce() → verifier + challenge
        3. state = secrets.token_urlsafe(24)
        4. OAUTH_FLOW_STORE[state] = { client_id, client_secret, redirect_uri, scope, verifier, created_at }
        5. session["oauth_state"] = state
        6. 构建 authorize_url = https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?...
                │
                ▼
        返回 { authorize_url } → 前端 window.open(authorize_url) 打开 OAuth 弹窗
                │
                ▼
        用户在 Microsoft 页面登录 + 授权
                │
                ▼
        Microsoft 重定向到 redirect_uri?code=xxx&state=xxx
                │
                ▼
        GET /token-tool/callback?code=xxx&state=xxx
                │
                ▼
        Controller: handle_callback()
        1. 提取 code, state, error
        2. 如果 error → 渲染 popup_result.html（错误提示 + 关闭按钮）
        3. 渲染 popup_result.html（成功提示 + "请复制地址栏 URL" + 复制按钮 + 关闭按钮）
                │
                ▼
        用户复制回调 URL → 粘贴到 Token 工具页面「手动换取」区域
                │
                ▼
        POST /api/token-tool/exchange
        Body: { callback_url }
                │
                ▼
        Service: complete_oauth_callback()
        1. 从 URL 解析 code, state
        2. 校验 session["oauth_state"] == state
        3. 从 OAUTH_FLOW_STORE 取回 flow_data
        4. exchange_code_for_tokens(code, oauth_config, verifier)
        5. decode_jwt_payload(access_token) → audience, scope_claim
        6. 清理 session + OAUTH_FLOW_STORE
                │
                ▼
        返回 { refresh_token, access_token, granted_scope, audience, ... }
                │
                ▼
        前端展示结果 → 用户点击「写入到账号」
                │
                ▼
        POST /api/token-tool/save
        Body: { mode: "update"|"create", account_id?, email?, refresh_token, client_id }
                │
                ▼
        Service: 验证 token 有效性 → 写入 accounts 表
```

### 3.2 远程部署场景（Docker/反代）

与标准流程相同,区别在于:

- 步骤中 Microsoft 回调到 `http://localhost:xxx`（浏览器无法访问）
- OAuth 弹窗页面显示错误（打不开）
- 用户从浏览器地址栏复制完整 URL（包含 `?code=xxx&state=xxx`）
- 粘贴到 Token 工具页面的「手动换取」区域
- 后续流程相同

### 3.3 回调页面设计（popup_result.html）

OAuth 弹窗被 Microsoft 重定向后,渲染一个简单的结果页面:

**成功时**:
```
┌──────────────────────────────┐
│  ✓ 授权成功                    │
│                              │
│  请复制当前地址栏的完整 URL,    │
│  粘贴到 Token 工具页面         │
│                              │
│  [📋 复制回调地址]  [✕ 关闭]   │
└──────────────────────────────┘
```

**失败时**:
```
┌──────────────────────────────┐
│  ⓘ 授权未完成                  │
│                              │
│  错误: unauthorized_client    │
│  建议: 请到 Azure 门户...      │
│                              │
│  [✕ 关闭]                     │
└──────────────────────────────┘
```

---

## 4. 接口设计

### 4.1 `GET /token-tool` — 渲染页面

**认证**: `@login_required`

**行为**:
- 检查 `OAUTH_TOOL_ENABLED`,若为 `false` 返回 404
- 渲染 `token_tool.html` 模板
- 注入 `APP_VERSION` 等上下文变量

**响应**: HTML 页面

---

### 4.2 `POST /api/token-tool/prepare` — 生成授权 URL

**认证**: `@login_required`

**请求**:
```json
{
  "client_id": "xxx-xxx-xxx",
  "client_secret": "",
  "redirect_uri": "http://localhost:5000/token-tool/callback",
  "scope": "offline_access https://graph.microsoft.com/.default",
  "tenant": "consumers",
  "prompt_consent": false
}
```

**响应 (成功)**:
```json
{
  "success": true,
  "data": {
    "authorize_url": "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_id=xxx&..."
  }
}
```

**响应 (失败 — scope 校验)**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_SCOPE",
    "message": "同一次请求里,`.default` scope 不能和命名 scope 混用。"
  }
}
```

**校验规则**:
1. `client_id` 非空
2. `redirect_uri` 必须是完整的 `http(s)://` 地址
3. Scope 校验: 至少一个 API scope,不允许 `.default` 与命名 scope 混用,不允许跨资源
4. 自动补 `offline_access`

---

### 4.3 `GET /token-tool/callback` — 自动回调处理

**认证**: 通过 Session 中的 `oauth_state` 验证

**参数**: Query String `?code=xxx&state=xxx` 或 `?error=xxx&error_description=xxx`

**行为**:
- 渲染 `popup_result.html`
- 成功时: 显示"请复制回调地址"指引 + 复制按钮
- 失败时: 显示错误信息 + 引导建议

**不在此处直接换取 token**,仅展示回调结果页。用户复制 URL 后在 Token 工具主页面通过 `/exchange` 接口换取。

**理由**: 回调页运行在 OAuth 弹窗中,无法直接操作 Token 工具主页面。采用"复制 URL → 手动粘贴"方式统一处理所有部署场景,逻辑简单可靠。

---

### 4.4 `POST /api/token-tool/exchange` — 换取 Token

**认证**: `@login_required`

**请求**:
```json
{
  "callback_url": "http://localhost:5000/token-tool/callback?code=xxx&state=xxx&session_state=xxx"
}
```

**响应 (成功)**:
```json
{
  "success": true,
  "data": {
    "refresh_token": "0.AXEA...",
    "access_token": "eyJ0eXAi...",
    "expires_in": 3600,
    "token_type": "Bearer",
    "requested_scope": "offline_access https://graph.microsoft.com/.default",
    "granted_scope": "offline_access Mail.Read User.Read",
    "audience": "https://graph.microsoft.com",
    "scope_claim": "Mail.Read User.Read",
    "roles_claim": "",
    "client_id": "xxx-xxx-xxx",
    "redirect_uri": "http://localhost:5000/token-tool/callback"
  }
}
```

**响应 (失败)**:
```json
{
  "success": false,
  "error": {
    "code": "OAUTH_EXCHANGE_FAILED",
    "message": "换取 Token 失败",
    "detail": "unauthorized_client: ...",
    "guidance": "请到 Azure 门户 → 身份验证 → 高级设置 → 开启『允许公共客户端流』"
  }
}
```

**处理流程**:
1. 从 `callback_url` 解析 `code` 和 `state`
2. 校验 `state` == `session["oauth_state"]`
3. 从 `OAUTH_FLOW_STORE` 取回 flow_data（含 verifier、client_id 等）
4. 调用 Microsoft token endpoint 换取 token
5. 解码 access_token JWT 提取诊断信息
6. 清理 session 和 OAUTH_FLOW_STORE
7. 返回完整结果

---

### 4.5 `POST /api/token-tool/save` — 写入系统账号

**认证**: `@login_required`

**请求 (更新已有账号)**:
```json
{
  "mode": "update",
  "account_id": 123,
  "refresh_token": "0.AXEA...",
  "client_id": "xxx-xxx-xxx"
}
```

**请求 (创建新账号)**:
```json
{
  "mode": "create",
  "email": "user@outlook.com",
  "refresh_token": "0.AXEA...",
  "client_id": "xxx-xxx-xxx"
}
```

**响应 (成功)**:
```json
{
  "success": true,
  "data": {
    "account_id": 123,
    "email": "user@outlook.com",
    "status": "active",
    "token_valid": true
  }
}
```

**处理流程**:
1. 校验参数完整性
2. 调用 `test_refresh_token_with_rotation()` 验证 token 有效性
3. `mode=update`: 更新 accounts 表的 `refresh_token` + `client_id`,状态恢复 `active`
4. `mode=create`: 新增 accounts 记录,`account_type=outlook`,`status=active`
5. `refresh_token` 使用 `encrypt_data()` 加密存储

---

### 4.6 `GET /api/token-tool/accounts` — 获取可写入账号列表

**认证**: `@login_required`

**响应**:
```json
{
  "success": true,
  "data": [
    { "id": 1, "email": "user1@outlook.com", "status": "active", "account_type": "outlook" },
    { "id": 2, "email": "user2@hotmail.com", "status": "inactive", "account_type": "outlook" }
  ]
}
```

**说明**: 返回所有 `account_type=outlook` 的账号（含 inactive），供用户选择更新 token。

---

### 4.7 `GET /api/token-tool/config` — 获取保存的配置

**认证**: `@login_required`

**响应**:
```json
{
  "success": true,
  "data": {
    "client_id": "xxx-xxx-xxx",
    "client_secret": "",
    "redirect_uri": "http://localhost:5000/token-tool/callback",
    "scope": "offline_access https://graph.microsoft.com/.default",
    "tenant": "consumers",
    "prompt_consent": false
  }
}
```

**说明**: 从 Settings 表读取,key 前缀 `oauth_tool_`。环境变量作为默认值,Settings 表的值优先。

---

### 4.8 `POST /api/token-tool/config` — 保存配置

**认证**: `@login_required`

**请求**:
```json
{
  "client_id": "xxx-xxx-xxx",
  "client_secret": "",
  "redirect_uri": "http://localhost:5000/token-tool/callback",
  "scope": "offline_access https://graph.microsoft.com/.default",
  "tenant": "consumers",
  "prompt_consent": false
}
```

**响应**:
```json
{
  "success": true,
  "message": "配置已保存"
}
```

**说明**: 写入 Settings 表时，`client_secret` 固定写空；`tenant` 固定写 `consumers`。

---

## 5. OAuth 核心逻辑设计

### 5.1 PKCE 生成

```python
def generate_pkce():
    """生成 PKCE code_verifier + code_challenge (S256)"""
    verifier = secrets.token_urlsafe(64)  # 64 字节随机
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
```

### 5.2 OAuth Flow State 管理

```python
OAUTH_FLOW_STORE = {}          # { state: { created_at, client_id, verifier, ... } }
OAUTH_FLOW_LOCK = Lock()       # 线程安全
OAUTH_FLOW_TTL = 20 * 60       # 20 分钟过期

def store_oauth_flow(state, flow_data):
    """存储 OAuth 流程数据（自动清理过期条目）"""
    with OAUTH_FLOW_LOCK:
        _prune_expired()
        OAUTH_FLOW_STORE[state] = {"created_at": time.time(), **flow_data}

def get_oauth_flow(state):
    """获取 OAuth 流程数据（自动清理过期条目）"""
    with OAUTH_FLOW_LOCK:
        _prune_expired()
        data = OAUTH_FLOW_STORE.get(state)
        return dict(data) if data else None

def discard_oauth_flow(state):
    """清理指定 state 的流程数据"""
    with OAUTH_FLOW_LOCK:
        OAUTH_FLOW_STORE.pop(state, None)
```

**关键约束**:
- 内存存储,单进程安全（Flask 默认单 worker 或 threaded 模式兼容）
- Docker 部署需确保 `workers=1`（已有约束,与现有 gunicorn 配置一致）
- 每次读写自动清理过期条目

### 5.3 授权 URL 构建

```python
def start_oauth_flow(oauth_config):
    """
    生成 Microsoft OAuth 授权 URL
    
    Returns:
        (authorize_url, state) 或 (None, error_message)
    """
    # 1. 校验 scope
    normalized_scope, scope_error = validate_scope(oauth_config["scope"])
    if scope_error:
        return None, scope_error
    
    # 2. 生成 PKCE
    verifier, challenge = generate_pkce()
    
    # 3. 生成 state
    state = secrets.token_urlsafe(24)
    
    # 4. 存储 flow data
    store_oauth_flow(state, {
        "client_id": oauth_config["client_id"],
        "client_secret": oauth_config.get("client_secret", ""),
        "redirect_uri": oauth_config["redirect_uri"],
        "scope": normalized_scope,
        "verifier": verifier,
    })
    
    # 5. 构建授权 URL
    tenant = oauth_config.get("tenant", "consumers")
    authority = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    params = {
        "client_id": oauth_config["client_id"],
        "response_type": "code",
        "redirect_uri": oauth_config["redirect_uri"],
        "scope": normalized_scope,
        "response_mode": "query",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if oauth_config.get("prompt_consent"):
        params["prompt"] = "consent"
    
    authorize_url = f"{authority}/authorize?{urlencode(params)}"
    return authorize_url, state
```

### 5.4 Token 换取

```python
def exchange_code_for_tokens(code, oauth_config, verifier):
    """
    用授权码换取 token
    
    Returns:
        (token_data_dict, None) 或 (None, error_message)
    """
    tenant = oauth_config.get("tenant", "consumers")
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    
    payload = {
        "client_id": oauth_config["client_id"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth_config["redirect_uri"],
        "code_verifier": verifier,
        "scope": oauth_config["scope"],
    }
    if oauth_config.get("client_secret"):
        payload["client_secret"] = oauth_config["client_secret"]
    
    try:
        resp = requests.post(token_url, data=payload, timeout=15)
    except requests.RequestException as exc:
        return None, f"无法连接 Microsoft 服务器: {exc}"
    
    if resp.status_code != 200:
        error_detail = _parse_error_response(resp)
        guidance = map_error_guidance(error_detail)
        return None, {"message": error_detail, "guidance": guidance}
    
    tokens = resp.json()
    return _extract_token_data(tokens, oauth_config), None
```

### 5.5 Scope 校验

```python
OIDC_SCOPES = {"openid", "profile", "email", "offline_access"}

def validate_scope(scope_value):
    """
    校验 scope 合法性
    
    Returns:
        (normalized_scope, None) 或 (None, error_message)
    """
    normalized = normalize_scope(scope_value)
    scopes = normalized.split()
    api_scopes = [s for s in scopes if s not in OIDC_SCOPES]
    
    if not api_scopes:
        return None, "至少需要一个 API scope（如 https://graph.microsoft.com/.default）"
    
    # .default 和命名 scope 不能混用
    has_default = any(s.endswith("/.default") for s in api_scopes)
    has_named = any(not s.endswith("/.default") for s in api_scopes)
    if has_default and has_named:
        return None, "同一次请求里,`.default` scope 不能和命名 scope 混用"
    
    # 不允许跨资源
    resources = {_scope_resource(s) for s in api_scopes if _scope_resource(s)}
    if len(resources) > 1:
        return None, "一次 OAuth 请求只能对应一个资源,请分开获取"
    
    return normalized, None
```

### 5.6 错误引导映射

```python
ERROR_GUIDANCE_MAP = {
    "unauthorized_client": "请到 Azure 门户 → 身份验证 → 高级设置 → 开启『允许公共客户端流』",
    "aadsts70000": "请求 scope 未授权或已失效。请确认 Graph 权限（offline_access/Mail.Read/User.Read）已添加，并使用强制 Consent 重新授权后再写入",
    "invalid_grant": "授权码已过期或已使用,请重新点击『登录 Microsoft』",
    "invalid_scope": "请到 Azure 门户 → API 权限 → 添加对应的 Microsoft Graph 委托权限",
    "redirect_uri_mismatch": "回调地址不匹配,请确认 Azure 门户中注册的重定向 URI 与当前填写的一致",
    "interaction_required": "请勾选『强制 Consent』后重新授权",
    "consent_required": "此权限需要组织管理员同意,请联系 IT 管理员或切换为个人账号",
}

def map_error_guidance(error_detail):
    """根据错误信息匹配引导建议"""
    for key, guidance in ERROR_GUIDANCE_MAP.items():
        if key in error_detail.lower():
            return guidance
    return "请检查配置后重试,如持续失败请参考 Azure 注册指引"
```

---

## 6. 前端设计

### 6.1 页面模板 (`token_tool.html`)

独立的 Jinja2 模板,不依赖 `index.html`,包含:

```html
<!DOCTYPE html>
<html>
<head>
  <title>Token 获取工具 - OutlookEmailPlus</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/token_tool.css') }}">
</head>
<body>
  <!-- 快速指引卡片（可折叠） -->
  <details id="guide-card" open>...</details>
  
  <!-- OAuth 配置表单 -->
  <section id="config-form">...</section>
  
  <!-- 手动回调区（可折叠） -->
  <section id="manual-exchange">...</section>
  
  <!-- 结果展示区 -->
  <section id="result-panel">...</section>
  
  <!-- 写入账号弹窗 -->
  <dialog id="save-dialog">...</dialog>
  
  <script src="{{ url_for('static', filename='js/features/token_tool.js') }}"></script>
</body>
</html>
```

### 6.2 页面布局

```
┌─────────────────────────────────────────────────────┐
│  🔑 Token 获取工具                        [✕ 关闭]  │
├─────────────────────────────────────────────────────┤
│  📘 Azure 应用注册快速指引           [▼ 收起/展开]   │
│  ┌─────────────────────────────────────────────┐   │
│  │ 步骤1: 注册应用 [Azure 门户→]               │   │
│  │ 步骤2: 开启公共客户端 ⚠️ 最易遗漏           │   │
│  │ 步骤3: 配置 API 权限                        │   │
│  │ 步骤4: 配置重定向 URI                       │   │
│  │ 步骤5: 获取 Client ID                       │   │
│  └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  ① OAuth 配置                                       │
│                                                     │
│  Client ID     [________________________]           │
│  Client Secret [________________________] (可选)     │
│  Tenant        [consumers ▼            ]            │
│  Redirect URI  [http://localhost:5000/token-tool/callback]│
│  Scope         [chip] [chip] [chip] [+ 添加]        │
│                [预设: Graph] [预设: IMAP]            │
│  ☐ 强制 Consent  ☐ 保存配置                         │
│                                                     │
│  [🔵 登录 Microsoft]                                │
├─────────────────────────────────────────────────────┤
│  ② 手动换取 Token                  [▼ 展开/收起]    │
│  ┌─────────────────────────────────────────────┐   │
│  │ 粘贴回调 URL: [____________________________]│   │
│  │ [🔄 换取 Token]                              │   │
│  └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  ③ 结果                                            │
│                                                     │
│  ✅ Token 获取成功                                   │
│  Refresh Token  [****...****]         [📋 复制]     │
│  Access Token   [****...****]         [📋 复制]     │
│  Client ID      [xxx-xxx-xxx]         [📋 复制]     │
│  请求的 Scope    offline_access ...                  │
│  实际授权 Scope  Mail.Read User.Read                 │
│  Audience       https://graph.microsoft.com         │
│                                                     │
│  [💾 写入到账号]  [📋 复制全部]                       │
└─────────────────────────────────────────────────────┘
```

### 6.3 Scope Chips 交互

借鉴 QuickMSToken 实现:

```
┌─────────────────────────────────────────┐
│ [offline_access 🔒] [.default ✕] [+ __]│
│                                         │
│ 预设: [Graph 邮件] [IMAP] [自定义]       │
└─────────────────────────────────────────┘
```

- `offline_access` 固定显示,带锁图标,不可删除
- 其他 scope 可通过 ✕ 删除
- 输入框支持粘贴多个 scope（空格/逗号/分号分隔自动拆分）
- 预设按钮:
  - **Graph 邮件**: `offline_access https://graph.microsoft.com/.default`
  - **IMAP**: `offline_access https://outlook.office.com/IMAP.AccessAsUser.All`

### 6.4 写入账号弹窗

```
┌─────────────────────────────────────┐
│  写入到账号                          │
│                                     │
│  ○ 更新已有账号                      │
│    [搜索账号... ▼]                   │
│    user1@outlook.com (active)       │
│    user2@hotmail.com (inactive) ←   │
│                                     │
│  ○ 创建新账号                        │
│    邮箱地址: [________________]      │
│                                     │
│  [取消]  [✅ 确认写入]               │
└─────────────────────────────────────┘
```

### 6.5 主页面集成

在 `index.html` 侧边栏新增入口:

```javascript
// static/js/main.js 新增
function openTokenTool() {
    window.open('/token-tool', 'token-tool', 'width=720,height=860,scrollbars=yes');
}
```

侧边栏 HTML:
```html
<!-- 仅在 OAUTH_TOOL_ENABLED 时渲染 -->
{% if OAUTH_TOOL_ENABLED %}
<a onclick="openTokenTool()" title="Token 获取工具">🔑 Token 工具</a>
{% endif %}
```

---

## 7. Blueprint 注册与开关

### 7.1 Blueprint 工厂

```python
# outlook_web/routes/token_tool.py

def create_blueprint():
    bp = Blueprint("token_tool", __name__)
    bp.add_url_rule("/token-tool", view_func=controller.render_page, methods=["GET"])
    bp.add_url_rule("/api/token-tool/prepare", view_func=controller.prepare_oauth, methods=["POST"])
    bp.add_url_rule("/token-tool/callback", view_func=controller.handle_callback, methods=["GET"])
    bp.add_url_rule("/api/token-tool/exchange", view_func=controller.exchange_token, methods=["POST"])
    bp.add_url_rule("/api/token-tool/save", view_func=controller.save_to_account, methods=["POST"])
    bp.add_url_rule("/api/token-tool/accounts", view_func=controller.get_account_list, methods=["GET"])
    bp.add_url_rule("/api/token-tool/config", view_func=controller.get_config, methods=["GET"])
    bp.add_url_rule("/api/token-tool/config", view_func=controller.save_config, methods=["POST"])
    return bp
```

### 7.2 条件注册

```python
# outlook_web/app.py

from outlook_web import config as app_config

if app_config.get_oauth_tool_enabled():
    from outlook_web.routes import token_tool
    app.register_blueprint(token_tool.create_blueprint())
```

### 7.3 模板上下文注入

```python
@app.context_processor
def inject_app_version():
    return {
        "APP_VERSION": APP_VERSION,
        "OAUTH_TOOL_ENABLED": app_config.get_oauth_tool_enabled(),  # 新增
    }
```

---

## 8. 配置存储设计

### 8.1 Settings 表 Key 规范

| Key | 类型 | 说明 | 加密 |
|-----|------|------|------|
| `oauth_tool_client_id` | string | Client ID | ❌ |
| `oauth_tool_client_secret` | string | Client Secret（兼容模式固定空值） | ❌ |
| `oauth_tool_redirect_uri` | string | Redirect URI | ❌ |
| `oauth_tool_scope` | string | Scope（空格分隔） | ❌ |
| `oauth_tool_tenant` | string | Tenant | ❌ |
| `oauth_tool_prompt_consent` | string | "true"/"false" | ❌ |

### 8.2 配置优先级

```
页面用户输入 > Settings 表存储值 > 环境变量默认值 > 硬编码默认值
```

**加载逻辑**:
1. 页面加载时 `GET /api/token-tool/config`
2. 后端: Settings 表有值 → 返回; 无值 → 读环境变量; 都无 → 返回硬编码默认值
3. 用户修改后勾选「保存配置」→ `POST /api/token-tool/config` 写入 Settings 表

---

## 9. 安全设计

### 9.1 认证保护

| 路由 | 认证方式 |
|------|---------|
| `GET /token-tool` | `@login_required`（Session） |
| `POST /api/token-tool/*` | `@login_required`（Session） |
| `GET /token-tool/callback` | Session `oauth_state` 校验 |

### 9.2 CSRF 保护

- Token 工具页面的 POST 请求需携带 CSRF token
- 从 `/api/csrf-token` 获取（复用现有机制）
- 或在模板中注入 `{{ csrf_token() }}`

### 9.3 敏感数据处理

| 数据 | 存储位置 | 加密方式 |
|------|---------|---------|
| `client_secret` | 不落库（固定空值） | 不适用 |
| `refresh_token` | accounts 表 | `encrypt_data()` |
| PKCE `verifier` | 内存 OAUTH_FLOW_STORE | 不持久化,20 分钟自动清理 |
| OAuth `state` | Session cookie + 内存 | HttpOnly + 内存 TTL |

### 9.4 OAUTH_FLOW_STORE 安全

- 线程安全: `threading.Lock()` 保护所有读写
- 自动过期: 每次操作清理 > 20 分钟的条目
- 单次使用: token 换取成功后立即从 Store 中删除
- 进程隔离: 内存存储,重启后清空（无持久化风险）

---

## 10. 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `OAUTH_TOOL_ENABLED` | `true` | 是否启用 Token 工具 Blueprint |
| `OAUTH_CLIENT_ID` | 空 | 默认 Client ID |
| `OAUTH_CLIENT_SECRET` | 空 | 兼容模式固定空值（不参与页面输入） |
| `OAUTH_REDIRECT_URI` | 空（自动检测） | 默认 Redirect URI |
| `OAUTH_SCOPE` | `offline_access https://outlook.office.com/IMAP.AccessAsUser.All` | 后端环境变量默认 Scope（兼容 fallback） |
| `OAUTH_TENANT` | `consumers` | 默认 Tenant |

---

## 11. 回调页面模板设计

### popup_result.html

OAuth 弹窗被 Microsoft 重定向后渲染的页面,极简设计:

```html
<!DOCTYPE html>
<html>
<head><title>OAuth 回调</title></head>
<body>
  {% if error %}
    <!-- 错误模式 -->
    <div class="error-card">
      <h2>⚠️ 授权未完成</h2>
      <p>{{ error_description }}</p>
      <p class="guidance">{{ guidance }}</p>
      <button onclick="window.close()">关闭</button>
    </div>
  {% else %}
    <!-- 成功模式 -->
    <div class="success-card">
      <h2>✅ 授权成功</h2>
      <p>请复制当前地址栏的完整 URL,粘贴到 Token 工具页面的「手动换取」区域</p>
      <button onclick="copyCurrentUrl()">📋 复制回调地址</button>
      <button onclick="window.close()">关闭</button>
    </div>
  {% endif %}
  
  <script>
    function copyCurrentUrl() {
      navigator.clipboard.writeText(window.location.href)
        .then(() => { /* 提示已复制 */ });
    }
  </script>
</body>
</html>
```
