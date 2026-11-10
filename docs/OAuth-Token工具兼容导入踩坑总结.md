# OAuth Token 工具兼容导入模式：实战踩坑总结

## 1. 最终跑通时的微软侧配置

### 1.1 Supported account types

必须使用：

- **Accounts in any identity provider or organizational directory and personal Microsoft accounts**
- 对应 `signInAudience = "AzureADandPersonalMicrosoftAccount"`

不要使用：

- `AzureADMyOrg` / 仅组织目录
- `PersonalMicrosoftAccount` / 仅个人账号

原因：

- 仅组织目录会在授权前报 `unauthorized_client`
- 仅个人账号会在保存前或运行时 `/common` 验证链路报 `AADSTS9002331`

### 1.2 Public Client / Token 版本

- `allowPublicClient = true`
- `accessTokenAcceptedVersion = 2`

如果 Azure 门户在修改受众时提示：

- `Property api.requestedAccessTokenVersion is invalid`

则先到 Manifest 把：

```json
"api": {
  "requestedAccessTokenVersion": 2
}
```

或当前旧格式等价字段调到 `2`，再保存。

### 1.3 Platform configuration

兼容导入模式应走：

- **Mobile and desktop applications**

本次实测可用的 Redirect URI：

- `http://localhost:5000/token-tool/callback`

补充建议：

- 如有需要，可同时登记 `http://127.0.0.1:5000/token-tool/callback`
- 若本地 callback 仍有问题，可退回：
  - `http://localhost`
  - 或 `https://login.microsoftonline.com/common/oauth2/nativeclient`
  - 然后在工具里走**手动粘贴回调 URL**

### 1.4 Client Secret

- 兼容导入模式下**不要填写 `client_secret`**
- 保留 Azure 中已有 secret 不影响，但这条导入链路不使用它

### 1.5 API permissions

要让邮件真正拉取成功，至少要补：

- **Office 365 Exchange Online → Delegated permissions → IMAP.AccessAsUser.All**

如果还希望 Graph 链路也可用，再补：

- **Microsoft Graph → Delegated permissions → Mail.Read**

---

## 2. 我们项目当前兼容导入模式的真实约束

### 2.1 工具侧约束

- Tenant 固定 `consumers`
- Public Client 模式
- `client_secret` 禁用
- 默认 Scope 应使用 IMAP 预设：

```text
offline_access https://outlook.office.com/IMAP.AccessAsUser.All
```

### 2.2 运行时模型

当前项目运行时仍是旧模型：

- Graph token 刷新：
  - 端点：`https://login.microsoftonline.com/common/oauth2/v2.0/token`
  - scope：`https://graph.microsoft.com/.default`
- IMAP token 刷新：
  - 端点：`https://login.microsoftonline.com/consumers/oauth2/v2.0/token`
  - scope：`https://outlook.office.com/IMAP.AccessAsUser.All offline_access`

这也是为什么：

- 受众不能收窄到 `PersonalMicrosoftAccount`
- Scope 不能继续残留旧的 Graph 默认值

---

## 3. 本次实际踩到的坑与对应结论

### 3.1 `unauthorized_client` / `not enabled for consumers`

现象：

- Azure 报应用未对 consumers 启用

结论：

- Supported account types 没包含 personal Microsoft accounts

正确做法：

- 改成 `AzureADandPersonalMicrosoftAccount`

### 3.2 `Property api.requestedAccessTokenVersion is invalid`

现象：

- Azure 门户修改受众时报 manifest 校验失败

结论：

- Token 版本前置字段没满足 personal accounts 要求

正确做法：

- 先把 `requestedAccessTokenVersion` / 等价 token 版本字段设为 `2`

### 3.3 `AADSTS70002: must include client_secret`

现象：

- 即使已经想走 Public Client，Azure 仍要求 secret

结论：

- 当前 redirect/platform 仍被当成机密 Web 客户端

正确做法：

- 切到 **Mobile and desktop applications**
- 不再继续沿 Web 平台思路硬顶

### 3.4 `ms-sso.copilot.microsoft.com/processcookie` + `ERR_CONNECTION_CLOSED`

现象：

- 登录后跳到 `ms-sso.copilot.microsoft.com/processcookie?...`
- 浏览器报 `ERR_CONNECTION_CLOSED`

结论：

- 这更像是浏览器 / Copilot / Microsoft SSO Cookie 辅助链路干扰
- 不属于我们应用自己的 Redirect URI

正确做法：

- 用隐身窗口 / Guest Profile / 另一浏览器重试
- 清理 `live.com` / `microsoftonline.com` / `copilot.microsoft.com` 相关 cookie
- 暂时关闭代理 / VPN / 扩展 / HTTPS 检查

### 3.5 保存前报 `AADSTS9002331`

现象：

- 授权成功、写入前验证失败
- 错误提示应用仅供 Microsoft Account users 使用，并要求 `/consumers`

结论：

- `PersonalMicrosoftAccount` 太窄
- 与当前 `/common` 验证 / 运行模型冲突

正确做法：

- 改回 `AzureADandPersonalMicrosoftAccount`

### 3.6 写入成功后读取失败

日志中曾同时出现：

- Graph：`AADSTS9002331`
- Graph：`ErrorAccessDenied`
- IMAP：`AADSTS70000`

结论：

这是三层问题叠加：

