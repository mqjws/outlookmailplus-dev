# TDD: OAuth Token 获取工具

- 文档版本: v1.3
- 创建日期: 2026-04-12
- 更新日期: 2026-04-16（v1.3 — 会话文档按实际实现口径再同步）
- 文档类型: 测试设计文档（TDD）
- 关联 PRD: `docs/PRD/2026-04-12-OAuth-Token获取工具PRD.md`
- 关联 FD: `docs/FD/2026-04-12-OAuth-Token获取工具FD.md`
- 关联 TD: `docs/TD/2026-04-12-OAuth-Token获取工具TD.md`
- 目标版本: v1.15.0

> **v1.15.0 实施收口说明（兼容账号导入模式）**
>
> 当前自动化测试已按兼容账号导入模式调整：
> - 配置接口返回固定空 `client_secret` 与 `tenant=consumers`
> - `prepare / config / save` 需覆盖拒绝非空 `client_secret` 与非 `consumers` tenant 的场景
> - 后端配置默认 Scope 断言为 IMAP 兼容预设；前端首次展示默认 Graph 预设
> - 当前本地专项回归基线已扩展为 `64` 条用例
> - `unauthorized_client` 的引导应明确提示“应用必须支持个人 Microsoft 账号 + 开启公共客户端流”
> - `AADSTS9002331` 的引导应明确提示：不要使用 `PersonalMicrosoftAccount`，而应切到 `AzureADandPersonalMicrosoftAccount`
> - 若文档涉及 Azure 门户切换 Supported account types，应补充 `api.requestedAccessTokenVersion = 2` 的前置约束
> - 2026-04-16 前端已加入新手引导折叠记忆（`token_tool_guide_dismissed`）与教程链接扩展位（`GUIDE_TUTORIAL_LINKS`）
> - 2026-04-16 会话回归记录：unittest 分批执行累计 `1158 passed / 7 skipped`；Jest 在当前环境因缺少 `jest-environment-jsdom` 未通过（环境依赖问题）
>
> 文中早前关于 `client_secret` 加密存储回传、可变 tenant、tenant-aware / client-secret-aware 保存验证的测试设计，均属于历史口径，不再作为当前测试基线。

> 注：本文主体保留了实施前测试设计清单，便于追溯；与当前仓库实现冲突时，以 `outlook_web/controllers/token_tool.py`、`templates/token_tool.html`、`static/js/features/token_tool.js` 和现有测试结果为准。

---

## 1. 文档目标

本文档仅讨论「OAuth Token 获取工具」的**测试设计**，不重复展开业务需求与实现细节。

本 TDD 重点回答以下问题：

1. OAuth2 Authorization Code + PKCE 流程中**哪些环节必须用自动化测试覆盖**，哪些仅做人工验收。
2. 如何在**不依赖真实 Microsoft OAuth 端点**的前提下，高可信验证 Token 换取全链路。
3. FLOW_STORE（内存状态）的**线程安全与 TTL 过期**如何在测试中可靠复现。
4. 配置读写链（Settings 表 + 环境变量 + 加密存储）的**优先级与持久化**如何断言。
5. Token 写入已有账号 / 新建账号的**兼容性与数据完整性**如何验证（尤其 `update_account()` 的必填参数约束）。
6. Blueprint 条件注册（`OAUTH_TOOL_ENABLED` 开关）如何测试。

---

## 2. 测试目标（必须同时成立）

本次测试目标不是"接口能通"，而是证明以下五件事同时成立：

1. **PKCE 安全性**: `code_verifier` 与 `code_challenge` 的生成符合 RFC 7636 规范，长度与编码正确。
2. **Scope 防护正确**: 非法 scope（跨资源、`.default` 混用）被拦截；合法 scope 通过且自动补 `offline_access`。
3. **FLOW_STORE 可靠**: 状态存取线程安全、TTL 过期自动清理、并发读写无竞态。
4. **Token 换取链路**: prepare → 用户授权 → exchange 的完整链路中，state/PKCE 校验严格，Microsoft 返回正确解析。
5. **账号写入兼容**: Token 写入已有账号时正确回传 `email_addr`/`group_id`/`remark` 等必填字段；新建账号时正确调用 `add_account()`。

---

## 3. 测试原则

### 3.1 测试优先级（按风险排序）

1. **Service 层核心逻辑**（PKCE 生成、Scope 校验、FLOW_STORE CRUD/TTL/线程安全、Token 交换、错误引导映射）
2. **Controller/API 集成**（prepare/exchange/save/config 端点、参数校验、认证拦截）
3. **配置读写与加密**（Settings 优先级链、client_secret 加密存储验证）
4. **Blueprint 开关**（enabled/disabled 状态下的路由可达性）
5. **前端手动验收**（OAuth 流程端到端、UI 交互）

### 3.2 测试策略

遵循"**单元为主，接口集成为核心，人工冒烟兜底**"的策略：

- Service 单元测试：50% ~ 60%
- Controller/API 集成测试：30% ~ 40%
- 前端手动验收：10%（不写自动化）

### 3.3 明确不做（本期不强制）

1. 真实 Microsoft OAuth 端点的端到端自动化（避免外部依赖与 token 泄漏）
2. 浏览器级 E2E 自动化（Selenium/Playwright）
3. 性能/压测（OAuth 工具为低频操作，无需压测）
4. 前端 JS 单元测试（`token_tool.js` 逻辑简单，手动验收即可）

---

## 4. 测试文件与分层设计

> **设计决策**: 采用**单文件方案** — 所有测试集中在 `tests/test_oauth_tool.py` 中，通过多个 TestCase 子类按职责分组。
>
> **理由**: OAuth Token 工具是独立功能模块，单文件便于集中管理 fixture 与 helpers，避免跨文件维护成本。

