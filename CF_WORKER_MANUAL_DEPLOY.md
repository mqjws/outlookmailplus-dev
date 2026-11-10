# Outlook Email Plus 兼容 CF Worker 临时邮箱手动部署教程

本文档用于手动部署一个新的 Cloudflare Worker 临时邮箱服务，不使用本仓库的 `cf-deploy/deploy-one-click.ps1` 脚本。

部署完成后，Outlook Email Plus 需要填写：

```text
CF Worker 部署地址 = https://email-api.你的域名
CF Worker Admin 密码 = 你在 ADMIN_PASSWORDS 里设置的密码
```

## 0. 前提

你需要准备：

1. 一个 Cloudflare 账号。
2. 一个已经添加到 Cloudflare 并由 Cloudflare 托管 DNS 的真实域名，例如 `yourmail.cc.cd`。
3. 本机已安装 Node.js。
4. 当前 PowerShell 已能运行 `npx wrangler --version`。

如果你使用 v2rayN SOCKS5 代理，可在当前 PowerShell 窗口先设置：

```powershell
$env:http_proxy  = "socks5://127.0.0.1:10808"
$env:https_proxy = "socks5://127.0.0.1:10808"
```

## 1. 创建新的 Worker 工作区

建议在任意你方便的位置创建，例如桌面或当前项目旁边：

```powershell
mkdir D:\oep-cf-temp-worker
cd D:\oep-cf-temp-worker
mkdir src
```

后续所有文件都放在：

```text
D:\oep-cf-temp-worker
```

## 2. 创建 `wrangler.toml`

在 `D:\oep-cf-temp-worker\wrangler.toml` 新建以下内容。

把下面这些值替换成你自己的：

```text
yourmail.cc.cd              -> 你的收件域名
email-api.yourmail.cc.cd    -> 你的 Worker API 自定义域名
CHANGE_THIS_ADMIN_PASSWORD  -> 你的 CF Worker Admin 密码
CHANGE_THIS_LONG_RANDOM_SECRET -> 随机长字符串
```

```toml
name = "oep-temp-mail-api"
main = "src/worker.js"
compatibility_date = "2025-04-01"

# 如果你的域名已托管到 Cloudflare，推荐用自定义域名。
# 部署后 Outlook Email Plus 里的 CF Worker 部署地址就填：
# https://email-api.yourmail.cc.cd
routes = [
  { pattern = "email-api.yourmail.cc.cd", custom_domain = true }
]

[vars]
DOMAINS = ["yourmail.cc.cd"]
DEFAULT_DOMAINS = ["yourmail.cc.cd"]
ADMIN_PASSWORDS = ["CHANGE_THIS_ADMIN_PASSWORD"]
JWT_SECRET = "CHANGE_THIS_LONG_RANDOM_SECRET"

[[d1_databases]]
binding = "DB"
database_name = "oep-temp-mail-db"
database_id = "先运行 d1 create 后替换这里"
```

生成随机 `JWT_SECRET` 可用：

```powershell
[Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

## 3. 创建 `schema.sql`

在 `D:\oep-cf-temp-worker\schema.sql` 新建：

```sql
CREATE TABLE IF NOT EXISTS addresses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  address TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  domain TEXT NOT NULL,
  created_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_addresses_address ON addresses(address);
CREATE INDEX IF NOT EXISTS idx_addresses_deleted ON addresses(deleted_at);

CREATE TABLE IF NOT EXISTS mails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  address_id INTEGER NOT NULL,
  address TEXT NOT NULL,
  source TEXT,
  message_id TEXT,
  created_at TEXT NOT NULL,
  raw TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mails_address_id ON mails(address_id);
