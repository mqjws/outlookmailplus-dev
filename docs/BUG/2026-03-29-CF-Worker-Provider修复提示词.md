# Cloudflare Worker Temp Mail Provider 适配修复任务

## 任务背景

当前项目已完成临时邮箱二期平台化，具备 provider factory + ABC contract 架构。现在需要将底层 provider 从 GPTMail (chatgpt.org.uk) 切换到 Cloudflare Workers (dreamhunter2333/cloudflare_temp_email)。

完整的 BUG 分析文档位于：`docs/BUG/2026-03-29-CF-Worker-Provider适配缺陷分析BUG.md`

## 目标

1. 创建新的 `CloudflareTempMailProvider` 类对接 CF Worker API
2. 修复仓库层、通知层、factory 层的适配问题
3. 确保上层 API（用户侧、任务侧、external）保持不变
4. 通过所有现有测试

---

## 修复任务清单（按优先级）

### 第一步：仓库层加固（不依赖 CF provider）

#### 1.1 修复 BUG-CF-01：from_address 字段映射不完整

**文件**：`outlook_web/repositories/temp_emails.py` 第 371 行

**问题**：`save_temp_email_messages()` 中 `from_address` 只检查 `msg.get("from_address")`，但 CF Worker 返回的字段名是 `"source"`。

**修复方案**：
```python
# 原代码（第 371 行）
from_address = str(msg.get("from_address") or "")

# 修改为
from_address = str(
    msg.get("from_address")
    or msg.get("source")      # CF Worker
    or msg.get("from")        # Graph API 风格
    or msg.get("sender")      # 其他常见格式
    or ""
)
```

#### 1.2 修复 BUG-CF-07：created_at 类型不匹配

**文件**：`outlook_web/repositories/temp_emails.py` 第 373 行

**问题**：CF Worker 的 `created_at` 是 ISO 字符串（如 `"2025-12-07T10:30:00.000Z"`），而项目期望 integer timestamp。

**修复方案**：
```python
# 原代码（第 373 行）
timestamp = msg.get("timestamp", 0)

# 修改为
ts = msg.get("timestamp") or msg.get("created_at")
if isinstance(ts, str):
    # ISO 8601 string -> integer timestamp
    from datetime import datetime
    try:
        ts_clean = ts.replace("Z", "+00:00").replace(".000", "")
        timestamp = int(datetime.fromisoformat(ts_clean).timestamp())
    except (ValueError, AttributeError):
        timestamp = 0
else:
    timestamp = int(ts or 0)
```

**注意**：文件开头需要确认已导入 `datetime`。

---

### 第二步：通知模块收口

#### 2.1 修复 BUG-CF-04：通知模块绕过 provider 抽象

**文件**：`outlook_web/services/notification_dispatch.py`

**问题**：`_fetch_temp_email_messages()` 直接调用 `gptmail.get_temp_emails_from_api(address)`，绕过了 TempMailService 和 provider factory。

**修复方案**：

1. 修改 import（文件开头）：
```python
# 原代码
from outlook_web.services import email_push, gptmail

# 修改为
from outlook_web.services import email_push
from outlook_web.services.temp_mail_service import TempMailService, TempMailError
```

2. 修改 `_fetch_temp_email_messages` 函数（第 185-211 行）：
```python
def _fetch_temp_email_messages(source: dict[str, Any], since: str) -> list[dict[str, Any]]:
    """通过 TempMailService 统一读取临时邮箱"""
    address = source["email"]
    results: list[dict[str, Any]] = []

    try:
        service = TempMailService()
        # TempMailService.list_messages 会自动调用 provider、同步远程、缓存到 DB
        messages = service.list_messages(address, sync_remote=True)

        for item in messages:
            received_at = _extract_message_timestamp(item.get("timestamp") or item.get("created_at"))
            if received_at and received_at <= since:
                continue
            plain_content = (item.get("content", "") or "").strip()
            if not plain_content and item.get("has_html"):
                plain_content = _html_to_plain(item.get("html_content", "") or "")
            preview = plain_content[:MAX_TEMP_EMAIL_PREVIEW_LENGTH]
            results.append(
                {
                    "message_id": item.get("message_id", ""),
                    "subject": item.get("subject", "") or "无主题",
                    "sender": item.get("from_address", "") or "unknown",
                    "received_at": received_at,
                    "preview": preview,
                    "content": plain_content,
                    "folder": "inbox",
                }
            )
    except (TempMailError, Exception):
        # Provider 读取失败时返回空列表，不影响其他通知源
        logger.warning(f"Failed to fetch temp email messages for {address}", exc_info=True)

    return results
```

3. 同步修复测试文件 `tests/test_notification_dispatch.py`（第 820-826 行）：
```python
# 原代码
), patch(
    "outlook_web.services.notification_dispatch.gptmail.get_temp_emails_from_api",
    return_value=None,
),

# 修改为
mock_messages = [{
    "message_id": "html-only-message",
    "from_address": "sender@example.com",
    "subject": "HTML only",
    "content": "",
    "html_content": "<div>Hello <strong>HTML</strong> world</div>",
    "has_html": True,
    "timestamp": 1772407200,
}]

), patch(
    "outlook_web.services.notification_dispatch.TempMailService.list_messages",
    return_value=mock_messages,
),
```