> 说明：本项目测试入口统一使用 `tests/_import_app.py`，其会将 `DATABASE_PATH` 指向临时 DB 文件，并禁用调度器自启动。

### 4.0 文件结构

```
tests/test_oauth_tool.py
├── OAuthToolTestBase             # 基类 — 共享 setup/helpers
├── OAuthToolPkceTests            # PKCE 生成测试
├── OAuthToolScopeTests           # Scope 校验测试
├── OAuthToolFlowStoreTests       # FLOW_STORE CRUD/TTL/线程安全
├── OAuthToolErrorGuidanceTests   # 错误引导映射
├── OAuthToolJwtDecodeTests       # JWT Payload 解码
├── OAuthToolTokenExchangeTests   # Token 交换 (Service 层 mock)
├── OAuthToolApiPrepareTests      # /api/token-tool/prepare 接口测试
├── OAuthToolApiExchangeTests     # /api/token-tool/exchange 接口测试
├── OAuthToolApiConfigTests       # /api/token-tool/config 配置接口测试
├── OAuthToolApiSaveTests         # /api/token-tool/save 账号写入测试
├── OAuthToolApiBlueprintTests    # Blueprint 开关 / 页面访问
└── OAuthToolApiAccountListTests  # /api/token-tool/accounts 列表测试
```

---

### 4.1 基类设计（OAuthToolTestBase）

```python
import unittest
import uuid
from unittest.mock import patch, MagicMock
from tests._import_app import clear_login_attempts, import_web_app_module


class OAuthToolTestBase(unittest.TestCase):
    """OAuth Token 工具测试基类 — 所有子类共享"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            db = get_db()
            # 清理测试相关表
            db.execute("DELETE FROM settings WHERE key LIKE 'oauth_tool_%'")
            db.execute("DELETE FROM accounts WHERE email_addr LIKE '%@oauth-test%'")
            db.commit()

    # ---- Helpers ----

    def _login(self, client, password="testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))
        return resp

    def _save_oauth_config(self, client, **overrides):
        """保存 OAuth 配置的便捷方法"""
        payload = {
            "client_id": "test-client-id-000",
            "tenant_id": "common",
            "scope": "offline_access https://graph.microsoft.com/.default",
            "redirect_uri": "http://localhost:5000/token-tool/callback",
            **overrides,
        }
        return client.post("/api/token-tool/config", json=payload)

    def _insert_test_account(self, email="user@oauth-test.com",
                              client_id="old-client-id",
                              refresh_token="old-rt"):
        """向 DB 插入测试账号，返回 account_id"""
        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo
            accounts_repo.add_account(
                email_addr=email,
                password="",
                client_id=client_id,
                refresh_token=refresh_token,
                group_id=1,
                remark="oauth-test",
            )
            acc = accounts_repo.get_account_by_email(email)
            return acc["id"] if acc else None

    @staticmethod
    def _mock_microsoft_token_response(
        access_token="mock-at",
        refresh_token="mock-new-rt",
        expires_in=3600,
        scope="offline_access https://graph.microsoft.com/.default",
    ):
        """构造 Microsoft Token 端点成功响应"""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "scope": scope,
            "token_type": "Bearer",
        }
        return resp

    @staticmethod
    def _mock_microsoft_error_response(error="invalid_grant",
                                        description="Token expired"):
        """构造 Microsoft Token 端点失败响应"""
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "error": error,
            "error_description": description,
        }
        return resp
```

**设计要点**:

| 要素 | 说明 |
|------|------|
| `setUpClass` | 一次性导入 app，所有子类共享 |
| `setUp` 清理 | 删除 `oauth_tool_%` 配置 + 测试账号，防止测试间互影响 |
| `_login()` | 标准登录 helper，复用项目惯例 |
| `_save_oauth_config()` | 配置保存便捷方法，减少重复 |
| `_insert_test_account()` | 通过 `add_account()` 写入测试账号 |
| `_mock_microsoft_*()` | Microsoft Token 端点响应构造器 |

---

### 4.2 Service 层 — PKCE 生成测试（OAuthToolPkceTests）

**目标**: 验证 PKCE code_verifier 与 code_challenge 生成符合 RFC 7636 规范。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-PKCE-01 | `test_generate_pkce_verifier_length` | 生成 PKCE | `code_verifier` 长度 ≥ 43 且 ≤ 128 |
| S-PKCE-02 | `test_generate_pkce_verifier_charset` | 字符合法性 | `code_verifier` 仅含 `[A-Za-z0-9\-._~]` |
| S-PKCE-03 | `test_generate_pkce_challenge_is_s256` | S256 算法 | `code_challenge` = base64url(SHA256(verifier))，无填充 |
| S-PKCE-04 | `test_generate_pkce_uniqueness` | 随机性 | 连续两次调用返回不同 verifier |

**伪代码**:

```python
class OAuthToolPkceTests(OAuthToolTestBase):

    def test_generate_pkce_verifier_length(self):
        from outlook_web.services.oauth_tool import generate_pkce
        verifier, challenge = generate_pkce()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

    def test_generate_pkce_verifier_charset(self):
        import re
        from outlook_web.services.oauth_tool import generate_pkce
        verifier, _ = generate_pkce()
        self.assertRegex(verifier, r'^[A-Za-z0-9\-._~]+$')

    def test_generate_pkce_challenge_is_s256(self):
        import hashlib, base64
        from outlook_web.services.oauth_tool import generate_pkce
        verifier, challenge = generate_pkce()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)

    def test_generate_pkce_uniqueness(self):
        from outlook_web.services.oauth_tool import generate_pkce
        v1, _ = generate_pkce()
        v2, _ = generate_pkce()
        self.assertNotEqual(v1, v2)
```

---

### 4.3 Service 层 — Scope 校验测试（OAuthToolScopeTests）

