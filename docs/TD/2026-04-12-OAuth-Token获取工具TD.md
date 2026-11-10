# TD: OAuth Token 获取工具

- 文档版本: v1.5
- 创建日期: 2026-04-12
- 更新日期: 2026-04-16（v1.5 — 会话文档按实际实现口径再同步）
- 文档类型: 技术细节设计
- 关联 PRD: `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`
- 关联 FD: `docs/FD/2026-04-12-OAuth-Token获取工具FD.md`
- 关联 TDD: `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md`
- 目标版本: v1.15.0

> **v1.15.0 实施收口说明（兼容账号导入模式）**
>
> 当前代码实现以兼容账号导入模式为准：
> - Tenant 固定 `consumers`
> - `client_secret` 在页面、配置返回与保存接口中均保持为空
> - `prepare_oauth()`、`save_config()`、`save_to_account()` 统一拒绝不兼容配置
> - 前端默认 Scope 采用 Graph 预设；后端环境变量默认值仍为 IMAP 兼容预设
> - Azure 应用注册应使用 **AzureADandPersonalMicrosoftAccount**；仅组织目录会在授权前返回 `unauthorized_client`，仅个人账号会在保存前 `/common` 验证链路返回 `AADSTS9002331`
> - 若 Azure 门户在切换该受支持账户类型时报 `api.requestedAccessTokenVersion is invalid`，需先在 Manifest 中把 `api.requestedAccessTokenVersion` 改成 `2`
> - 2026-04-16 已落地前端新手引导机制：`<details id="guide-card">` + `localStorage(token_tool_guide_dismissed)` 记忆 + `GUIDE_TUTORIAL_LINKS` 扩展位
>
> 本文较早伪代码中若仍保留可变 tenant、`client_secret` 加密存储/回传、tenant-aware 或 client-secret-aware 保存链路，均已被当前实现收口逻辑取代。**最终以 `outlook_web/controllers/token_tool.py`、`templates/token_tool.html`、`static/js/features/token_tool.js` 的当前代码为准。**

---

## 1. 文档目标

本文档解决以下技术实现问题:

1. **Blueprint 条件注册**: 如何在 `app.py` 中条件注册 Token 工具 Blueprint，环境变量开关控制
2. **PKCE + State 安全实现**: 如何在 Service 层实现 OAuth2 Authorization Code + PKCE 完整流程
3. **OAUTH_FLOW_STORE 生命周期**: 内存状态存储的线程安全、TTL 清理、单进程约束
4. **配置优先级链**: Settings 表 + 环境变量 + 硬编码默认值的读取顺序实现
5. **账号写入兼容**: 如何复用现有 `accounts_repo.add_account()` / `update_account()` 将 Token 写入系统
6. **独立页面模板**: 如何创建不依赖 `index.html` 的独立 Jinja2 模板

**不解决的问题**（留给未来版本）:
- 批量 Token 获取向导
- Token 到期预警与自动续期
- IMAP Token 获取快捷模式
- Redis 替换内存 OAUTH_FLOW_STORE

---

## 2. 当前技术现状

### 2.1 应用工厂与 Blueprint 注册

**核心模块**: `outlook_web/app.py`

**当前 Blueprint 注册**（lines 138-150）:
```python
app.register_blueprint(pages.create_blueprint(csrf_exempt=csrf_exempt))
app.register_blueprint(groups.create_blueprint())
app.register_blueprint(tags.create_blueprint())
app.register_blueprint(accounts.create_blueprint())
app.register_blueprint(emails.create_blueprint())
app.register_blueprint(temp_emails.create_blueprint(csrf_exempt=csrf_exempt))
app.register_blueprint(settings.create_blueprint())
app.register_blueprint(scheduler.create_blueprint())
app.register_blueprint(system.create_blueprint())
app.register_blueprint(audit.create_blueprint())
app.register_blueprint(external_pool.create_blueprint(csrf_exempt=csrf_exempt))
app.register_blueprint(external_temp_emails.create_blueprint(csrf_exempt=csrf_exempt))
```

**Context Processor**（lines 80-82）:
```python
@app.context_processor
def inject_app_version():
    return {"APP_VERSION": APP_VERSION}
```

**关键约束**:
- 12 个 Blueprint 全部无条件注册（无先例的条件注册模式）
- CSRF 保护通过 `flask_wtf.CSRFProtect` 全局启用（line 109）
- 部分 Blueprint 接收 `csrf_exempt` 装饰器（external_pool、external_temp_emails、pages、temp_emails）

### 2.2 Token 换取现有实现

**核心模块**: `outlook_web/services/graph.py`

**Token URL**（line 11）:
```python
TOKEN_URL_GRAPH = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
```

**Token 获取**（lines 46-106）:
```python
def get_access_token_graph_result(client_id: str, refresh_token: str, proxy_url: str = None) -> Dict[str, Any]:
    res = requests.post(
        TOKEN_URL_GRAPH,
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
        proxies=build_proxies(proxy_url),
    )
```

**Token 验证 + 轮换**（lines 255-293）:
```python
def test_refresh_token_with_rotation(
    client_id: str, refresh_token: str, proxy_url: str = None
) -> tuple[bool, str | None, str | None]:
    """返回 (success, error_message, new_refresh_token)"""
```

**复用点**:
- OAuth Token 工具的 `/save` 接口需调用 `test_refresh_token_with_rotation()` 验证新获取的 token 有效性
- Token endpoint URL 模式相同，但 OAuth 工具使用 `grant_type=authorization_code`（非 `refresh_token`）
- 当前工具固定兼容模式 tenant=`consumers`，可变 tenant 设计不在本期实现范围

### 2.3 加密体系

**核心模块**: `outlook_web/security/crypto.py`

**加密**（lines 66-80）:
```python
def encrypt_data(data: str) -> str:
    """加密敏感数据，返回 'enc:' + base64 加密字符串"""
    if not data:
        return data
    if data.startswith("enc:"):
        return data  # 幂等：已加密直接返回
    cipher = get_cipher()
    encrypted = cipher.encrypt(data.encode("utf-8"))
    return "enc:" + encrypted.decode("utf-8")
```

**解密**（lines 83-111）:
```python
def decrypt_data(encrypted_data: str) -> str:
    """解密敏感数据，无 'enc:' 前缀直接返回（向后兼容）"""
```

**密钥派生**: PBKDF2 + SHA256 + 固定盐 `b"outlook_email_encryption_salt_v1"`，从 `SECRET_KEY` 派生

**本期使用场景**:
- `oauth_tool_client_secret` 在兼容模式下固定为空值（不参与保存链路）
- 账号表的 `refresh_token` 写入时使用 `encrypt_data()` 加密（复用现有 `add_account` 逻辑）

### 2.4 Settings 存储

**核心模块**: `outlook_web/repositories/settings.py`

**基础读写**:
```python
def get_setting(key: str, default: str = "") -> str:      # line 21
def set_setting(key: str, value: str, *, commit: bool = True) -> bool:  # line 29
```

**Typed Getter 模式**（已有先例）:
```python
def get_cf_worker_domains() -> list[dict[str, Any]]:       # JSON 解析
def get_cf_worker_default_domain() -> str:                  # 直接返回
def get_external_api_rate_limit() -> int:                   # int 转换 + 默认值
def get_external_api_key() -> str:                          # 自动解密
```

### 2.5 账号管理

**核心模块**: `outlook_web/repositories/accounts.py`