CREATE INDEX IF NOT EXISTS idx_mails_created_at ON mails(created_at);
```

## 4. 创建 `src/worker.js`

在 `D:\oep-cf-temp-worker\src\worker.js` 新建：

```js
const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
  "access-control-allow-headers": "authorization,content-type,x-admin-auth",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function text(data, status = 200) {
  return new Response(data, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
}

function parseList(value) {
  if (Array.isArray(value)) return value.map(String).map((x) => x.trim()).filter(Boolean);
  if (!value) return [];
  const s = String(value).trim();
  if (!s) return [];
  try {
    const parsed = JSON.parse(s);
    if (Array.isArray(parsed)) return parsed.map(String).map((x) => x.trim()).filter(Boolean);
  } catch (_) {
    // fall through
  }
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

function getDomains(env) {
  return parseList(env.DOMAINS);
}

function getDefaultDomains(env) {
  const defaults = parseList(env.DEFAULT_DOMAINS);
  return defaults.length ? defaults : getDomains(env).slice(0, 1);
}

function isAdmin(request, env) {
  const password = request.headers.get("x-admin-auth") || "";
  return parseList(env.ADMIN_PASSWORDS).includes(password);
}

function b64urlEncodeBytes(bytes) {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64urlEncodeText(textValue) {
  return b64urlEncodeBytes(new TextEncoder().encode(textValue));
}

function b64urlDecodeText(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function hmacSha256(data, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return b64urlEncodeBytes(new Uint8Array(sig));
}

async function signJwt(payload, secret) {
  const header = { alg: "HS256", typ: "JWT" };
  const encodedHeader = b64urlEncodeText(JSON.stringify(header));
  const encodedPayload = b64urlEncodeText(JSON.stringify(payload));
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const signature = await hmacSha256(signingInput, secret);
  return `${signingInput}.${signature}`;
}

async function verifyJwt(token, secret) {
  const parts = String(token || "").split(".");
  if (parts.length !== 3) return null;
  const signingInput = `${parts[0]}.${parts[1]}`;
  const expected = await hmacSha256(signingInput, secret);
  if (expected !== parts[2]) return null;
  try {
    return JSON.parse(b64urlDecodeText(parts[1]));
  } catch (_) {
    return null;
  }
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (_) {
    return {};
  }
}

async function readStreamAsText(stream) {
  if (!stream) return "";
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let out = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    out += decoder.decode(value, { stream: true });
  }
  out += decoder.decode();
  return out;
}

async function getMailboxFromAuth(request, env) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7).trim() : "";
  const payload = await verifyJwt(token, env.JWT_SECRET || "dev-secret");
  if (!payload || !payload.address_id) return null;

  const row = await env.DB.prepare(
    "SELECT id, address FROM addresses WHERE id = ? AND deleted_at IS NULL"
  ).bind(payload.address_id).first();

  return row || null;
}

async function handleFetch(request, env) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "") || "/";

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: JSON_HEADERS });
  }

  if (request.method === "GET" && path === "/") {
    return json({ ok: true, service: "oep-compatible-temp-mail", version: "1.0.0" });
  }

  if (request.method === "GET" && path === "/open_api/settings") {
    const domains = getDomains(env);
    const defaultDomains = getDefaultDomains(env);
    return json({
      title: "OEP Compatible Temp Mail",
      version: "1.0.0",
      domains,
      defaultDomains,
      defaultDomain: defaultDomains[0] || domains[0] || "",
    });
  }

  if (request.method === "POST" && path === "/admin/new_address") {
    if (!isAdmin(request, env)) return json({ error: "unauthorized" }, 401);

    const body = await readJson(request);
    const domains = getDomains(env);
    const defaultDomains = getDefaultDomains(env);
    const domain = String(body.domain || defaultDomains[0] || domains[0] || "").trim().toLowerCase();
    const name = String(body.name || "").trim().toLowerCase();

    if (!name || !/^[a-z0-9][a-z0-9._-]{0,63}$/.test(name)) {
      return json({ error: "invalid name" }, 400);
    }
    if (!domain || !domains.includes(domain)) {
      return json({ error: "invalid domain" }, 400);
    }

    const address = `${name}@${domain}`;
    const now = new Date().toISOString();

    try {
      const result = await env.DB.prepare(
        "INSERT INTO addresses (address, name, domain, created_at) VALUES (?, ?, ?, ?)"
      ).bind(address, name, domain, now).run();

      const id = result.meta.last_row_id;
      const jwt = await signJwt({ address_id: id, address, iat: Math.floor(Date.now() / 1000) }, env.JWT_SECRET || "dev-secret");

      return json({
        id,
        address_id: id,
        address,
        jwt,
      });
    } catch (err) {
      return json({ error: "address exists or database error", detail: String(err && err.message ? err.message : err) }, 409);
    }
  }

  const deleteAddressMatch = path.match(/^\/admin\/delete_address\/(\d+)$/);
  if (request.method === "DELETE" && deleteAddressMatch) {
    if (!isAdmin(request, env)) return json({ error: "unauthorized" }, 401);
    const id = Number(deleteAddressMatch[1]);
    await env.DB.prepare("UPDATE addresses SET deleted_at = ? WHERE id = ?").bind(new Date().toISOString(), id).run();
    await env.DB.prepare("DELETE FROM mails WHERE address_id = ?").bind(id).run();
    return json({ ok: true, success: true });
  }

  const clearInboxMatch = path.match(/^\/admin\/clear_inbox\/(\d+)$/);
  if (request.method === "DELETE" && clearInboxMatch) {
    if (!isAdmin(request, env)) return json({ error: "unauthorized" }, 401);
    const id = Number(clearInboxMatch[1]);
    await env.DB.prepare("DELETE FROM mails WHERE address_id = ?").bind(id).run();
    return json({ ok: true, success: true });
  }

  if (request.method === "GET" && path === "/api/mails") {
    const mailbox = await getMailboxFromAuth(request, env);
    if (!mailbox) return json({ error: "unauthorized" }, 401);

    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 100), 1), 200);
    const offset = Math.max(Number(url.searchParams.get("offset") || 0), 0);
    const result = await env.DB.prepare(
      "SELECT id, source, message_id, created_at, raw FROM mails WHERE address_id = ? ORDER BY id DESC LIMIT ? OFFSET ?"
    ).bind(mailbox.id, limit, offset).all();

    return json({
      mails: (result.results || []).map((row) => ({
        id: row.id,
        source: row.source || "",
        message_id: row.message_id || "",
        created_at: row.created_at,
        raw: row.raw || "",
      })),
    });
  }

  const deleteMailMatch = path.match(/^\/api\/mails\/(\d+)$/);
  if (request.method === "DELETE" && deleteMailMatch) {
    const mailbox = await getMailboxFromAuth(request, env);
    if (!mailbox) return json({ error: "unauthorized" }, 401);
    const mailId = Number(deleteMailMatch[1]);
    await env.DB.prepare("DELETE FROM mails WHERE id = ? AND address_id = ?").bind(mailId, mailbox.id).run();
    return json({ ok: true, success: true });
  }

  return json({ error: "not found" }, 404);
}