**目标**: 验证 scope 白名单校验与自动补全逻辑。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-SCOPE-01 | `test_validate_scope_graph_default_ok` | `offline_access https://graph.microsoft.com/.default` | 无错误返回 |
| S-SCOPE-02 | `test_validate_scope_imap_ok` | `offline_access https://outlook.office365.com/IMAP.AccessAsUser.All` | 无错误返回 |
| S-SCOPE-03 | `test_validate_scope_no_api_scope` | `offline_access` （缺少 API scope） | 返回错误信息 |
| S-SCOPE-04 | `test_validate_scope_mixed_default_and_named` | `.default` 与命名 scope 混用 | 返回错误信息 |
| S-SCOPE-05 | `test_validate_scope_cross_resource` | 同时包含 graph 与 outlook 域 | 返回错误信息 |
| S-SCOPE-06 | `test_normalize_scope_auto_adds_offline_access` | 只传 API scope 无 `offline_access` | 结果包含 `offline_access` |
| S-SCOPE-07 | `test_normalize_scope_no_duplicate` | 已含 `offline_access` | 不重复添加 |

**伪代码**:

```python
class OAuthToolScopeTests(OAuthToolTestBase):

    def test_validate_scope_graph_default_ok(self):
        from outlook_web.services.oauth_tool import validate_scope
        err = validate_scope("offline_access https://graph.microsoft.com/.default")
        self.assertIsNone(err)

    def test_validate_scope_cross_resource(self):
        from outlook_web.services.oauth_tool import validate_scope
        err = validate_scope(
            "https://graph.microsoft.com/Mail.Read "
            "https://outlook.office365.com/IMAP.AccessAsUser.All"
        )
        self.assertIsNotNone(err)
        self.assertIn("跨资源", err)  # 错误信息应提示跨资源

    def test_normalize_scope_auto_adds_offline_access(self):
        from outlook_web.services.oauth_tool import normalize_scope
        result = normalize_scope("https://graph.microsoft.com/.default")
        self.assertIn("offline_access", result)
```

---

### 4.4 Service 层 — FLOW_STORE 测试（OAuthToolFlowStoreTests）

**目标**: 验证内存状态存储的 CRUD、TTL 过期清理、线程安全。

> **测试难点**: FLOW_STORE 使用 `time.time()` 判断过期，需要 Mock 时间来可靠复现 TTL。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-FLOW-01 | `test_flow_store_crud` | 存入 → 读取 → 删除 | store 后 get 有值；discard 后 get 为 None |
| S-FLOW-02 | `test_flow_store_ttl_not_expired` | 存入后立即读取 | get 返回非 None |
| S-FLOW-03 | `test_flow_store_ttl_expired` | Mock time 推进 > 20 分钟 | get 返回 None |
| S-FLOW-04 | `test_flow_store_cleanup_removes_expired_only` | 多条记录，部分过期 | cleanup 只删过期的，未过期的仍存在 |
| S-FLOW-05 | `test_flow_store_thread_safety` | 多线程并发写入/读取 | 无异常；所有写入可读回 |
| S-FLOW-06 | `test_flow_store_get_nonexistent_key` | 读取不存在的 key | 返回 None，无异常 |

**伪代码**:

```python
import threading
import time as real_time

class OAuthToolFlowStoreTests(OAuthToolTestBase):

    def test_flow_store_crud(self):
        from outlook_web.services.oauth_tool import store_flow, get_flow, discard_flow
        state = "test-state-" + uuid.uuid4().hex
        flow_data = {"code_verifier": "abc", "scope": "test"}
        store_flow(state, flow_data)
        self.assertEqual(get_flow(state), flow_data)
        discard_flow(state)
        self.assertIsNone(get_flow(state))

    @patch("outlook_web.services.oauth_tool.time")
    def test_flow_store_ttl_expired(self, mock_time):
        from outlook_web.services.oauth_tool import store_flow, get_flow
        # 存入时的时间
        mock_time.time.return_value = 1000.0
        state = "ttl-test-" + uuid.uuid4().hex
        store_flow(state, {"code_verifier": "x"})
        # 推进 21 分钟（1260 秒）
        mock_time.time.return_value = 1000.0 + 1260
        self.assertIsNone(get_flow(state))

    def test_flow_store_thread_safety(self):
        from outlook_web.services.oauth_tool import store_flow, get_flow
        results = {}
        errors = []

        def writer(i):
            try:
                key = f"thread-{i}"
                store_flow(key, {"i": i})
                val = get_flow(key)
                results[i] = val
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(errors), 0, f"线程安全错误: {errors}")
        self.assertEqual(len(results), 20)
```

> **Mock 说明**: `time.time()` 的 mock 路径取决于 `oauth_tool.py` 中的导入方式。若使用 `import time` 则 mock `outlook_web.services.oauth_tool.time`；若使用 `from time import time` 则 mock `outlook_web.services.oauth_tool.time`（函数级）。实现阶段需根据实际代码调整。

---

### 4.5 Service 层 — 错误引导映射（OAuthToolErrorGuidanceTests）

**目标**: 验证 Microsoft 错误码到用户友好引导文本的映射。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-ERR-01 | `test_map_unauthorized_client` | `error=unauthorized_client` | 返回包含"Azure 注册"/"Redirect URI"引导文本 |
| S-ERR-02 | `test_map_invalid_grant` | `error=invalid_grant` | 返回包含"授权码过期"/"重试"引导 |
| S-ERR-03 | `test_map_invalid_scope` | `error=invalid_scope` | 返回包含"scope 不正确"引导 |
| S-ERR-04 | `test_map_unknown_error` | `error=some_random_error` | 返回通用引导（不抛异常） |

**伪代码**:

```python
class OAuthToolErrorGuidanceTests(OAuthToolTestBase):

    def test_map_unauthorized_client(self):
        from outlook_web.services.oauth_tool import map_error_guidance
        guidance = map_error_guidance("unauthorized_client")
        self.assertIsNotNone(guidance)
        self.assertIsInstance(guidance, str)
        self.assertTrue(len(guidance) > 0)

    def test_map_unknown_error(self):
        from outlook_web.services.oauth_tool import map_error_guidance
        guidance = map_error_guidance("completely_unknown_xyz")
        self.assertIsNotNone(guidance)  # 应返回通用引导而非 None
```

---

### 4.6 Service 层 — JWT Payload 解码（OAuthToolJwtDecodeTests）

**目标**: 验证无需验签的 JWT payload 提取（仅用于显示 token 详情，不用于安全校验）。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-JWT-01 | `test_decode_jwt_extracts_fields` | 标准 JWT (header.payload.signature) | 正确提取 `aud`、`scp`、`exp` 等字段 |
| S-JWT-02 | `test_decode_jwt_invalid_format` | 非 JWT 字符串 | 返回 None 或空 dict，不抛异常 |
| S-JWT-03 | `test_decode_jwt_missing_padding` | Base64 缺少 `=` 填充 | 自动补齐，正确解码 |

**伪代码**:

```python
import base64, json

class OAuthToolJwtDecodeTests(OAuthToolTestBase):

    def test_decode_jwt_extracts_fields(self):
        from outlook_web.services.oauth_tool import decode_jwt_payload
        # 构造测试 JWT
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256"}).encode()
        ).rstrip(b"=").decode()
        payload_data = {"aud": "https://graph.microsoft.com", "scp": "Mail.Read", "exp": 9999999999}
        payload = base64.urlsafe_b64encode(
            json.dumps(payload_data).encode()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}.fake-signature"

        result = decode_jwt_payload(token)
        self.assertEqual(result.get("aud"), "https://graph.microsoft.com")
        self.assertEqual(result.get("scp"), "Mail.Read")

    def test_decode_jwt_invalid_format(self):
        from outlook_web.services.oauth_tool import decode_jwt_payload
        result = decode_jwt_payload("not-a-jwt")
        self.assertIsNotNone(result)  # 应返回空 dict 而非 None
        self.assertEqual(len(result), 0)
```

---

### 4.7 Service 层 — Token 交换（OAuthToolTokenExchangeTests）

**目标**: 验证 Service 层对 Microsoft token 端点调用的封装，包括成功、失败、网络异常场景。

> **核心 Mock**: `requests.post()` — 必须 mock，绝不能真实调用 Microsoft。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| S-EXCH-01 | `test_exchange_token_success` | Microsoft 返回 200 | 返回包含 `access_token`、`refresh_token` 的 dict |
| S-EXCH-02 | `test_exchange_token_invalid_grant` | Microsoft 返回 400 invalid_grant | 返回错误信息 + 错误引导 |
| S-EXCH-03 | `test_exchange_token_network_timeout` | `requests.post` 抛 `Timeout` | 返回网络超时错误，不崩溃 |
| S-EXCH-04 | `test_exchange_token_validates_state` | state 不在 FLOW_STORE 中 | 返回错误（state 无效/已过期） |
| S-EXCH-05 | `test_exchange_token_consumes_flow` | 成功换取后 | FLOW_STORE 中对应 state 已被清除（防重放） |

**伪代码**:

```python
class OAuthToolTokenExchangeTests(OAuthToolTestBase):

    @patch("outlook_web.services.oauth_tool.requests.post")
    def test_exchange_token_success(self, mock_post):
        from outlook_web.services.oauth_tool import (
            exchange_token, store_flow, get_flow
        )
        mock_post.return_value = self._mock_microsoft_token_response()
        state = "exch-test-" + uuid.uuid4().hex
        store_flow(state, {
            "code_verifier": "test-verifier",
            "scope": "offline_access https://graph.microsoft.com/.default",
            "redirect_uri": "http://localhost:5000/token-tool/callback",
            "client_id": "test-cid",
            "tenant_id": "common",
        })

        result = exchange_token(state=state, code="mock-auth-code")
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("refresh_token"), "mock-new-rt")
        self.assertEqual(result.get("access_token"), "mock-at")

    @patch("outlook_web.services.oauth_tool.requests.post")
    def test_exchange_token_invalid_grant(self, mock_post):
        from outlook_web.services.oauth_tool import exchange_token, store_flow
        mock_post.return_value = self._mock_microsoft_error_response(
            "invalid_grant", "AADSTS70000: The provided value for the input parameter 'code' is not valid."
        )
        state = "exch-fail-" + uuid.uuid4().hex
        store_flow(state, {
            "code_verifier": "v", "scope": "s",
            "redirect_uri": "http://localhost:5000/token-tool/callback",
            "client_id": "cid", "tenant_id": "common",
        })

        result = exchange_token(state=state, code="bad-code")
        self.assertFalse(result.get("success"))
        self.assertIn("invalid_grant", result.get("error", ""))

    @patch("outlook_web.services.oauth_tool.requests.post")
    def test_exchange_token_network_timeout(self, mock_post):
        import requests as real_requests
        from outlook_web.services.oauth_tool import exchange_token, store_flow
        mock_post.side_effect = real_requests.exceptions.Timeout("Connection timed out")
        state = "timeout-" + uuid.uuid4().hex
        store_flow(state, {
            "code_verifier": "v", "scope": "s",
            "redirect_uri": "r", "client_id": "c", "tenant_id": "t",
        })

        result = exchange_token(state=state, code="code")
        self.assertFalse(result.get("success"))

    def test_exchange_token_validates_state(self):
        from outlook_web.services.oauth_tool import exchange_token
        result = exchange_token(state="nonexistent-state", code="code")
        self.assertFalse(result.get("success"))

    @patch("outlook_web.services.oauth_tool.requests.post")
    def test_exchange_token_consumes_flow(self, mock_post):
        from outlook_web.services.oauth_tool import (
            exchange_token, store_flow, get_flow
        )
        mock_post.return_value = self._mock_microsoft_token_response()
        state = "consume-" + uuid.uuid4().hex
        store_flow(state, {
            "code_verifier": "v", "scope": "s",
            "redirect_uri": "r", "client_id": "c", "tenant_id": "t",
        })

        exchange_token(state=state, code="code")
        # Flow 应已被消费
        self.assertIsNone(get_flow(state))
```