**新增账号**（lines 157-236）:
```python
def add_account(
    email_addr: str, password: str, client_id: str, refresh_token: str,
    group_id: int = 1, remark: str = "", account_type: str = "outlook",
    provider: str = "outlook", ..., add_to_pool: bool = False,
) -> bool:
```

**关键约束**:
- `client_id TEXT NOT NULL`、`refresh_token TEXT NOT NULL`（DB 约束）
- IMAP 类型使用空字符串占位，OAuth 类型必须提供非空值
- 自动加密: `encrypt_data(refresh_token)`

**更新账号**（lines 239-339）:
```python
def update_account(
    account_id: int, email_addr: str, password: Optional[str],
    client_id: Optional[str], refresh_token: Optional[str],
    group_id: int, remark: str, status: str,
) -> bool:
```

### 2.6 环境变量配置

**核心模块**: `outlook_web/config.py`

**读取模式**（line 6）:
```python
def _getenv(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None:
        return default
    value = value.strip()
    return value if value != "" else default
```

**布尔值模式**（line 50）:
```python
def env_true(key: str, default: bool) -> bool:
    value = _getenv(key, "true" if default else "false") or (...)
    return value.lower() == "true"
```

### 2.7 错误码体系

**核心模块**: `outlook_web/errors.py`

**已定义的 OAuth 相关错误码**（lines 49-56, 95-102）:

| 错误码 | 中文 | 英文 |
|--------|------|------|
| `OAUTH_CODE_INVALID` | 授权码无效或已过期 | Authorization code is invalid or expired |
| `OAUTH_CODE_PARSE_FAILED` | 无法从回跳结果中解析授权码 | Failed to parse the authorization code from the callback |
| `OAUTH_CONFIG_INVALID` | OAuth 配置无效 | OAuth configuration is invalid |
| `OAUTH_MICROSOFT_AUTH_FAILED` | 微软授权失败 | Microsoft authorization failed |
| `OAUTH_MICROSOFT_REQUEST_FAILED` | 请求微软 OAuth 服务失败 | Request to Microsoft OAuth failed |
| `OAUTH_REDIRECT_URI_MISMATCH` | redirect_uri 与当前 OAuth 配置不匹配 | The redirect URI does not match the configured OAuth redirect URI |
| `OAUTH_REFRESH_TOKEN_MISSING` | 微软未返回 refresh_token | Microsoft did not return a refresh token |
| `OAUTH_VERIFY_TOKEN_REQUIRED` | 缺少 verify_token | Verification token is required |

**复用**: 大部分错误码已存在，本期新增少量即可。

---

## 3. 核心技术决策

### 3.1 决策一: Schema 变更策略

**选定方案**: 无需升级 Schema（保持 v19）

**理由**:
1. OAuth 工具配置以 `oauth_tool_*` key 前缀存入已有 Settings 表，`set_setting()` 使用 `INSERT OR REPLACE` 自动处理不存在的 key
2. Token 写入复用已有 `accounts` 表字段（`client_id`、`refresh_token`），无新增列需求
3. 避免无意义的版本升级，减少用户升级负担

**Settings 表新增 Key**（运行时按需创建，无需 init_db 预写入）:

| Key | 说明 | 加密 |
|-----|------|------|
| `oauth_tool_client_id` | Client ID | ❌ |
| `oauth_tool_client_secret` | Client Secret | ✅ |
| `oauth_tool_redirect_uri` | Redirect URI | ❌ |
| `oauth_tool_scope` | Scope（空格分隔） | ❌ |
| `oauth_tool_tenant` | Tenant | ❌ |
| `oauth_tool_prompt_consent` | "true"/"false" | ❌ |

### 3.2 决策二: 配置优先级实现

**选定方案**: `repositories/settings.py` 新增 Typed Getter 函数

**理由**:
1. 与已有 `get_cf_worker_domains()`、`get_external_api_rate_limit()` 等模式一致
2. 封装优先级链（Settings → 环境变量 → 硬编码），Controller 层无需感知细节
3. 敏感字段（`client_secret`）自动解密封装在 getter 中

**实施方式**: 新增 6 个 getter 函数（详见 §4.2）

### 3.3 决策三: CSRF 策略

**选定方案**: 标准 CSRF 流程，不需要 `csrf_exempt`

**理由**:
1. `GET /token-tool/callback` 是 GET 请求，Flask-WTF 默认不校验 GET 的 CSRF
2. `POST /api/token-tool/*` 接口由独立模板 `token_tool.html` 发起 Fetch，可通过 `{{ csrf_token() }}` 注入 token
3. 遵循最小权限原则，不给 Token 工具 Blueprint 做 CSRF 豁免

**回调路由特殊处理**:
- `GET /token-tool/callback` 不需要 `@login_required`，因为是 Microsoft OAuth 重定向过来的
- 但需要通过 Session 中 `oauth_state` 进行 state 校验

### 3.4 决策四: OAUTH_FLOW_STORE 实现位置

**选定方案**: 放在 `services/oauth_tool.py` 内部（模块级变量）

**理由**:
1. OAUTH_FLOW_STORE 与 OAuth 流程逻辑紧密耦合（start_flow → store → get_flow → exchange → discard）
2. 当前项目 Service 层自包含模式（如 `graph.py` 的 token 处理全在一个文件）
3. 模块级变量 + `threading.Lock()` 在单 worker 部署下安全可靠
4. 未来如需 Redis 替换，只需重写 3 个函数（store/get/discard），不影响外部调用方

**单进程约束验证**:
- 现有部署使用 `app.run()` 或 Gunicorn `workers=1`（调度器一致性要求）
- OAUTH_FLOW_STORE 作为模块级变量，与此约束兼容
- Docker 部署的 `workers=1` 约束已在 Dockerfile/docker-compose.yml 中体现

### 3.5 决策五: Blueprint 条件注册

**选定方案**: 参照 `config.py` 的 `env_true()` 模式实现条件注册

**理由**:
1. 项目首例条件注册 Blueprint，但 `config.py` 中已有布尔环境变量模式（`get_proxy_fix_enabled()`、`get_scheduler_autostart_default()`）
2. 默认值: `OAUTH_TOOL_ENABLED=true`（PRD 要求开箱即用，降低新用户门槛）
3. Docker 用户可通过 `OAUTH_TOOL_ENABLED=false` 关闭

---

## 4. 后端实现

### 4.1 `outlook_web/config.py` — 新增环境变量

**位置**: 文件末尾（约 line 92 之后）

```python
# ---- OAuth Token 工具 ----

def get_oauth_tool_enabled() -> bool:
    """是否启用 Token 获取工具。默认启用。"""
    return env_true("OAUTH_TOOL_ENABLED", True)


def get_oauth_client_id_default() -> str:
    """OAuth 工具默认 Client ID（环境变量层）。"""
    return _getenv("OAUTH_CLIENT_ID", "") or ""


def get_oauth_client_secret_default() -> str:
    """OAuth 工具默认 Client Secret（环境变量层）。"""
    return _getenv("OAUTH_CLIENT_SECRET", "") or ""


def get_oauth_redirect_uri_default() -> str:
    """OAuth 工具默认 Redirect URI（环境变量层）。"""
    return _getenv("OAUTH_REDIRECT_URI", "") or ""


def get_oauth_scope_default() -> str:
    """OAuth 工具默认 Scope（环境变量层）。"""
    return _getenv("OAUTH_SCOPE", "offline_access https://outlook.office.com/IMAP.AccessAsUser.All") or "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"


def get_oauth_tenant_default() -> str:
    """OAuth 工具默认 Tenant（环境变量层）。"""
    return _getenv("OAUTH_TENANT", "consumers") or "consumers"
```