async function handleEmail(message, env) {
  const to = String(message.to || "").trim().toLowerCase();
  const from = String(message.from || "").trim();
  const row = await env.DB.prepare(
    "SELECT id, address FROM addresses WHERE address = ? AND deleted_at IS NULL"
  ).bind(to).first();

  if (!row) {
    message.setReject("Unknown temporary mailbox");
    return;
  }

  const raw = await readStreamAsText(message.raw);
  const messageId = message.headers ? String(message.headers.get("Message-ID") || "") : "";
  await env.DB.prepare(
    "INSERT INTO mails (address_id, address, source, message_id, created_at, raw) VALUES (?, ?, ?, ?, ?, ?)"
  ).bind(row.id, row.address, from, messageId, new Date().toISOString(), raw).run();
}

export default {
  fetch: handleFetch,
  email: handleEmail,
};
```

## 5. 登录 Cloudflare

```powershell
npx wrangler login
```

浏览器会打开 Cloudflare 授权页，登录并授权。

## 6. 创建 D1 数据库

在 `D:\oep-cf-temp-worker` 目录运行：

```powershell
npx wrangler d1 create oep-temp-mail-db
```

输出里会有：

```toml
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

复制这个 `database_id`，替换 `wrangler.toml` 里的：

```toml
database_id = "先运行 d1 create 后替换这里"
```

## 7. 初始化 D1 表结构

```powershell
npx wrangler d1 execute oep-temp-mail-db --remote --file=.\schema.sql
```

如果提示确认，输入 `y`。

## 8. 部署 Worker

```powershell
npx wrangler deploy
```