---

### 4.8 API 集成 — prepare 端点（OAuthToolApiPrepareTests）

**目标**: 验证 `/api/token-tool/prepare` 端点的参数校验与授权 URL 生成。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-PREP-01 | `test_prepare_returns_auth_url` | 合法参数 | 200；response 含 `auth_url`；URL 包含 `code_challenge`、`state`、`response_type=code` |
| A-PREP-02 | `test_prepare_invalid_scope_rejected` | `.default` 混用命名 scope | 400；error code 为 `OAUTH_CONFIG_INVALID` 或等价 |
| A-PREP-03 | `test_prepare_missing_client_id` | 不传 client_id | 400 |
| A-PREP-04 | `test_prepare_requires_login` | 未登录 | 401 |
| A-PREP-05 | `test_prepare_stores_flow` | 调用后检查 FLOW_STORE | state 对应的 flow 存在 |

**伪代码**:

```python
class OAuthToolApiPrepareTests(OAuthToolTestBase):

    def test_prepare_returns_auth_url(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/prepare", json={
                "client_id": "test-cid",
                "tenant_id": "common",
                "scope": "offline_access https://graph.microsoft.com/.default",
                "redirect_uri": "http://localhost:5000/token-tool/callback",
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))
            auth_url = data.get("auth_url", "")
            self.assertIn("code_challenge=", auth_url)
            self.assertIn("response_type=code", auth_url)
            self.assertIn("state=", auth_url)

    def test_prepare_invalid_scope_rejected(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/prepare", json={
                "client_id": "cid",
                "tenant_id": "common",
                "scope": "https://graph.microsoft.com/.default https://graph.microsoft.com/Mail.Read",
                "redirect_uri": "http://localhost:5000/token-tool/callback",
            })
            self.assertEqual(resp.status_code, 400)

    def test_prepare_requires_login(self):
        with self.app.test_client() as client:
            resp = client.post("/api/token-tool/prepare", json={
                "client_id": "cid",
                "tenant_id": "common",
                "scope": "offline_access https://graph.microsoft.com/.default",
                "redirect_uri": "http://localhost:5000/token-tool/callback",
            })
            self.assertIn(resp.status_code, (401, 302))
```

---

### 4.9 API 集成 — exchange 端点（OAuthToolApiExchangeTests）

**目标**: 验证 `/api/token-tool/exchange` 端点的 state 校验与 token 换取链路。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-EXCH-01 | `test_exchange_success` | 合法 state + mock Microsoft 200 | 200；返回 refresh_token |
| A-EXCH-02 | `test_exchange_missing_state` | 不传 state | 400 |
| A-EXCH-03 | `test_exchange_expired_flow` | state 已过期 | 400；error 包含过期提示 |
| A-EXCH-04 | `test_exchange_missing_code` | 不传 code | 400 |
| A-EXCH-05 | `test_exchange_requires_login` | 未登录 | 401 |

**伪代码**:

```python
class OAuthToolApiExchangeTests(OAuthToolTestBase):

    @patch("outlook_web.services.oauth_tool.requests.post")
    def test_exchange_success(self, mock_post):
        mock_post.return_value = self._mock_microsoft_token_response()
        with self.app.test_client() as client:
            self._login(client)
            # 先 prepare 获取 state
            prep_resp = client.post("/api/token-tool/prepare", json={
                "client_id": "cid", "tenant_id": "common",
                "scope": "offline_access https://graph.microsoft.com/.default",
                "redirect_uri": "http://localhost:5000/token-tool/callback",
            })
            auth_url = prep_resp.get_json().get("auth_url", "")
            # 从 URL 提取 state
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(auth_url).query)
            state = qs.get("state", [""])[0]

            # 用 state + mock code 进行 exchange
            exch_resp = client.post("/api/token-tool/exchange", json={
                "state": state,
                "code": "mock-auth-code",
            })
            self.assertEqual(exch_resp.status_code, 200)
            data = exch_resp.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("refresh_token", data)

    def test_exchange_missing_state(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/exchange", json={
                "code": "some-code",
            })
            self.assertEqual(resp.status_code, 400)

    def test_exchange_expired_flow(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/exchange", json={
                "state": "definitely-not-in-store",
                "code": "some-code",
            })
            self.assertEqual(resp.status_code, 400)
```

---

### 4.10 API 集成 — config 端点（OAuthToolApiConfigTests）

**目标**: 验证配置的保存、读取、加密存储。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-CFG-01 | `test_config_save_and_load` | POST 保存 → GET 读取 | 值一致 |
| A-CFG-02 | `test_config_secret_encrypted_in_db` | 保存含 client_secret | Settings 表中值以 `enc:` 前缀存储 |
| A-CFG-03 | `test_config_load_returns_masked_secret` | 读取配置 | client_secret 脱敏（如 `***`） 或不返回 |
| A-CFG-04 | `test_config_env_override` | 环境变量设置 client_id | GET 返回环境变量优先 |
| A-CFG-05 | `test_config_requires_login` | 未登录 | 401 |

**伪代码**:

```python
class OAuthToolApiConfigTests(OAuthToolTestBase):

    def test_config_save_and_load(self):
        with self.app.test_client() as client:
            self._login(client)
            # 保存
            save_resp = self._save_oauth_config(client, client_id="my-cid-123")
            self.assertEqual(save_resp.status_code, 200)
            # 读取
            load_resp = client.get("/api/token-tool/config")
            self.assertEqual(load_resp.status_code, 200)
            data = load_resp.get_json()
            self.assertEqual(data.get("client_id"), "my-cid-123")

    def test_config_secret_encrypted_in_db(self):
        with self.app.test_client() as client:
            self._login(client)
            self._save_oauth_config(client, client_secret="super-secret-value")
        # 直接查 DB
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo
            raw = settings_repo.get_setting("oauth_tool_client_secret", "")
            self.assertTrue(
                raw.startswith("enc:"),
                f"client_secret 应加密存储，实际: {raw[:20]}..."
            )

    def test_config_requires_login(self):
        with self.app.test_client() as client:
            resp = client.get("/api/token-tool/config")
            self.assertIn(resp.status_code, (401, 302))
```

---

### 4.11 API 集成 — save 端点（OAuthToolApiSaveTests）

**目标**: 验证 Token 写入已有账号与新建账号的逻辑。

> **关键约束**: `update_account()` 的 `email_addr`、`group_id`、`remark` 参数为必填（非 Optional），传 None 会导致 `return False`。TD 中的修复方案是先通过 `get_account_by_id()` 获取现有数据再回传。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-SAVE-01 | `test_save_update_existing_account` | 指定已存在 account_id | 账号 client_id/refresh_token 已更新；email_addr/group_id/remark 未被覆盖 |
| A-SAVE-02 | `test_save_create_new_account` | 不指定 account_id，提供 email | 新账号被创建；client_id/refresh_token 正确 |
| A-SAVE-03 | `test_save_validates_refresh_token` | Mock `test_refresh_token_with_rotation` 失败 | 400；提示 token 验证失败 |
| A-SAVE-04 | `test_save_nonexistent_account_id` | 指定不存在的 account_id | 400；提示账号不存在 |
| A-SAVE-05 | `test_save_preserves_account_fields` | 更新已有账号 | 更新后 `email_addr`、`group_id`、`remark` 与原值一致 |
| A-SAVE-06 | `test_save_requires_login` | 未登录 | 401 |

**伪代码**:

```python
class OAuthToolApiSaveTests(OAuthToolTestBase):

    @patch("outlook_web.services.graph.test_refresh_token_with_rotation")
    def test_save_update_existing_account(self, mock_test_rt):
        mock_test_rt.return_value = (True, None, None)  # 验证通过
        acc_id = self._insert_test_account(
            email="save-test@oauth-test.com",
            client_id="old-cid",
            refresh_token="old-rt",
        )
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/save", json={
                "account_id": acc_id,
                "client_id": "new-cid",
                "refresh_token": "new-rt",
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get("success"))

        # 验证 DB 中的值
        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo
            acc = accounts_repo.get_account_by_id(acc_id)
            self.assertEqual(acc["client_id"], "new-cid")
            # refresh_token 应已加密存储，这里取解密后的值
            # (load_accounts/get_account_by_id 返回的是解密后的)

    @patch("outlook_web.services.graph.test_refresh_token_with_rotation")
    def test_save_preserves_account_fields(self, mock_test_rt):
        """确保 update_account 的必填字段被正确回传"""
        mock_test_rt.return_value = (True, None, None)
        acc_id = self._insert_test_account(
            email="preserve@oauth-test.com",
            client_id="orig-cid",
            refresh_token="orig-rt",
        )
        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo
            original = accounts_repo.get_account_by_id(acc_id)
            original_email = original["email_addr"]
            original_group = original["group_id"]
            original_remark = original["remark"]

        with self.app.test_client() as client:
            self._login(client)
            client.post("/api/token-tool/save", json={
                "account_id": acc_id,
                "client_id": "updated-cid",
                "refresh_token": "updated-rt",
            })

        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo
            updated = accounts_repo.get_account_by_id(acc_id)
            self.assertEqual(updated["email_addr"], original_email)
            self.assertEqual(updated["group_id"], original_group)
            self.assertEqual(updated["remark"], original_remark)

    @patch("outlook_web.services.graph.test_refresh_token_with_rotation")
    def test_save_create_new_account(self, mock_test_rt):
        mock_test_rt.return_value = (True, None, None)
        with self.app.test_client() as client:
            self._login(client)
            resp = client.post("/api/token-tool/save", json={
                "email": "brand-new@oauth-test.com",
                "client_id": "new-cid",
                "refresh_token": "new-rt",
            })
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json().get("success"))

        # 验证新账号已创建
        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo
            acc = accounts_repo.get_account_by_email("brand-new@oauth-test.com")
            self.assertIsNotNone(acc)
            self.assertEqual(acc["client_id"], "new-cid")
```

---

### 4.12 API 集成 — Blueprint 开关（OAuthToolApiBlueprintTests）

**目标**: 验证 `OAUTH_TOOL_ENABLED` 环境变量控制 Blueprint 注册行为。

> **测试难点**: Blueprint 注册发生在 `create_app()` 阶段，修改环境变量需要在应用创建之前。由于测试中 app 是 `setUpClass` 阶段创建的单例，直接修改环境变量不会影响已注册的 Blueprint。

> **推荐测试方式**: 测试 controller 层的开关判断（如果有），或在工具关闭时验证路由返回 404。如果实现方式是"controller 层检查 config"（而非 Blueprint 不注册），则可以动态 mock config。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-BP-01 | `test_token_tool_page_accessible_when_enabled` | 默认启用 | GET `/token-tool` → 200，HTML 包含 token_tool 标识 |
| A-BP-02 | `test_token_tool_disabled_returns_404` | Mock 配置关闭 | GET `/token-tool` → 404 |
| A-BP-03 | `test_token_tool_api_disabled_returns_404` | Mock 配置关闭 | POST `/api/token-tool/prepare` → 404 |