**共新增 6 个函数**，遵循已有 `_getenv()` + `env_true()` 模式。

### 4.2 `outlook_web/repositories/settings.py` — 新增 OAuth 工具 Getter

**位置**: 文件末尾（约 `get_cf_worker_prefix_rules()` 之后）

```python
# ---- OAuth Token 工具配置 ----

def get_oauth_tool_client_id() -> str:
    """Settings 表 → 环境变量 → 空字符串"""
    value = get_setting("oauth_tool_client_id")
    if value:
        return value
    return config.get_oauth_client_id_default()


def get_oauth_tool_client_secret() -> str:
    """Settings 表（自动解密） → 环境变量 → 空字符串"""
    value = get_setting("oauth_tool_client_secret")
    if value:
        try:
            return decrypt_data(value)
        except Exception:
            return ""
    return config.get_oauth_client_secret_default()


def get_oauth_tool_redirect_uri() -> str:
    """Settings 表 → 环境变量 → 空字符串"""
    value = get_setting("oauth_tool_redirect_uri")
    if value:
        return value
    return config.get_oauth_redirect_uri_default()


def get_oauth_tool_scope() -> str:
    """Settings 表 → 环境变量 → 默认 IMAP 兼容 scope（前端首次展示可覆盖为 Graph）"""
    value = get_setting("oauth_tool_scope")
    if value:
        return value
    return config.get_oauth_scope_default()


def get_oauth_tool_tenant() -> str:
    """Settings 表 → 环境变量 → 'consumers'"""
    value = get_setting("oauth_tool_tenant")
    if value:
        return value
    return config.get_oauth_tenant_default()


def get_oauth_tool_prompt_consent() -> bool:
    """Settings 表 → False"""
    value = get_setting("oauth_tool_prompt_consent", "false")
    return value.lower() == "true"
```

**共新增 6 个 getter 函数**，与 `get_external_api_key()` 模式一致（敏感字段自动解密）。

### 4.3 `outlook_web/app.py` — 条件注册 Blueprint

**变更 1: 新增 import**（约 line 32-45 imports 区域）:

```python
from outlook_web.routes import (
    ...existing imports...
)
# 条件导入
from outlook_web import config as app_config
```

**变更 2: 条件注册 Blueprint**（约 line 150 之后）:

```python
# OAuth Token 工具（可通过 OAUTH_TOOL_ENABLED=false 关闭）
if app_config.get_oauth_tool_enabled():
    from outlook_web.routes import token_tool
    app.register_blueprint(token_tool.create_blueprint())
```

**变更 3: Context Processor 扩展**（约 line 80-82）:

```python
@app.context_processor
def inject_app_version():
    return {
        "APP_VERSION": APP_VERSION,
        "OAUTH_TOOL_ENABLED": app_config.get_oauth_tool_enabled(),
    }
```

### 4.4 `outlook_web/routes/token_tool.py` — Blueprint 定义

```python
from __future__ import annotations

from flask import Blueprint

from outlook_web.controllers import token_tool as token_tool_controller


def create_blueprint() -> Blueprint:
    """创建 token_tool Blueprint"""
    bp = Blueprint("token_tool", __name__)

    # 页面渲染
    bp.add_url_rule(
        "/token-tool",
        view_func=token_tool_controller.render_page,
        methods=["GET"],
    )

    # OAuth 准备（生成授权 URL）
    bp.add_url_rule(
        "/api/token-tool/prepare",
        view_func=token_tool_controller.prepare_oauth,
        methods=["POST"],
    )

    # OAuth 回调页面（Microsoft 重定向）
    bp.add_url_rule(
        "/token-tool/callback",
        view_func=token_tool_controller.handle_callback,
        methods=["GET"],
    )

    # 手动粘贴 URL 换取 Token
    bp.add_url_rule(
        "/api/token-tool/exchange",
        view_func=token_tool_controller.exchange_token,
        methods=["POST"],
    )

    # 写入系统账号
    bp.add_url_rule(
        "/api/token-tool/save",
        view_func=token_tool_controller.save_to_account,
        methods=["POST"],
    )

    # 获取可写入账号列表
    bp.add_url_rule(
        "/api/token-tool/accounts",
        view_func=token_tool_controller.get_account_list,
        methods=["GET"],
    )

    # 配置读写
    bp.add_url_rule(
        "/api/token-tool/config",
        view_func=token_tool_controller.get_config,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/api/token-tool/config",
        endpoint="save_config",
        view_func=token_tool_controller.save_config,
        methods=["POST"],
    )

    return bp
```

**关键技术细节**:

**Q1**: 为什么 `GET /api/token-tool/config` 和 `POST /api/token-tool/config` 要设 `endpoint`？
- **A**: Flask 同一 Blueprint 内，同一 URL 不同 method 需要不同 endpoint 名称，否则报 `AssertionError: View function mapping is overwriting`。`GET` 默认 endpoint = `get_config`，`POST` 显式设为 `save_config`。

**Q2**: 回调路由为什么不加 `@login_required`？
- **A**: `GET /token-tool/callback` 是 Microsoft OAuth 服务器重定向过来的，浏览器上下文虽携带 Session cookie，但该请求由外部发起。安全性通过 `state` 参数校验保证（Session + OAUTH_FLOW_STORE 双重验证）。

### 4.5 `outlook_web/controllers/token_tool.py` — 控制器

```python
from __future__ import annotations

import html
import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from flask import jsonify, redirect, render_template, request, session, url_for

from outlook_web.audit import log_audit
from outlook_web.errors import build_error_response
from outlook_web.repositories import accounts as accounts_repo
from outlook_web.repositories import settings as settings_repo
from outlook_web.security.auth import login_required
from outlook_web.security.crypto import encrypt_data
from outlook_web.services import graph as graph_service
from outlook_web.services import oauth_tool as oauth_tool_service

logger = logging.getLogger(__name__)
```

**render_page()** — 渲染工具页面:
```python
@login_required
def render_page() -> Any:
    return render_template("token_tool.html")
```

**prepare_oauth()** — 生成授权 URL:
```python
@login_required
def prepare_oauth() -> Any:
    data = request.get_json(silent=True) or {}

    client_id = (data.get("client_id") or "").strip()
    if not client_id:
        return build_error_response("OAUTH_CONFIG_INVALID", "Client ID 不能为空", status=400)

    redirect_uri = (data.get("redirect_uri") or "").strip()
    if not redirect_uri or not redirect_uri.startswith(("http://", "https://")):
        return build_error_response("OAUTH_CONFIG_INVALID", "Redirect URI 格式无效", status=400)

    oauth_config = {
        "client_id": client_id,
        "client_secret": (data.get("client_secret") or "").strip(),
        "redirect_uri": redirect_uri,
        "scope": (data.get("scope") or "").strip(),
        "tenant": (data.get("tenant") or "consumers").strip(),
        "prompt_consent": bool(data.get("prompt_consent")),
    }

    authorize_url, state_or_error = oauth_tool_service.start_oauth_flow(oauth_config)
    if authorize_url is None:
        return build_error_response("OAUTH_CONFIG_INVALID", state_or_error, status=400)

    # 双重 state：Session + 内存
    session["oauth_state"] = state_or_error
    return jsonify({"success": True, "data": {"authorize_url": authorize_url}})
```

