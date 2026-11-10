# 2026-11-04 公网部署验收记录

域名：`https://outlook.ivano.cyou`。
服务器目录：`/home/ubuntu/apps/outlook-email-plus`。
SSH/FinalShell 用户与容器用户：ubuntu，UID/GID `1001:1001`。

## 已完成

- 在 ARM64 服务器构建生产镜像 `outlook-email-plus:2.7.0-public-20261104`，使用 Gunicorn 单进程、8 线程。
- 镜像 ID：`sha256:9c47c8166f341ca0149d62eefa935a88053003dd2c3163b30ecd956f3e50050f`。
- 保留同镜像标签 `outlook-email-plus:deployed-20261104`，以及补齐图标前的 `outlook-email-plus:rollback-before-icon-20261104`。
- 仅向本机绑定 `127.0.0.1:5001`，公网入口复用原有 1Panel OpenResty 站点和 HTTPS。
- 仅修改本站反代与站点配置，增加本站 Cloudflare 来源信任、覆盖转发头、关闭私密响应缓存和明确超时；未更改全局 Cloudflare 设置。
- 修复源码被复制为 root 专属文件造成的启动失败；禁用与只读根目录不兼容的 Gunicorn 控制套接字。
- 补齐页面所需 `img/ico.png`，不上传其余项目截图；镜像不包含数据库、环境密钥和根目录测试插件。
- 正式数据与运行目录持久化，项目目录全部属于 ubuntu；验证 ubuntu 能读取并删除应用创建的测试文件，测试文件已移除。

## 验收结果

- 公网及直接访问源站：健康接口、登录页面均返回 200，TLS 验证成功；HTTP 跳转 HTTPS，未登录首页跳转登录页面。
- 登录页面、API 及静态资源检查到 no-store，Cloudflare 未命中缓存；HSTS 保留。
- 非法 Host 返回 400，未登录的账号 API 返回 401；会话 Cookie 具有 Secure、HttpOnly、SameSite=Lax。
- 带正确 CSRF Token 的受保护 POST：缺少或使用错误 Referer 返回 400，正确本站 Referer 的未登录请求仍返回 401；未创建账号或绕过登录。
- SQLite quick_check 通过，原有 103 个账号 ID、数据库登录密码哈希和原 SECRET_KEY 均与迁移备份一致。
- 101 条 refresh_token、101 条账号密码、2 条 IMAP 密码和 2 条加密设置可用原密钥解密；未输出明文或执行真实微软邮箱请求。
- 本次复测 50 项相关测试：49 通过，1 项 Windows 符号链接测试跳过；Black、isort 与备份脚本语法检查通过。
- 其他原有 Docker 应用保持运行；OpenResty 仅平滑 reload，没有重启整个容器。

## 备份

- 服务器文件：`backups/outlook-20261103T163225Z.tar.gz`。
- SHA256：`8ac459cb0d8f0cf4ec641f8bf7276ee4710ba6b5e31bb4c66ed845230bcf3edd`。
- UTC 时间 2026-11-03 16:32:25，对应台湾时间 2026-11-04 00:32:25。
- 包含 data、运行目录、生产环境和 Compose；ubuntu 拥有，权限 600。
- 已将备份数据库放入隔离临时目录验证 quick_check、103 账号与生产配置一致；未执行线上覆盖恢复。
- 备份完成后容器恢复 healthy，公网登录页及健康接口返回 200。
- 初始迁移备份及原站点配置备份仍保留在服务器 backups 目录。

## 保留的待办

- 用户需使用本地已修改的密码登录公网，并手动测试一个邮箱收信；本次没有获取用户密码，也没有执行真实邮件读写。
- `SCHEDULER_AUTOSTART=false`，避免与本地后台重复执行；确认收信正常并停止本地同批账号后台任务后，再按操作说明启用。
- 现有证书于 2027-01-25 到期，手动 DNS 签发、自动续签关闭；按用户确认保持不变，到期前另行处理续签。
- 本次没有安装自动备份定时任务；可使用 `sh deploy/backup.sh` 手动备份。