**伪代码**:

```python
class OAuthToolApiBlueprintTests(OAuthToolTestBase):

    def test_token_tool_page_accessible_when_enabled(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/token-tool")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            # 应包含 token_tool 页面标识
            self.assertIn("token", html.lower())

    @patch("outlook_web.config.get_oauth_tool_enabled", return_value=False)
    def test_token_tool_disabled_returns_404(self, _):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/token-tool")
            self.assertEqual(resp.status_code, 404)
```

> **实现阶段注意**: 如果 Blueprint 条件注册是在 `create_app()` 中完成的，则上述 mock 方式可能不生效。此时需要在 controller 层添加动态开关检查（如 `if not config.get_oauth_tool_enabled(): abort(404)`），以支持测试。TD 需同步更新。

---

### 4.13 API 集成 — 账号列表（OAuthToolApiAccountListTests）

**目标**: 验证 `/api/token-tool/accounts` 返回的账号列表仅包含非敏感字段。

| 用例 ID | 用例名 | 场景 | 关键断言 |
|---------|--------|------|---------|
| A-LIST-01 | `test_accounts_list_returns_non_sensitive_fields` | 存在账号 | 返回列表含 `id`、`email`、`status`、`account_type` |
| A-LIST-02 | `test_accounts_list_excludes_sensitive_fields` | 存在账号 | 返回不含 `refresh_token`、`password`、`imap_password` |
| A-LIST-03 | `test_accounts_list_empty` | 无账号 | 返回空列表 |
| A-LIST-04 | `test_accounts_list_requires_login` | 未登录 | 401 |

**伪代码**:

```python
class OAuthToolApiAccountListTests(OAuthToolTestBase):

    def test_accounts_list_returns_non_sensitive_fields(self):
        self._insert_test_account(email="list-test@oauth-test.com")
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/api/token-tool/accounts")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            accounts = data.get("accounts", [])
            self.assertTrue(len(accounts) > 0)
            acc = accounts[0]
            self.assertIn("id", acc)
            self.assertIn("email", acc)
            self.assertIn("status", acc)
            self.assertIn("account_type", acc)

    def test_accounts_list_excludes_sensitive_fields(self):
        self._insert_test_account(email="sensitive-test@oauth-test.com")
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/api/token-tool/accounts")
            data = resp.get_json()
            for acc in data.get("accounts", []):
                self.assertNotIn("refresh_token", acc)
                self.assertNotIn("password", acc)
                self.assertNotIn("imap_password", acc)
```

---

## 5. Mock 策略

### 5.1 禁止真实网络

所有涉及 Microsoft OAuth 端点的调用必须 mock：

| Mock 目标 | Mock 路径 | 用途 |
|-----------|----------|------|
| Token 交换 | `outlook_web.services.oauth_tool.requests.post` | exchange 流程 |
| Token 验证 | `outlook_web.services.graph.test_refresh_token_with_rotation` | save 流程的 token 有效性校验 |

### 5.2 时间控制

| Mock 目标 | Mock 路径 | 用途 |
|-----------|----------|------|
| FLOW_STORE TTL | `outlook_web.services.oauth_tool.time` | 测试 Flow 过期清理 |

### 5.3 配置控制

| Mock 目标 | Mock 路径 | 用途 |
|-----------|----------|------|
| Blueprint 开关 | `outlook_web.config.get_oauth_tool_enabled` | 测试工具禁用时的 404 |

### 5.4 推荐 Mock 返回值构造

**Microsoft Token 端点成功响应**:

```python
{
    "access_token": "mock-at-xxx",
    "refresh_token": "mock-new-rt-xxx",
    "expires_in": 3600,
    "scope": "offline_access https://graph.microsoft.com/.default",
    "token_type": "Bearer",
}
```

**Microsoft Token 端点失败响应**:

```python
{
    "error": "invalid_grant",
    "error_description": "AADSTS70000: ...",
}
```

**Token 验证返回**:

```python
# 成功：(True, None, None) 或 (True, None, "new-rotated-rt")
# 失败：(False, "error description", None)
```

---

## 6. 测试数据与环境准备

### 6.1 DB 与 App 初始化

- 统一使用 `tests/_import_app.py::import_web_app_module()` 导入 app
- 通过 `app.app_context()` 获取 DB 并清理 `settings` 表（`oauth_tool_%` 前缀）和测试账号
- CSRF 默认禁用（`WTF_CSRF_ENABLED=False`），无需额外处理

### 6.2 测试账号约定

| 属性 | 值 | 说明 |
|------|-----|------|
| 邮箱域名 | `@oauth-test.com` | 避免与其他测试冲突 |
| group_id | `1` | 默认分组 |
| account_type | `outlook` | 默认类型 |
| remark | `oauth-test` | 可识别来源 |

### 6.3 清理策略

| 时机 | 操作 |
|------|------|
| `setUp()` | `DELETE FROM settings WHERE key LIKE 'oauth_tool_%'` |
| `setUp()` | `DELETE FROM accounts WHERE email_addr LIKE '%@oauth-test%'` |
| `setUp()` | `clear_login_attempts()` |

---

## 7. 测试难点与应对方案

### 7.1 FLOW_STORE 是模块级内存变量

**难点**: FLOW_STORE 是 `services/oauth_tool.py` 中的模块级变量，测试间可能互相污染。

**应对**:
- 每个测试用例使用唯一 `state` key（`uuid.uuid4().hex` 前缀）
- 如果实现提供 `clear_all_flows()` 函数，可在 `setUp()` 中调用清理
- 线程安全测试使用独立的 key 范围，不与其他用例冲突

### 7.2 Blueprint 条件注册时机