**handle_callback()** — 回调处理（无 @login_required）:
```python
def handle_callback() -> Any:
    error = request.args.get("error")
    error_description = request.args.get("error_description", "")

    if error:
        guidance = oauth_tool_service.map_error_guidance(error)
        return render_template(
            "popup_result.html",
            error=True,
            error_code=error,
            error_description=error_description,
            guidance=guidance,
        )

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return render_template(
            "popup_result.html",
            error=True,
            error_code="missing_params",
            error_description="回调缺少 code 或 state 参数",
            guidance="请重新点击『登录 Microsoft』",
        )

    # 渲染成功页（用户需复制 URL 回主页面）
    return render_template("popup_result.html", error=False)
```

**exchange_token()** — 手动粘贴换取:
```python
@login_required
def exchange_token() -> Any:
    data = request.get_json(silent=True) or {}
    callback_url = (data.get("callback_url") or "").strip()
    if not callback_url:
        return build_error_response("OAUTH_CODE_PARSE_FAILED", "请粘贴回调 URL", status=400)

    # 从 URL 解析 code 和 state
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    code = (qs.get("code") or [None])[0]
    state = (qs.get("state") or [None])[0]

    if not code:
        return build_error_response("OAUTH_CODE_PARSE_FAILED", "URL 中未包含 code 参数", status=400)
    if not state:
        return build_error_response("OAUTH_CODE_PARSE_FAILED", "URL 中未包含 state 参数", status=400)

    # State 校验：Session
    session_state = session.get("oauth_state")
    if not session_state or session_state != state:
        return build_error_response(
            "OAUTH_MICROSOFT_AUTH_FAILED",
            "state 校验失败，请重新发起授权",
            status=400,
        )

    # 从 OAUTH_FLOW_STORE 取回 flow_data
    flow_data = oauth_tool_service.get_oauth_flow(state)
    if not flow_data:
        return build_error_response(
            "OAUTH_CODE_INVALID",
            "授权流程已过期（超过 20 分钟），请重新发起",
            status=400,
        )

    # 换取 Token
    token_data, error_info = oauth_tool_service.exchange_code_for_tokens(
        code=code,
        oauth_config={
            "client_id": flow_data["client_id"],
            "client_secret": flow_data.get("client_secret", ""),
            "redirect_uri": flow_data["redirect_uri"],
            "scope": flow_data["scope"],
            "tenant": flow_data.get("tenant", "consumers"),
        },
        verifier=flow_data["verifier"],
    )

    # 清理
    oauth_tool_service.discard_oauth_flow(state)
    session.pop("oauth_state", None)

    if token_data is None:
        if isinstance(error_info, dict):
            return build_error_response(
                "OAUTH_MICROSOFT_REQUEST_FAILED",
                error_info.get("message", "换取 Token 失败"),
                status=400,
                details=error_info.get("guidance"),
            )
        return build_error_response("OAUTH_MICROSOFT_REQUEST_FAILED", str(error_info), status=400)

    log_audit("create", "oauth_token", flow_data["client_id"], "Token 获取成功")
    return jsonify({"success": True, "data": token_data})
```

**save_to_account()** — 写入系统账号:
```python
@login_required
def save_to_account() -> Any:
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "").strip()
    refresh_token = (data.get("refresh_token") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    if not refresh_token:
        return build_error_response("OAUTH_REFRESH_TOKEN_MISSING", "refresh_token 不能为空", status=400)
    if not client_id:
        return build_error_response("OAUTH_CONFIG_INVALID", "client_id 不能为空", status=400)

    # 验证 token 有效性
    valid, error_msg, new_rt = graph_service.test_refresh_token_with_rotation(client_id, refresh_token)
    if not valid:
        return build_error_response(
            "OAUTH_MICROSOFT_REQUEST_FAILED",
            f"Token 验证失败: {error_msg}",
            status=400,
        )
    # 如果 Microsoft 返回了新的 refresh_token（轮换），使用新值
    if new_rt:
        refresh_token = new_rt

    if mode == "update":
        account_id = data.get("account_id")
        if not account_id:
            return build_error_response("OAUTH_CONFIG_INVALID", "account_id 不能为空", status=400)
        # 使用 update_account_credentials 仅更新凭据字段（不影响 email/group/remark 等）
        success = accounts_repo.update_account_credentials(
            int(account_id),
            client_id=client_id,
            refresh_token=refresh_token,
        )
        if not success:
            return build_error_response("INTERNAL_ERROR", "更新账号失败", status=500)

        # 恢复 active 状态（注：需先扩展 update_account_credentials 的 allowed set 支持 "status"）
        # 或使用 get_account_by_id + update_account 传入完整字段
        existing = accounts_repo.get_account_by_id(int(account_id))
        if existing:
            accounts_repo.update_account(
                account_id=int(account_id),
                email_addr=existing["email"],
                password=None,
                client_id=client_id,
                refresh_token=refresh_token,
                group_id=existing.get("group_id", 1),
                remark=existing.get("remark", ""),
                status="active",
            )
        if not success:
            return build_error_response("INTERNAL_ERROR", "更新账号失败", status=500)
        log_audit("update", "account", str(account_id), f"Token 工具写入 (client_id={client_id[:8]}...)")
        return jsonify({"success": True, "data": {"account_id": account_id, "token_valid": True}})

    elif mode == "create":
        email = (data.get("email") or "").strip()
        if not email or "@" not in email:
            return build_error_response("OAUTH_CONFIG_INVALID", "邮箱格式无效", status=400)
        success = accounts_repo.add_account(
            email_addr=email,
            password="",
            client_id=client_id,
            refresh_token=refresh_token,
            account_type="outlook",
            provider="outlook",
        )
        if not success:
            return build_error_response("INTERNAL_ERROR", "创建账号失败（邮箱可能已存在）", status=400)
        log_audit("create", "account", email, f"Token 工具新建 (client_id={client_id[:8]}...)")
        return jsonify({"success": True, "data": {"email": email, "token_valid": True}})
    else:
        return build_error_response("OAUTH_CONFIG_INVALID", "mode 必须是 update 或 create", status=400)
```

**get_account_list()** — 可写入账号列表:
```python
@login_required
def get_account_list() -> Any:
    accounts = accounts_repo.load_accounts()
    result = [
        {
            "id": a["id"],
            "email": a["email"],
            "status": a.get("status", "active"),
            "account_type": a.get("account_type", "outlook"),
        }
        for a in accounts
        if a.get("account_type") in ("outlook", None)
    ]
    return jsonify({"success": True, "data": result})
```

**get_config() / save_config()** — 配置 CRUD:
```python
@login_required
def get_config() -> Any:
    return jsonify({
        "success": True,
        "data": {
            "client_id": settings_repo.get_oauth_tool_client_id(),
            "client_secret": settings_repo.get_oauth_tool_client_secret(),
            "redirect_uri": settings_repo.get_oauth_tool_redirect_uri(),
            "scope": settings_repo.get_oauth_tool_scope(),
            "tenant": settings_repo.get_oauth_tool_tenant(),
            "prompt_consent": settings_repo.get_oauth_tool_prompt_consent(),
        },
    })


@login_required
def save_config() -> Any:
    data = request.get_json(silent=True) or {}
    settings_repo.set_setting("oauth_tool_client_id", (data.get("client_id") or "").strip())
    # client_secret 加密存储
    secret = (data.get("client_secret") or "").strip()
    settings_repo.set_setting("oauth_tool_client_secret", encrypt_data(secret) if secret else "")
    settings_repo.set_setting("oauth_tool_redirect_uri", (data.get("redirect_uri") or "").strip())
    settings_repo.set_setting("oauth_tool_scope", (data.get("scope") or "").strip())
    settings_repo.set_setting("oauth_tool_tenant", (data.get("tenant") or "").strip())
    settings_repo.set_setting("oauth_tool_prompt_consent", "true" if data.get("prompt_consent") else "false")

    log_audit("update", "oauth_tool_config", "settings", "保存 OAuth 工具配置")
    return jsonify({"success": True, "message": "配置已保存"})
```