---

### 第三步：创建 CloudflareTempMailProvider

#### 3.1 新建文件：`outlook_web/services/temp_mail_provider_cf.py`

**要求**：

1. 继承 `TempMailProviderBase`
2. 实现 CF Worker API 对接（dreamhunter2333/cloudflare_temp_email）
3. 处理 CF 的双认证模型：x-admin-auth（管理员）+ Bearer JWT（用户）
4. 解析 CF 返回的原始 MIME 为结构化字段

**CF Worker API 规范**：

| 操作 | 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|------|
| 创建邮箱 | POST | `/admin/new_address` | `x-admin-auth` | 返回 `{address, jwt, address_id}` |
| 删除邮箱 | DELETE | `/admin/{address}` | `x-admin-auth` | - |
| 邮件列表 | GET | `/mails` | `Authorization: Bearer <jwt>` | 返回原始 MIME |
| 删除邮件 | DELETE | `/mails/{id}` | `Authorization: Bearer <jwt>` | - |
| 清空邮箱 | DELETE | `/mails` | `Authorization: Bearer <jwt>` | - |

**CF 响应格式示例**：
```json
// 创建邮箱响应
{
  "address": "test@cf-domain.com",
  "jwt": "eyJhbGciOiJIUzI1NiIs...",
  "address_id": "abc123"
}

// 邮件列表响应
{
  "mails": [
    {
      "id": 456,
      "source": "sender@example.com",
      "address": "test@cf-domain.com",
      "raw": "From: sender@example.com\r\nSubject: 验证码\r\nContent-Type: text/html\r\n\r\n<p>123456</p>",
      "message_id": "<abc123@mail.example.com>",
      "created_at": "2025-12-07T10:30:00.000Z"
    }
  ]
}
```

**关键实现要点**：

1. **MIME 解析**（BUG-CF-02）：使用 Python 标准库 `email` 模块解析 `raw` 字段
```python
import email
import email.policy

def _parse_mime_raw(raw_mime: str) -> dict[str, Any]:
    msg = email.message_from_string(raw_mime, policy=email.policy.default)
    # 提取 subject, from_address, content, html_content, has_html
    # ...
```

2. **JWT 缓存**（BUG-CF-03）：将 JWT 存入 `meta_json["provider_jwt"]`
```python
def _build_meta(self, *, jwt: str = "", address_id: str = "") -> dict[str, Any]:
    return {
        "provider_name": self.provider_name,
        "provider_mailbox_id": address_id,
        "provider_jwt": jwt,  # 关键：缓存 JWT 用于后续读信
        "provider_cursor": "",
        # ...
    }
```

3. **ID 命名空间**（BUG-CF-05）：CF 的 integer ID 加 `cf_` 前缀避免冲突
```python
message_id = f"cf_{cf_msg['id']}"
```

4. **前缀控制**（BUG-CF-06）：固定 `enablePrefix: false`
```python
payload = {
    "name": prefix or "",
    "domain": target_domain,
    "enablePrefix": False,  # 避免自动加前缀
}
```

5. **时间戳转换**（BUG-CF-07）：ISO 字符串转为 integer timestamp
```python
from datetime import datetime
timestamp = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
```

**完整的 Provider 模板**：

参考 `outlook_web/services/temp_mail_provider_custom.py` 的结构，实现以下方法：
- `get_options()` - 返回域名配置
- `create_mailbox()` - 调用 CF API 创建邮箱，返回 email + meta（含 JWT）
- `delete_mailbox()` - 调用 CF API 删除邮箱
- `list_messages()` - 使用 JWT 读取邮件，解析 MIME
- `get_message_detail()` - 获取邮件详情
- `delete_message()` - 删除单封邮件
- `clear_messages()` - 清空邮箱

**错误处理**：
- 创建自定义异常 `CloudflareTempMailProviderError`
- 映射 CF HTTP 错误到统一错误码（UNAUTHORIZED, UPSTREAM_SERVER_ERROR 等）
- 使用 `requests` 库，设置 30 秒超时

---

### 第四步：Factory 注册和 Settings 配置

#### 4.1 修复 BUG-CF-08：注册 CF provider

**文件 1**：`outlook_web/repositories/settings.py`

在常量定义区域（第 10-16 行）添加：
```python
DEFAULT_TEMP_MAIL_PROVIDER = "custom_domain_temp_mail"
LEGACY_TEMP_MAIL_PROVIDER = "legacy_bridge"
CLOUDFLARE_TEMP_MAIL_PROVIDER = "cloudflare_temp_mail"  # 新增
LEGACY_TEMP_MAIL_PROVIDER_NAMES = {"legacy_bridge", "legacy_gptmail", "gptmail"}
SUPPORTED_TEMP_MAIL_PROVIDERS = {
    DEFAULT_TEMP_MAIL_PROVIDER,
    LEGACY_TEMP_MAIL_PROVIDER,
    CLOUDFLARE_TEMP_MAIL_PROVIDER,  # 新增
}
```