**难点**: `create_app()` 中的 Blueprint 注册是一次性的，后续修改环境变量不会动态生效。

**应对**:
- **推荐方案**: controller 层添加动态开关检查（`if not config.get_oauth_tool_enabled(): abort(404)`）
- 这样测试可通过 `@patch("outlook_web.config.get_oauth_tool_enabled")` 动态控制
- 如果实现确实采用"不注册 Blueprint"方式，则需要单独的 app fixture（重新调用 `create_app()`）来测试

### 7.3 `update_account()` 必填参数

**难点**: `update_account(account_id, email_addr, password, client_id, refresh_token, group_id, remark, status)` 的 `email_addr`(str)、`group_id`(int)、`remark`(str) 为必填参数，传 None 会导致 `return False`。

**应对**:
- TD 已修复（v1.1）: save 逻辑先调用 `get_account_by_id()` 获取现有值，再回传
- 测试 A-SAVE-05 专门验证此行为：更新后原字段值不被覆盖

### 7.4 `requests.post` Mock 路径

**难点**: Mock 路径取决于 `oauth_tool.py` 中 `requests` 的导入方式。

**应对**:
- 若 `import requests` → mock `outlook_web.services.oauth_tool.requests.post`
- 若 `from requests import post` → mock `outlook_web.services.oauth_tool.post`
- 实现阶段确定后统一调整

---

## 8. 前端手动验收清单

以下场景不写自动化测试，通过人工验收覆盖：

| # | 场景 | 验收步骤 | 预期结果 |
|---|------|---------|---------|
| M-01 | localhost 完整流程 | 配置 Azure 应用 → 点击授权 → 回调 → 获取 Token | Token 显示在结果区 |
| M-02 | Docker 部署手动粘贴 | 回调页提示复制 URL → 粘贴到输入框 → 换取 Token | Token 换取成功 |
| M-03 | 配置保存/加载 | 填写配置 → 保存 → 刷新页面 | 配置自动回填 |
| M-04 | Scope 预设按钮 | 点击"Graph 邮件"/"IMAP" 按钮 | Scope 输入框填充对应值 |
| M-05 | 写入已有账号 | 选择账号 → 写入 | 账号列表 Token 更新，状态恢复 active |
| M-06 | 创建新账号 | 不选账号 → 输入邮箱 → 写入 | 新账号出现在主页账号列表 |
| M-07 | 开关关闭 | 设置 `OAUTH_TOOL_ENABLED=false` 重启 | 侧边栏无入口；直接访问 /token-tool 返回 404 |
| M-08 | 错误引导 | 使用错误 client_id 授权 | 错误提示含引导文本（如检查 Azure 注册） |

---

## 9. 用例总表

### 9.1 Service 层（单元测试）— 29 个用例

| 分组 | 用例数 | 用例 ID 范围 |
|------|--------|------------|
| PKCE 生成 | 4 | S-PKCE-01 ~ 04 |
| Scope 校验 | 7 | S-SCOPE-01 ~ 07 |
| FLOW_STORE | 6 | S-FLOW-01 ~ 06 |
| 错误引导映射 | 4 | S-ERR-01 ~ 04 |
| JWT 解码 | 3 | S-JWT-01 ~ 03 |
| Token 交换 | 5 | S-EXCH-01 ~ 05 (Service 层) |

### 9.2 API 集成测试 — 28 个用例

| 分组 | 用例数 | 用例 ID 范围 |
|------|--------|------------|
| prepare 端点 | 5 | A-PREP-01 ~ 05 |
| exchange 端点 | 5 | A-EXCH-01 ~ 05 |
| config 端点 | 5 | A-CFG-01 ~ 05 |
| save 端点 | 6 | A-SAVE-01 ~ 06 |
| Blueprint 开关 | 3 | A-BP-01 ~ 03 |
| 账号列表 | 4 | A-LIST-01 ~ 04 |

### 9.3 前端手动验收 — 8 个场景

| 范围 | 场景数 | 标识 |
|------|--------|------|
| 手动验收 | 8 | M-01 ~ M-08 |

**合计**: 自动化 57 个 + 手动验收 8 个 = **65 个测试点**

---

## 10. 测试执行命令

```bash
# 运行 OAuth Token 工具全部测试
python -m pytest tests/test_oauth_tool.py -v

# 仅运行 Service 层
python -m pytest tests/test_oauth_tool.py -v -k "Pkce or Scope or FlowStore or ErrorGuidance or JwtDecode or TokenExchange"

# 仅运行 API 集成
python -m pytest tests/test_oauth_tool.py -v -k "Api"

# 兼容 unittest 方式
python -m unittest tests.test_oauth_tool -v
```

---

## 11. 与 TD §8 测试策略的差异说明

| 项目 | TD §8 原始设计 | TDD 调整 | 调整原因 |
|------|--------------|---------|---------|
| 文件数量 | 2 个文件（`test_oauth_tool_service.py` + `test_oauth_tool_api.py`） | **1 个文件**（`test_oauth_tool.py`） | 用户选择集中管理方案，减少维护成本 |
| 单元测试用例 | 11 个 | **24 个** | 增加了 PKCE 字符集、Scope 更多边界、FLOW_STORE 更细粒度、Token 交换完整链路 |
| 集成测试用例 | 9 个 | **23 个** | 增加了认证拦截、参数缺失、账号字段保持、敏感数据过滤等边界用例 |
| 前端测试 | 7 个手动场景 | **8 个手动场景** | 增加了"错误引导"场景 |
| Blueprint 开关测试 | 1 个（`test_tool_disabled`） | **3 个** | 区分页面 / API / enabled 三个场景 |

> **注意**: TD §8 需同步更新测试文件名引用（从两个文件合并为一个），将在本文档创建后统一修改。

---

**文档结束**