**关键技术细节**:

**Q1**: `save_to_account()` 的 `update_account()` 参数处理？
- **A**: `update_account()` 要求 `email_addr: str`、`group_id: int`、`remark: str` 均为必填（非 Optional）。传入 None 会导致 `if not email_addr` 检查返回 False。因此需先通过 `get_account_by_id()` 获取现有账号数据，将原有字段回传，仅替换 `client_id`、`refresh_token` 和 `status`。

**Q2**: `get_account_list()` 是否需要过滤 IMAP/CF 账号？
- **A**: 是的。OAuth Token 只能写入 `account_type='outlook'` 的账号（IMAP 使用密码认证，CF 临时邮箱不需要 OAuth）。过滤条件: `a.get("account_type") in ("outlook", None)`。注意 `load_accounts()` 会返回解密后的敏感字段，但 `get_account_list()` 只提取 `id`、`email`、`status`、`account_type` 四个非敏感字段返回前端。

**Q3**: `exchange_token()` 清理 FLOW_STORE 的时机？
- **A**: 无论成功失败都必须清理。成功时 token 已获取；失败时 state 已暴露，同一 flow 不应再次使用。这遵循 OAuth 安全最佳实践（authorization code 单次使用）。

### 4.6 `outlook_web/services/oauth_tool.py` — OAuth 核心逻辑

**完整实现**（含 PKCE、State 管理、Scope 校验、错误引导）:

```python
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from threading import Lock
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# ---- OAUTH_FLOW_STORE（模块级内存存储） ----
OAUTH_FLOW_STORE: Dict[str, Dict[str, Any]] = {}
OAUTH_FLOW_LOCK = Lock()
OAUTH_FLOW_TTL = 20 * 60  # 20 分钟


def _prune_expired() -> None:
    """清理过期的 flow 条目（必须在 LOCK 内调用）"""
    now = time.time()
    expired = [k for k, v in OAUTH_FLOW_STORE.items() if now - v.get("created_at", 0) > OAUTH_FLOW_TTL]
    for k in expired:
        del OAUTH_FLOW_STORE[k]
    if expired:
        logger.debug("[oauth_tool] 清理 %d 个过期 flow", len(expired))


def store_oauth_flow(state: str, flow_data: Dict[str, Any]) -> None:
    with OAUTH_FLOW_LOCK:
        _prune_expired()
        OAUTH_FLOW_STORE[state] = {"created_at": time.time(), **flow_data}


def get_oauth_flow(state: str) -> Optional[Dict[str, Any]]:
    with OAUTH_FLOW_LOCK:
        _prune_expired()
        data = OAUTH_FLOW_STORE.get(state)
        return dict(data) if data else None


def discard_oauth_flow(state: str) -> None:
    with OAUTH_FLOW_LOCK:
        OAUTH_FLOW_STORE.pop(state, None)
```

**PKCE 生成**:
```python
def generate_pkce() -> Tuple[str, str]:
    """生成 PKCE code_verifier + code_challenge (S256)"""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
```

**OAuth Flow 启动**:
```python
def start_oauth_flow(oauth_config: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """
    生成 Microsoft OAuth 授权 URL

    Returns:
        (authorize_url, state) — 成功
        (None, error_message)  — 失败
    """
    # 1. Scope 校验
    normalized_scope, scope_error = validate_scope(oauth_config.get("scope", ""))
    if scope_error:
        return None, scope_error

    # 2. 生成 PKCE
    verifier, challenge = generate_pkce()

    # 3. 生成 state
    state = secrets.token_urlsafe(24)

    # 4. 存储 flow data
    tenant = (oauth_config.get("tenant") or "consumers").strip()
    store_oauth_flow(state, {
        "client_id": oauth_config["client_id"],
        "client_secret": oauth_config.get("client_secret", ""),
        "redirect_uri": oauth_config["redirect_uri"],
        "scope": normalized_scope,
        "tenant": tenant,
        "verifier": verifier,
    })

    # 5. 构建授权 URL
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
    logger.info("[oauth_tool] 授权 URL 已生成 (state=%s...)", state[:8])
    return authorize_url, state
```

**Token 换取**:
```python
def exchange_code_for_tokens(
    code: str, oauth_config: Dict[str, Any], verifier: str
) -> Tuple[Optional[Dict[str, Any]], Any]:
    """
    用授权码换取 token

    Returns:
        (token_data_dict, None)     — 成功
        (None, error_info)          — 失败
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
        logger.error("[oauth_tool] Token 换取网络错误: %s", exc)
        return None, f"无法连接 Microsoft 服务器: {exc}"

    if resp.status_code != 200:
        error_detail = _parse_error_response(resp)
        guidance = map_error_guidance(error_detail)
        logger.warning("[oauth_tool] Token 换取失败: %s", error_detail[:200])
        return None, {"message": error_detail, "guidance": guidance}

    tokens = resp.json()
    return _extract_token_data(tokens, oauth_config), None
```

**辅助函数**:
```python
def _parse_error_response(resp) -> str:
    try:
        err = resp.json()
        return err.get("error_description") or err.get("error") or resp.text[:500]
    except Exception:
        return resp.text[:500]


def _extract_token_data(tokens: dict, oauth_config: dict) -> dict:
    access_token = tokens.get("access_token", "")
    result = {
        "refresh_token": tokens.get("refresh_token", ""),
        "access_token": access_token,
        "expires_in": tokens.get("expires_in", 0),
        "token_type": tokens.get("token_type", "Bearer"),
        "requested_scope": oauth_config.get("scope", ""),
        "granted_scope": tokens.get("scope", ""),
        "client_id": oauth_config["client_id"],
        "redirect_uri": oauth_config["redirect_uri"],
    }

    # JWT 解码（不验签，仅展示用）
    if access_token:
        jwt_payload = decode_jwt_payload(access_token)
        if jwt_payload:
            result["audience"] = jwt_payload.get("aud", "")
            result["scope_claim"] = jwt_payload.get("scp", "")
            result["roles_claim"] = " ".join(jwt_payload.get("roles", []))
    return result


def decode_jwt_payload(token: str) -> Optional[dict]:
    """不验签解码 JWT payload（纯展示用途）"""
    import json as json_mod
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        # 补齐 Base64 padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json_mod.loads(decoded)
    except Exception:
        return None
```

**Scope 校验**:
```python
OIDC_SCOPES = {"openid", "profile", "email", "offline_access"}


def validate_scope(scope_value: str) -> Tuple[str, Optional[str]]:
    """
    校验并标准化 scope

    Returns:
        (normalized_scope, None)       — 合法
        (scope_value, error_message)   — 不合法
    """
    normalized = normalize_scope(scope_value)
    scopes = normalized.split()
    api_scopes = [s for s in scopes if s not in OIDC_SCOPES]

    if not api_scopes:
        return normalized, "至少需要一个 API scope（如 https://graph.microsoft.com/.default）"

    # .default 和命名 scope 不能混用
    has_default = any(s.endswith("/.default") for s in api_scopes)
    has_named = any(not s.endswith("/.default") for s in api_scopes)
    if has_default and has_named:
        return normalized, "同一次请求里，`.default` scope 不能和命名 scope 混用"

    # 不允许跨资源
    resources = {_scope_resource(s) for s in api_scopes if _scope_resource(s)}
    if len(resources) > 1:
        return normalized, "一次 OAuth 请求只能对应一个资源，请分开获取"

    return normalized, None


def normalize_scope(scope_value: str) -> str:
    """标准化 scope: 去重、排序、确保包含 offline_access"""
    scopes = set(scope_value.strip().split())
    scopes.add("offline_access")
    return " ".join(sorted(scopes))


def _scope_resource(scope: str) -> Optional[str]:
    """提取 scope 的资源前缀: https://graph.microsoft.com/Mail.Read → https://graph.microsoft.com"""
    if scope.startswith("https://"):
        parts = scope.split("/")
        if len(parts) >= 4:
            return "/".join(parts[:3])
    return None
```