**文件 2**：`outlook_web/services/temp_mail_provider_factory.py`

1. 添加 import：
```python
from outlook_web.services.temp_mail_provider_cf import CloudflareTempMailProvider
```

2. 修改 `get_temp_mail_provider()` 函数（第 19-35 行）：
```python
def get_temp_mail_provider(provider_name: str | None = None) -> TempMailProviderBase:
    resolved_provider_name = settings_repo.get_temp_mail_runtime_provider_name(provider_name)
    if not resolved_provider_name:
        raise TempMailProviderFactoryError(
            "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            "未配置临时邮箱 Provider",
        )

    # 根据 provider name 路由到对应实现
    if resolved_provider_name == "cloudflare_temp_mail":
        return CloudflareTempMailProvider(provider_name=resolved_provider_name)

    if resolved_provider_name in settings_repo.get_supported_temp_mail_provider_names():
        return CustomTempMailProvider(provider_name=resolved_provider_name)

    raise TempMailProviderFactoryError(
        "TEMP_MAIL_PROVIDER_INVALID",
        "临时邮箱 Provider 配置无效",
        status=500,
        data={"provider_name": resolved_provider_name},
    )
```

---

### 第五步：前端代码清理（可选）

#### 5.1 修复 BUG-CF-11：清理冗余 fallback

**文件**：`static/js/features/temp_emails.js` 第 475-477 行

Controller 已统一映射字段名，前端的 fallback 是死代码。

```javascript
// 原代码
const from = email.from || email.sender || translateAppTextLocal('未知发件人');
const date = email.receivedDateTime || email.date || '';
const preview = (email.bodyPreview || email.body_preview || '').substring(0, 80);

// 修改为
const from = email.from || translateAppTextLocal('未知发件人');
const date = email.date || '';
const preview = (email.body_preview || '').substring(0, 80);
```

---

## 测试验证要求

### 单元测试
运行以下测试确保无回归：
```bash
pytest tests/test_temp_mail_provider_factory.py -v
pytest tests/test_temp_mail_provider_contract.py -v
pytest tests/test_temp_mail_service.py -v
pytest tests/test_temp_mail_mailbox_model.py -v
pytest tests/test_temp_emails_api_regression.py -v
pytest tests/test_temp_mail_settings_platform_contract.py -v
pytest tests/test_notification_dispatch.py::NotificationDispatchTests::test_temp_email_html_body_is_converted_for_notification -v
```

### 全量测试
```bash
pytest tests/ -k "temp_mail or temp_email" -v
```

### 预期结果
所有测试通过，无新增失败。

---

## 关联文件清单

| 文件路径 | 修改类型 | 涉及 BUG |
|----------|----------|----------|
| `outlook_web/repositories/temp_emails.py` | 修改 | CF-01, CF-07 |
| `outlook_web/services/notification_dispatch.py` | 修改 | CF-04 |
| `outlook_web/services/temp_mail_provider_cf.py` | **新建** | CF-02, CF-03, CF-05, CF-06, CF-07 |
| `outlook_web/repositories/settings.py` | 修改 | CF-08 |
| `outlook_web/services/temp_mail_provider_factory.py` | 修改 | CF-08 |
| `static/js/features/temp_emails.js` | 修改（可选） | CF-11 |
| `tests/test_notification_dispatch.py` | 修改 | CF-04 |

---

## 重要注意事项

1. **不要修改的文件**（二期平台化已验证）：
   - `outlook_web/controllers/temp_emails.py` - 用户侧控制器
   - `outlook_web/controllers/settings.py` - settings 页面
   - `outlook_web/services/temp_mail_service.py` - service 层
   - `outlook_web/services/mailbox_resolver.py` - resolver
   - `outlook_web/services/external_api.py` - external API（temp mail 路径已正确）

2. **外部依赖**：
   - `requests` 库（用于 HTTP 请求）
   - Python 标准库 `email` 模块（用于 MIME 解析）
   - 无需安装其他第三方库

3. **配置说明**：
   - `temp_mail_api_key` 存储的是 CF Worker 的 `ADMIN_PASSWORDS` 环境变量值
   - `temp_mail_api_base_url` 是 CF Worker 的部署地址
   - `temp_mail_domains` 是 CF Worker 配置的域名列表

4. **向后兼容**：
   - 修复后的代码必须不影响现有的 GPTMail provider
   - 切换 provider 只需修改 settings 中的 `temp_mail_provider` 配置

---

## 交付标准

1. ✅ 所有代码修改完成
2. ✅ 所有单元测试通过
3. ✅ 无新增 failing tests
4. ✅ BUG 文档状态更新为"已修复"

---

## 参考文档

- BUG 详细分析：`docs/BUG/2026-03-29-CF-Worker-Provider适配缺陷分析BUG.md`
- Provider 基类：`outlook_web/services/temp_mail_provider_base.py`
- Custom Provider 实现：`outlook_web/services/temp_mail_provider_custom.py`
- CF Worker 开源项目：https://github.com/dreamhunter2333/cloudflare_temp_email