1. 受众配置不对
2. API permissions 没放开
3. 当前工具里保存的 Scope 还是旧的 Graph 默认值

正确做法：

1. 受众改成 `AzureADandPersonalMicrosoftAccount`
2. 放开 `IMAP.AccessAsUser.All`
3. Scope 切回 IMAP 预设
4. 重新授权、重新写入账号

---

## 4. 本次已在项目中做过的收口

### 4.1 代码与交互

- Token 工具前端已收口为兼容导入模式
- `client_secret` 禁用
- Tenant 固定 `consumers`
- 页面 Azure 指引已补齐：
  - audience
  - public client
  - manifest token version
  - redirect platform
  - IMAP / Graph 权限提示

### 4.2 错误引导

已补充 / 修正：

- `unauthorized_client`
- `invalid_client`
- `AADSTS9002331` 对应的保存前引导

### 4.3 旧 Scope 兼容

为了减少旧配置残留带来的重复踩坑：

- `get_config()` 会把历史遗留的：

```text
offline_access https://graph.microsoft.com/.default
```

自动映射回 IMAP 默认值。

---

## 5. 当前已验证结果

本次会话中已验证：

- OAuth Tool 专项回归通过
- 全量回归通过
- 本地服务多次重启并验证 `/login` 返回 `200`
- 最终在放开正确权限后，日志确认：
  - `/api/token-tool/exchange` → `200`
  - `/api/token-tool/save` → `200`
  - `/api/emails/...` → `200`

---

## 6. 仍可后续单独处理的问题

日志里还看到一个**独立旁路问题**：

- `/api/emails/.../extract-verification`
- `AttributeError: 'str' object has no attribute 'get'`

这不影响本次“Token 导入后成功读取邮件”的主链路，但后续如果要继续完善教程或产品体验，可以单独修。

---

## 7. 后续写教程时建议强调的顺序

建议教程按下面顺序写：

1. 先讲“这不是任意 Azure 应用导入工具，而是兼容导入模式”
2. 再讲 Azure App Registration 正确配置：
   - audience
   - public client
   - mobile/desktop platform
   - redirect URI
   - API permissions
3. 再讲工具页面中要怎么填：
   - client_id
   - redirect_uri
   - IMAP preset
4. 再讲常见错误 → 根因映射：
   - `unauthorized_client`
   - `requestedAccessTokenVersion is invalid`
   - `must include client_secret`
   - `AADSTS9002331`
   - `AADSTS70000`
5. 最后讲“授权成功 → 写入成功 → 邮件读取成功”的验证链路

---

## 8. 这套配置能否借助微软 CLI / API 让 AI 自动完成

结论先说：

- **可以自动化一大半**
- **但不能 100% 全自动**

### 8.1 可以自动化的部分

如果本机已登录 Azure CLI / Microsoft Graph PowerShell，且账号具备应用注册管理权限，AI 可以脚本化完成这些动作：

1. **创建 / 更新 App Registration**
   - `signInAudience`
   - public client 开关
   - public redirect URIs

2. **配置平台与 Redirect URI**
   - Mobile and desktop applications 的 public redirect
   - Web / public redirect 的切换

3. **配置 API permissions**
   - 增加 Exchange Online 的 `IMAP.AccessAsUser.All`
   - 增加 Microsoft Graph 的 `Mail.Read`

4. **对组织租户执行 admin consent（如果适用）**
   - 这对工作/学校租户可自动化
   - 但**不适用于 personal Microsoft account 的最终用户交互授权**

### 8.2 不能完全自动化的部分

对于 **个人 Microsoft 账号 + Delegated 权限** 这条链路，AI 不能绕过：

1. **首次交互式登录**
   - 用户必须亲自登录 Microsoft 账号

2. **首次 consent 授权**
   - 特别是 `IMAP.AccessAsUser.All` 这类 delegated 权限
   - personal account 不存在“管理员替所有人同意”的自动化捷径

3. **最终 refresh_token 颁发**
   - 仍然依赖用户浏览器中的真实登录 + 授权动作

### 8.3 更现实的 AI 自动化方案

更可落地的做法不是“AI 全自动拿 token”，而是：

1. **AI 自动配置 Azure 应用**
   - audience
   - public client
   - redirect URI
   - API permissions

2. **AI 自动检查配置差异**
   - 输出当前 manifest / redirect / permission 是否满足兼容模式
   - 自动提示缺什么权限或哪个字段不对

3. **用户只做一次交互授权**
   - 在浏览器里登录并点击 consent

4. **AI 接管后续本地保存 / 校验 / 写入**
   - 校验 token
   - 写入账号
   - 做诊断提示

### 8.4 适合教程里讨论的自动化边界

如果后面要写教程，建议明确写清：

- **Azure 配置阶段：适合 AI + CLI / API 自动化**
- **用户登录授权阶段：必须保留人工交互**
- **本地导入与诊断阶段：适合 AI 辅助**

这样用户预期会更准确，不会误以为“只要接上微软 CLI，AI 就能替用户自动拿到 personal account 的 refresh_token”

---

## 9. 可直接复用的自动化提示词文件

如果后续要把“微软云配置阶段”直接交给其他 AI 执行，可直接使用：

- `docs/微软云配置自动化提示词.md`

该文件已经把：

- 自动化目标
- 边界
- 建议工具
- 字段级目标状态
- 权限与失败处理规则

都整理成了一份可以直接转发的提示词。