**错误引导映射**:
```python
ERROR_GUIDANCE_MAP = {
    "unauthorized_client": "请到 Azure 门户 → 身份验证 → 高级设置 → 开启『允许公共客户端流』",
    "invalid_grant": "授权码已过期或已使用，请重新点击『登录 Microsoft』",
    "invalid_scope": "请到 Azure 门户 → API 权限 → 添加对应的 Microsoft Graph 委托权限",
    "redirect_uri_mismatch": "回调地址不匹配，请确认 Azure 门户中注册的重定向 URI 与当前填写的一致",
    "interaction_required": "请勾选『强制 Consent』后重新授权",
    "consent_required": "此权限需要组织管理员同意，请联系 IT 管理员或切换为个人账号",
    "invalid_client": "Client ID 无效或应用已被删除，请到 Azure 门户确认应用注册状态",
    "access_denied": "用户拒绝了授权请求，请重新点击『登录 Microsoft』",
}


def map_error_guidance(error_detail: str) -> str:
    """根据错误信息匹配中文引导建议"""
    detail_lower = error_detail.lower() if isinstance(error_detail, str) else ""
    for key, guidance in ERROR_GUIDANCE_MAP.items():
        if key in detail_lower:
            return guidance
    return "请检查配置后重试，如持续失败请参考 Azure 注册指引"
```

### 4.7 `outlook_web/errors.py` — 新增错误码

**位置**: 英文字典（约 line 56 之后）和中文字典（约 line 102 之后）

需确认是否需要新增。经检查，已有的 8 个 OAuth 错误码覆盖了主要场景。可能需补充:

```python
# 英文
"OAUTH_STATE_MISMATCH": "OAuth state verification failed, please restart the authorization",
"OAUTH_FLOW_EXPIRED": "OAuth authorization flow has expired (20 min TTL)",
"OAUTH_SCOPE_INVALID": "Invalid scope configuration",

# 中文
"OAUTH_STATE_MISMATCH": "OAuth state 校验失败，请重新发起授权",
"OAUTH_FLOW_EXPIRED": "OAuth 授权流程已过期（20 分钟有效期）",
"OAUTH_SCOPE_INVALID": "Scope 配置无效",
```

**注**: Controller 层目前直接使用已有错误码（`OAUTH_CODE_INVALID`、`OAUTH_MICROSOFT_AUTH_FAILED` 等），新增错误码为可选优化。

---

## 5. 前端实现

### 5.1 `templates/token_tool.html` — 独立页面模板