成功后会得到一个 Worker 地址。若 `routes` 自定义域名生效，你的 API 地址就是：

```text
https://email-api.yourmail.cc.cd
```

如果自定义域名没有自动绑定，也可以先使用 Wrangler 输出的 `workers.dev` 地址作为 API 地址，例如：

```text
https://oep-temp-mail-api.xxxxx.workers.dev
```

注意：API 地址可以临时用 `workers.dev`，但收件域名仍必须是你在 `DOMAINS` 里配置的真实域名。

## 9. 配置 Cloudflare Email Routing

进入 Cloudflare Dashboard：

```text
你的域名
→ Email / Email Routing
→ 启用 Email Routing
```

然后添加路由规则：

```text
Routing Rules
→ Create rule
→ Custom address 或 Catch-all
→ Action 选择 Send to a Worker
→ Worker 选择 oep-temp-mail-api
→ 保存
```

建议直接配置 Catch-all：

```text
*@yourmail.cc.cd -> Send to Worker -> oep-temp-mail-api
```

这样 Outlook Email Plus 动态创建的任意临时邮箱都能收信。

## 10. 验证 Worker 接口

把 `$base` 和密码改成你自己的：

```powershell
$base = "https://email-api.yourmail.cc.cd"
$admin = "CHANGE_THIS_ADMIN_PASSWORD"
```

验证域名同步接口：

```powershell
Invoke-RestMethod "$base/open_api/settings"
```

正常应返回：

```json
{
  "title": "OEP Compatible Temp Mail",
  "version": "1.0.0",
  "domains": ["yourmail.cc.cd"],
  "defaultDomains": ["yourmail.cc.cd"],
  "defaultDomain": "yourmail.cc.cd"
}
```

验证创建邮箱：

```powershell
$body = '{"name":"test001","domain":"yourmail.cc.cd","enablePrefix":false}'
Invoke-RestMethod -Method Post `
  -Uri "$base/admin/new_address" `
  -Headers @{"x-admin-auth"=$admin;"content-type"="application/json"} `
  -Body $body
```

正常应返回：

```json
{
  "id": 1,
  "address_id": 1,
  "address": "test001@yourmail.cc.cd",
  "jwt": "..."
}
```

## 11. 填回 Outlook Email Plus

打开 Outlook Email Plus 页面：

```text
设置
→ 临时邮箱
→ Provider 选择 Cloudflare Temp Mail
```

填写：

```text
CF Worker 部署地址 = https://email-api.yourmail.cc.cd
CF Worker Admin 密码 = CHANGE_THIS_ADMIN_PASSWORD
```

然后点击：

```text
保存
从 CF Worker 同步域名
```

同步成功后，临时邮箱页面就可以创建：

```text
随机前缀@yourmail.cc.cd
```

## 12. 本项目需要的接口清单

这份 Worker 代码已适配 Outlook Email Plus 当前内置 `cloudflare_temp_mail` Provider 调用的接口：

```text
GET    /open_api/settings
POST   /admin/new_address
GET    /api/mails
DELETE /api/mails/{id}
DELETE /admin/delete_address/{address_id}
DELETE /admin/clear_inbox/{address_id}
```

认证规则：

```text
管理接口：x-admin-auth: <ADMIN_PASSWORDS 中的密码>
读信接口：Authorization: Bearer <创建邮箱时返回的 jwt>
```

## 13. 最终你要保存的两个值

如果你按本文示例部署：

```text
CF Worker 部署地址 = https://email-api.yourmail.cc.cd
CF Worker Admin 密码 = CHANGE_THIS_ADMIN_PASSWORD
```

其中：

```text
CF Worker 部署地址：来自 Worker 自定义域名或 wrangler deploy 输出的 workers.dev 地址
CF Worker Admin 密码：来自 wrangler.toml 里的 ADMIN_PASSWORDS
```

## 参考

- Cloudflare Email Routing / Email Workers 文档：https://developers.cloudflare.com/email-service/get-started/route-emails/
- Cloudflare D1 文档：https://developers.cloudflare.com/d1/get-started/
- Cloudflare Wrangler deploy 文档：https://developers.cloudflare.com/workers/wrangler/commands/workers/
