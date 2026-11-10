# 公网部署安全配置（阶段一）

本阶段只加固源码，不修改现有 `.env`、邮箱数据库或服务器配置。

## 已完成的加固

- Docker 按明确目录复制应用，构建上下文排除 `.env`、账号导入文本、备份和本地运行记录。
- 邮件全屏 iframe 保持与普通视图一致的沙盒；信任模式也不授予脚本执行权限。
- DOMPurify 3.4.17 本地托管，保留上游许可证。文件 SHA-256：`2ffc14b99b081b271d8df0740b688e0163bc5f0fdfc3e1888acc88f005ab0700`。
- 净化库不可用时转义 HTML 为纯文本，不使用正则表达式模拟安全净化。
- 邮件脚本使用新的缓存版本参数，避免旧的长期缓存继续加载修复前代码。
- 非开发环境缺少 Flask-WTF 时拒绝启动；HTTPS 的严格 CSRF 配置不再被覆盖。
- 批量接口测试通过 mock 上游执行真实控制流程，不在生产代码中保留测试捷径。

## 本地 HTTP 与公网 HTTPS

默认仍兼容本地 HTTP：`SESSION_COOKIE_SECURE=false`，`TRUSTED_HOSTS` 为空时不限制 Host。
这些兼容默认值不代表公网配置已完成。部署阶段应明确设置：

```dotenv
SESSION_COOKIE_SECURE=true
TRUSTED_HOSTS=outlook.ivano.cyou,localhost,127.0.0.1
PROXY_FIX_ENABLED=true
TRUSTED_PROXIES=127.0.0.1
WTF_CSRF_SSL_STRICT=true
```

`TRUSTED_PROXIES` 示例仅适用于应用实际看到代理连接方为 `127.0.0.1` 的情况。
Docker 端口转发可能使连接方变为网桥地址；部署时必须核实，再填写准确 IP 或最小 CIDR。
不要直接信任全部地址或未经核实的大范围内网网段。

应用仅信任指定连接方的单跳 `X-Forwarded-For` 和 `X-Forwarded-Proto`，不信任转发 Host 或路径前缀。
OpenResty 应先验证 Cloudflare 的来源地址，解析真实客户端 IP，再覆盖传给应用的转发头，
不要原样转发客户端提供的头。站点 Host 应保持目标域名；源站使用正确证书及 HTTPS。

`SESSION_COOKIE_SECURE=true` 本身不会建立 TLS，也不会自动重定向 HTTP。
必须先配置 HTTPS 入口，再启用这个配置。不要直接改动本机 HTTP 使用中的 `.env`。
Host 白名单保留 `localhost` 和 `127.0.0.1`，用于现有容器健康检查。

## 请求限制

| 配置 | 默认值 | 行为 |
| --- | --- | --- |
| `MAX_CONTENT_LENGTH` | 10485760 字节 | 超出读取上限返回 413 |
| `MAX_BATCH_ACCOUNTS` | 20 | 超出单批读信账号数返回 400 |
| `MAX_BATCH_FOLDERS` | 5 | 限制单批文件夹数，并去重 |
| `MAX_MAIL_PAGE_SIZE` | 100 | 单账号及批量读信的 `top` 上限；`skip` 不得为负数 |
| `MAX_QUICK_CHECK_ACCOUNTS` | 200 | 限制单次快速检测账号数 |

这些上限必须为正整数。安全布尔配置必须是 `true` 或 `false`，无效值会阻止启动。
`WTF_CSRF_SSL_STRICT` 留空时跟随 `SESSION_COOKIE_SECURE`。
限额不会把同步接口变为后台任务，也不保证整批请求一定在代理超时前完成。
大量账号应分批处理；异步批量任务和统一上游退避留待后续阶段。

## 数据和镜像

现有邮箱数据及原 `SECRET_KEY` 必须单独备份、迁移并保留，不能因为安全加固随意更换密钥。
不要上传整个本地目录或账号导入文本作为构建包。
部署必须构建当前源码，默认 Compose 的上游镜像不会自动包含这些本地修复。
阶段二再配置目标服务器上的持久化、证书、非 root 运行、备份和回退；阶段一没有执行这些操作。

阶段二已新增独立生产编排及手动部署材料，参见 [ARM64 公网部署教程](DEPLOYMENT_ARM64.md)。准备部署材料不等于服务器已经上传、构建或上线；原本的本地启动方式不变。

## 验证

```powershell
python -B -m unittest tests.test_deployment_security tests.test_batch_request_security tests.test_batch_notification_toggle.BatchEmailFetchApiTests
```

新增 JavaScript 安全用例位于 `tests/layout-system/unit/email-html-security.test.js`，
使用现有 Jest 配置并关闭覆盖率输出即可单独运行。
真实浏览器验证应确认信任模式进入全屏后脚本仍不执行，以及净化库不可用时没有活动脚本或图片节点。