**模板模式**: 与 `login.html` 相同的独立模板（不继承 base），不依赖 `index.html` 的 SPA 框架。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token 获取工具 - OutlookEmailPlus</title>
    <link rel="icon" type="image/png" href="/img/ico.png">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}?v={{ APP_VERSION }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/token_tool.css') }}?v={{ APP_VERSION }}">
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
<body>
    <!-- 页面内容（详见 FD §6.2 布局设计） -->

    <script src="{{ url_for('static', filename='js/features/token_tool.js') }}?v={{ APP_VERSION }}"></script>
</body>
</html>
```

**关键技术细节**:

**Q1**: CSRF token 如何传递给 JS？
- **A**: 通过 `<meta name="csrf-token">` 标签注入，JS 从 `document.querySelector('meta[name="csrf-token"]').content` 读取，附加到 Fetch 请求的 `X-CSRFToken` header。这与 `index.html` 的 `/api/csrf-token` 端点方式不同，因为独立页面使用 Jinja2 直接注入更简单。

**Q2**: 版本号缓存控制？
- **A**: `?v={{ APP_VERSION }}` 参数利用 `app.py` 的静态文件缓存策略（line 130-136），带版本号时返回 `Cache-Control: public, max-age=31536000, immutable`。

### 5.2 `templates/popup_result.html` — 回调结果页

极简页面，仅用于 OAuth 弹窗中展示结果：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>OAuth 回调</title>
    <style>
        /* 内联样式，不引入外部 CSS（最小化加载） */
        body { font-family: system-ui; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
        .card { background: white; border-radius: 8px; padding: 32px; max-width: 400px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 4px; }
        .btn-primary { background: #0078d4; color: white; }
        .btn-secondary { background: #e0e0e0; }
        .guidance { color: #666; font-size: 14px; margin-top: 12px; }
    </style>
</head>
<body>
    {% if error %}
    <div class="card">
        <h2>⚠️ 授权未完成</h2>
        <p><strong>{{ error_code }}</strong></p>
        <p>{{ error_description }}</p>
        <p class="guidance">💡 {{ guidance }}</p>
        <button class="btn btn-secondary" onclick="window.close()">关闭</button>
    </div>
    {% else %}
    <div class="card">
        <h2>✅ 授权成功</h2>
        <p>请复制当前地址栏的完整 URL，粘贴到 Token 工具页面的「手动换取」区域</p>
        <button class="btn btn-primary" onclick="copyCurrentUrl()">📋 复制回调地址</button>
        <button class="btn btn-secondary" onclick="window.close()">关闭</button>
        <p id="copy-tip" style="display:none; color:green; margin-top:8px;">✓ 已复制</p>
    </div>
    {% endif %}

    <script>
    function copyCurrentUrl() {
        navigator.clipboard.writeText(window.location.href).then(function() {
            document.getElementById('copy-tip').style.display = 'block';
        });
    }
    </script>
</body>
</html>
```

**关键技术细节**:

**Q1**: 为什么使用内联样式而非引入 `main.css`？
- **A**: 弹窗页面极简，只有一个卡片 + 两个按钮。内联样式避免额外 HTTP 请求，加载更快。Microsoft OAuth 重定向后用户等待的是这个页面，快速渲染很重要。

### 5.3 `static/js/features/token_tool.js` — 前端逻辑

**模块结构**（遵循已有 `accounts.js`、`emails.js` 的全局函数模式）:

```javascript
// ==================== Token 工具 ====================

// CSRF token 读取
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

// 通用 Fetch 封装
async function tokenToolFetch(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF_TOKEN,
        ...(options.headers || {}),
    };
    const resp = await fetch(url, { ...options, headers });
    return resp.json();
}

// 页面加载时读取配置
async function loadOAuthConfig() {
    const data = await tokenToolFetch('/api/token-tool/config');
    if (data.success) {
        const config = data.data;
        document.getElementById('clientId').value = config.client_id || '';
        document.getElementById('clientSecret').value = config.client_secret || '';
        document.getElementById('redirectUri').value = config.redirect_uri || buildDefaultRedirectUri();
        document.getElementById('tenant').value = config.tenant || 'consumers';
        document.getElementById('promptConsent').checked = config.prompt_consent || false;
        // Scope chips 渲染
        renderScopeChips(config.scope || 'offline_access https://graph.microsoft.com/.default');
    }
}

// 生成授权 URL 并打开弹窗
async function startOAuth() {
    const config = collectFormConfig();
    const data = await tokenToolFetch('/api/token-tool/prepare', {
        method: 'POST',
        body: JSON.stringify(config),
    });
    if (data.success) {
        window.open(data.data.authorize_url, 'oauth-popup', 'width=600,height=700,scrollbars=yes');
        // 展开手动换取区域
        document.getElementById('manual-exchange').open = true;
    } else {
        showError(data.error?.message || '生成授权 URL 失败');
    }
}

// 手动粘贴换取 Token
async function exchangeToken() {
    const callbackUrl = document.getElementById('callbackUrl').value.trim();
    if (!callbackUrl) { showError('请粘贴回调 URL'); return; }

    const data = await tokenToolFetch('/api/token-tool/exchange', {
        method: 'POST',
        body: JSON.stringify({ callback_url: callbackUrl }),
    });
    if (data.success) {
        renderTokenResult(data.data);
    } else {
        showError(data.error?.message || '换取 Token 失败', data.error?.details);
    }
}

// 写入账号
async function saveToAccount(mode, accountId, email) {
    const resultData = getCurrentTokenResult();
    const data = await tokenToolFetch('/api/token-tool/save', {
        method: 'POST',
        body: JSON.stringify({
            mode: mode,
            account_id: accountId,
            email: email,
            refresh_token: resultData.refresh_token,
            client_id: resultData.client_id,
        }),
    });
    if (data.success) {
        showSuccess('Token 已写入账号');
    } else {
        showError(data.error?.message || '写入失败');
    }
}

// 保存配置
async function saveConfig() {
    const config = collectFormConfig();
    const data = await tokenToolFetch('/api/token-tool/config', {
        method: 'POST',
        body: JSON.stringify(config),
    });
    if (data.success) {
        showSuccess('配置已保存');
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', loadOAuthConfig);
```

**关键技术细节**:

**Q1**: 为什么不使用 `index.html` 的 `/api/csrf-token` 端点？
- **A**: Token 工具是独立页面，不走 SPA 路由。Jinja2 直接注入 `{{ csrf_token() }}` 到 `<meta>` 标签更高效，省去一次额外 API 请求。

**Q2**: `window.open` 的 popup 窗口会被浏览器拦截吗？
- **A**: 不会，因为 `window.open()` 在按钮 `onclick` 同步事件处理器中调用（用户主动交互触发）。浏览器只拦截非用户交互触发的弹窗。

### 5.4 主页面侧边栏入口

**文件**: `templates/index.html`

**位置**: 侧边栏导航区（`<nav class="sidebar-nav">` 内）

```html
{% if OAUTH_TOOL_ENABLED %}
<button class="nav-item" onclick="window.open('/token-tool', 'token-tool', 'width=720,height=860,scrollbars=yes')" title="Token 获取工具">
    🔑 Token 工具
</button>
{% endif %}
```

**注**: 使用 Jinja2 条件渲染，`OAUTH_TOOL_ENABLED=false` 时侧边栏不显示此入口。

---

## 6. 安全设计

### 6.1 PKCE 安全性

| 属性 | 值 | 说明 |
|------|------|------|
| `code_verifier` 长度 | 64 字节（86 字符 base64url） | 超过 RFC 7636 最低 43 字符要求 |
| Challenge 方法 | S256（SHA256） | 不使用 plain 方法 |
| 存储位置 | 内存 OAUTH_FLOW_STORE | 不持久化，20 分钟自动清理 |
| 生命周期 | 单次使用，换取后立即删除 | 防止重放攻击 |

### 6.2 State 双重校验

```
1. Session Cookie: session["oauth_state"] = state
   └── HttpOnly, Secure（生产环境）, SameSite=Lax
   └── 浏览器自动携带，防 CSRF

2. 内存 Store: OAUTH_FLOW_STORE[state] = flow_data
   └── 服务端校验，防伪造
   └── 20 分钟 TTL，防过期攻击

3. 校验逻辑:
   if session["oauth_state"] != request.state:  → 拒绝
   if state not in OAUTH_FLOW_STORE:            → 拒绝（过期或已使用）
   if both pass:                                → 继续换取
```

### 6.3 OAUTH_FLOW_STORE 线程安全

```python
OAUTH_FLOW_LOCK = Lock()

# 所有读写操作必须在锁内：
with OAUTH_FLOW_LOCK:
    _prune_expired()    # 每次操作前清理过期条目
    OAUTH_FLOW_STORE[state] = {...}

# 单进程约束（已有）：
# - Flask dev server: 单进程多线程（threaded=True）→ Lock 有效
# - Gunicorn workers=1: 单 worker 多线程 → Lock 有效
# - Docker: docker-compose.yml 中 gunicorn -w 1 → Lock 有效
```

### 6.4 敏感数据处理

| 数据 | 传输 | 存储 | 清理 |
|------|------|------|------|
| `client_secret` | HTTPS POST body | Settings 表 `encrypt_data()` | 不主动清理（用户手动更新） |
| `refresh_token` | HTTPS POST body | accounts 表 `encrypt_data()` | 由系统调度器管理 |
| `code_verifier` | 不传输（服务端生成+使用） | 内存 OAUTH_FLOW_STORE | 20 分钟 TTL + 单次使用后删除 |
| `authorization_code` | URL Query String（一次性） | 不存储 | 换取后由 Microsoft 失效 |
| `access_token` | HTTPS JSON body（仅返回给用户） | 不存储（不持久化） | 前端页面关闭即消失 |

---

## 7. 错误处理与日志

### 7.1 错误码定义

| 错误码 | HTTP | 触发场景 | 用户引导 |
|--------|------|----------|----------|
| `OAUTH_CONFIG_INVALID` | 400 | client_id/redirect_uri/scope 缺失或格式错误 | 检查表单填写 |
| `OAUTH_CODE_PARSE_FAILED` | 400 | 粘贴的 URL 缺少 code/state 参数 | 请完整复制回调地址栏 URL |
| `OAUTH_CODE_INVALID` | 400 | state 对应的 flow 已过期（>20 分钟） | 请重新发起授权 |
| `OAUTH_MICROSOFT_AUTH_FAILED` | 400 | state 校验失败（Session 不匹配） | 请重新发起授权 |
| `OAUTH_MICROSOFT_REQUEST_FAILED` | 400 | Microsoft token endpoint 返回错误 | 根据错误引导表操作 |
| `OAUTH_REFRESH_TOKEN_MISSING` | 400 | refresh_token 为空 | 确保 scope 包含 offline_access |
| `OAUTH_REDIRECT_URI_MISMATCH` | 400 | 回调地址与 Azure 配置不一致 | 检查 Azure 门户注册的 URI |
| `INTERNAL_ERROR` | 500 | 账号写入失败（DB 错误等） | 检查日志或联系管理员 |

### 7.2 日志记录

| 操作 | 级别 | 格式 |
|------|------|------|
| 授权 URL 生成 | INFO | `[oauth_tool] 授权 URL 已生成 (state={state[:8]}...)` |
| Flow 过期清理 | DEBUG | `[oauth_tool] 清理 {n} 个过期 flow` |
| Token 换取成功 | INFO | `[oauth_tool] Token 换取成功 (client_id={id[:8]}...)` |
| Token 换取失败 | WARNING | `[oauth_tool] Token 换取失败: {error_detail[:200]}` |
| Token 换取网络错误 | ERROR | `[oauth_tool] Token 换取网络错误: {exc}` |
| 配置保存 | AUDIT | `log_audit("update", "oauth_tool_config", ...)` |
| Token 写入账号 | AUDIT | `log_audit("create/update", "account", ...)` |

**日志模块**: `outlook_web.services.oauth_tool`、`outlook_web.controllers.token_tool`

---

## 8. 测试策略

> **详细测试设计**: 完整的测试用例、伪代码、Mock 策略与执行命令已移至独立 TDD 文档：
> `docs/TDD/2026-04-12-OAuth-Token获取工具TDD.md`
>
> 本节仅保留概要，详细用例请参阅 TDD 文档。

**测试文件**: `tests/test_oauth_tool.py`（单文件，多 TestCase 分组）

> v1.2 更新：TDD 评审后由原设计的两个文件（`test_oauth_tool_service.py` + `test_oauth_tool_api.py`）合并为一个文件，便于集中管理 fixture 与 helpers。

### 8.1 单元测试（29 个用例）

| 分组 | 用例数 | 覆盖范围 |
|------|--------|---------|
| PKCE 生成 | 4 | verifier 长度/字符集/S256 算法/随机性 |
| Scope 校验 | 7 | 合法通过/缺少 API scope/混用/跨资源/自动补全 |
| FLOW_STORE | 6 | CRUD/TTL 未过期/TTL 过期/选择性清理/线程安全/不存在 key |
| 错误引导映射 | 4 | unauthorized_client/invalid_grant/invalid_scope/未知错误 |
| JWT 解码 | 3 | 正常解码/无效格式/缺少填充 |
| Token 交换 | 5 | 成功/invalid_grant/网络超时/state 无效/Flow 消费 |

**Mock 策略**:
- `requests.post()` → Mock，不真实调用 Microsoft
- `time.time()` → Mock，测试 TTL 过期
- `graph.test_refresh_token_with_rotation()` → Mock，测试 save 流程

### 8.2 集成测试（28 个用例）

| 分组 | 用例数 | 覆盖范围 |
|------|--------|---------|
| prepare 端点 | 5 | 成功/Scope 非法/缺 client_id/未登录/Flow 存储 |
| exchange 端点 | 5 | 成功/缺 state/Flow 过期/缺 code/未登录 |
| config 端点 | 5 | 保存读取/加密存储/脱敏返回/环境变量覆盖/未登录 |
| save 端点 | 6 | 更新已有/新建/验证失败/不存在 ID/字段保持/未登录 |
| Blueprint 开关 | 3 | 页面可达/页面 404/API 404 |
| 账号列表 | 4 | 非敏感字段/排除敏感/空列表/未登录 |

**测试环境**:
- 使用 Flask test_client
- 临时 SQLite 数据库
- Mock `requests.post` 和 `graph_service.test_refresh_token_with_rotation`

### 8.3 前端测试

手动验收（非自动化）— 8 个场景:

| 场景 | 验收标准 |
|------|---------|
| 本地 localhost | 完整 OAuth 流程可走通 |
| Docker 部署 | 手动粘贴回调 URL 可换取 Token |
| 配置保存/加载 | 刷新页面后配置仍在 |
| Scope 预设按钮 | Graph 邮件 / IMAP 预设正确填充 |
| 写入已有账号 | 账号列表显示正确，Token 更新后状态恢复 active |
| 创建新账号 | 新账号出现在账号列表 |
| 开关关闭 | 侧边栏不显示入口，直接访问 /token-tool 返回 404 |
| 错误引导 | 使用错误 client_id 授权，错误提示含引导文本 |

**合计**: 自动化 57 个 + 手动验收 8 个 = **65 个测试点**

---

## 9. 实施计划

### 9.1 里程碑 M1: 后端核心（Service + Repository + Config）

**任务清单**:
- [ ] `config.py`: 新增 6 个环境变量函数
- [ ] `repositories/settings.py`: 新增 6 个 OAuth getter 函数
- [ ] `services/oauth_tool.py`: 完整 Service 层（PKCE、Flow Store、Scope 校验、Token 换取、错误引导）
- [ ] `errors.py`: 补充新增错误码（如需要）
- [ ] `tests/test_oauth_tool_service.py`: Service 层单元测试

**验收标准**:
- [ ] 所有 Service 层单元测试通过
- [ ] PKCE + Scope 校验 + Flow Store TTL 测试覆盖

### 9.2 里程碑 M2: 后端路由（Blueprint + Controller）

**任务清单**:
- [ ] `routes/token_tool.py`: Blueprint 定义（8 个路由）
- [ ] `controllers/token_tool.py`: 全部 8 个 Controller 函数
- [ ] `app.py`: 条件注册 + Context Processor
- [ ] `tests/test_oauth_tool_api.py`: API 集成测试

**验收标准**:
- [ ] API 集成测试通过
- [ ] `OAUTH_TOOL_ENABLED=false` 时 Blueprint 不注册

### 9.3 里程碑 M3: 前端（模板 + JS + CSS）

**任务清单**:
- [ ] `templates/token_tool.html`: 独立页面模板
- [ ] `templates/popup_result.html`: 回调结果页
- [ ] `static/js/features/token_tool.js`: 前端逻辑
- [ ] `static/css/token_tool.css`: 页面样式
- [ ] `templates/index.html`: 侧边栏新增入口

**验收标准**:
- [ ] 本地 localhost 完整 OAuth 流程可走通
- [ ] Docker 部署手动粘贴模式可用

### 9.4 里程碑 M4: 文档与发布

**任务清单**:
- [ ] `CHANGELOG.md`: 新增版本记录
- [ ] `README.md` / `README.en.md`: 新增功能说明
- [ ] `.env.example`: 新增环境变量
- [ ] `docker-compose.yml`: 新增环境变量示例
- [ ] 全量测试通过

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| OAUTH_FLOW_STORE 内存泄漏 | 长时间运行后内存增长 | 每次操作自动 prune 过期条目 + 20 分钟 TTL |
| 多 worker 部署破坏 State 校验 | 用户在 worker A 启动 flow，回调到 worker B | 文档明确单 worker 约束（已有约束，调度器也依赖） |
| Microsoft OAuth 端点超时 | 用户等待过长 | `timeout=15` 秒 + 友好错误提示 |
| 浏览器弹窗被拦截 | OAuth 弹窗无法打开 | window.open 在用户 click 事件中调用（不会被拦截） |
| CSRF token 过期 | 长时间停留页面后操作失败 | 独立模板使用 Jinja2 注入，与页面生命周期一致 |
| Secret Key 变更导致解密失败 | 已保存的 client_secret 无法解密 | `decrypt_data()` 有异常处理，getter 返回空字符串 |
| 回调 URI 配置不一致 | Microsoft 拒绝回调 | 错误引导表提示用户检查 Azure 门户配置 |

---

## 11. 未来优化方向（P2）

1. **postMessage 自动回传**: 回调页面通过 `window.opener.postMessage()` 自动将 code 传回主页面，省去手动复制步骤
2. **Redis OAUTH_FLOW_STORE**: 支持多 worker 部署
3. **Token 到期预警**: 在仪表盘显示 Token 即将过期的账号
4. **批量获取向导**: 支持多个账号连续获取 Token（不重复填写配置）
5. **IMAP Token 快捷模式**: 预填 IMAP scope，一键获取 IMAP 专用 Token
6. **内置默认 Client ID**: 项目预注册公共 Azure 应用，新用户零配置使用

---

**文档结束**
