# 阶段二：第一次部署到 ARM64 公网服务器

当前服务器采用 Ubuntu 文件管理方案，部署到 `/home/ubuntu/apps/outlook-email-plus`，容器 UID/GID 为 `1001:1001`。日常管理以 [服务器运行说明](SERVER_OPERATIONS.md) 为准。

适用项目：当前本地加固后的 Outlook 邮箱管理界面；域名 `outlook.ivano.cyou`。
本文准备生产部署材料和手动操作步骤，不代表已经上传或在服务器启动了应用。

## 1. 先回答：到底上传什么？

**推荐：上传源码包与独立的私密迁移包，在服务器使用 Docker Compose 构建并运行。**

- 不是上传 `dist`。本项目由 Flask/Python 后端、模板和静态资源组成，不是仅部署静态前端的项目。
- Dockerfile 定义如何把源码制作成镜像；Compose 定义镜像如何运行、映射端口和持久化数据。
- 服务器是 ARM64，直接在服务器构建就使用 ARM64 基础镜像，不需要先在 Windows 安装 Docker 或交叉构建。
- 本次使用新增的 `compose.production.yaml`，不是原来的 `docker-compose.yml`。原配置会拉取上游镜像并运行 Watchtower，不适合部署本地加固版本。
- 默认生产镜像名是 `outlook-email-plus:2.7.0-public-20261104`。初次构建后保留镜像；更新时换新标签，不覆盖旧标签。

2026-11-03 通过 SSH 只读确认：目标服务器为 `aarch64`，Compose 为 `v5.6.0`，5001 没有监听者，`/home/ubuntu/apps/outlook-email-plus` 尚不存在。正式执行前仍需检查端口和目录是否被占用。
服务器已有 1Panel/OpenResty 提供 80/443；只新增这个域名的反向代理，不安装另一套 Nginx，不修改其他站点。

请求链路：

```text
浏览器 HTTPS → Cloudflare → 1Panel OpenResty HTTPS
                                 ↓
                         127.0.0.1:5001
                                 ↓
                         Docker 容器 :5000
                                 ↓
                          Microsoft Graph/IMAP
```

Cloudflare 不替代服务器访问微软时的出口 IP。上线后先测试单个邮箱，再逐步增加批量；仅能连通微软端口，不代表所有账号都通过微软风控。

## 2. 本次提供的部署材料

| 文件 | 用途 |
| --- | --- |
| `compose.production.yaml` | ARM64、本机回环端口、持久目录、非 root、只读根文件系统、资源和日志限制 |
| `deploy/Dockerfile` | 从当前加固源码构建，不把密钥、数据库或账号文本装进镜像 |
| `deploy/requirements.production.txt` | 固定应用与运行链路传递依赖版本；除 Gunicorn 外与本次本地回归环境版本一致 |
| `deploy/prepare_release.py` | 生成源码包与私密包；使用 SQLite backup API，不直接复制活跃数据库 |
| `deploy/openresty-location.conf` | 新域名的反向代理 location 配置 |
| `deploy/refresh_cloudflare_ips.py` | 从 Cloudflare 官方地址列表生成经过格式校验的 real-IP 配置 |
| `deploy/backup.sh` | 短暂停止本应用，备份数据库、密钥和编排，然后重新启动 |

生产镜像固定 1 worker、8 threads，避免进程内调度器重复运行；Gunicorn 不预加载应用，也不记录请求查询字符串。
部署材料没有启动 Watchtower，没有挂载 Docker socket。界面中的一键自更新在这个部署方案中不使用。
运行依赖版本已固定，但基础镜像仍为浮动标签，依赖文件也未使用完整 hash 锁定；不能承诺不同时间重新构建得到完全相同的镜像。完成验证后保留或导出已构建镜像，升级先备份。

## 3. 在你的 Windows 电脑打包

以下命令在 **Windows PowerShell** 运行，不是在服务器运行。

**早期检查发现原登录密码不足 8 位；用户已在本地系统设置更改密码，2026-11-04 的已知弱密码检查通过。其他部署者仍应在迁移前设置强密码并验证能登录。**
不需要修改原 `SECRET_KEY`。单改 `.env` 的 `LOGIN_PASSWORD` 不会更新已存在数据库的密码；打包工具会拒绝迁移已确认的弱密码，不会替你修改数据库。

建议先停止本地应用或至少停止改动账号、设置和插件。数据库备份本身是一致快照，但打包后继续在本机修改的内容不会自动同步到服务器；迁移切换时不要让两边后台任务同时跑。

```powershell
Set-Location D:\outlookEmailPlus-main\outlookEmailPlus-main
python -B deploy\prepare_release.py --output D:\outlook-deploy-upload-20261103
```

如果提示目录已存在，不要覆盖或删除原包；换一个新的输出目录，例如 `D:\outlook-deploy-upload-20261103-2`，后续上传命令也改为同一个目录。
如果提示缺少 `dotenv`，先执行 `python -m pip install python-dotenv==1.2.2`。

生成两个文件：

- `outlook-source.tar.gz`：只包含所需源码、资源、生产编排和教程。
- `outlook-private.tar.gz`：数据库一致快照、实际已安装的 `data/plugins`、从原 `.env` 转换出的 `.env.production`。

输出目录在 Windows 上移除继承权限，只授予当前用户访问；私密临时文件也放在这个目录下。不修改原 `.env`、数据库或账号导入文本。
私密包**没有加密**，仅靠文件访问权限保护；不要上传到网盘公开链接、Git、公开镜像仓库或聊天记录。
`hotmail.com_7.txt`、旧数据库备份、本地会话、根目录的测试插件不会被打包。

**原 `SECRET_KEY` 会完整保留，不要重新生成。** 旧数据库已用原密钥加密；更换密钥会导致原凭据无法解密。
原数据库的登录密码设置也会保留；不能假设修改 `.env.production` 的 `LOGIN_PASSWORD` 就能覆盖已存在的数据库密码。
如果原 `.env` 的引导密码仍不足 8 位或为默认值，工具仅为输出的 `.env.production` 生成一个新的随机引导密码，用于将来新建数据库；它不更改现有数据库的实际登录密码，也不修改原 `.env`。弱密码检查仅识别默认值与已知本地弱密码，不能从 bcrypt 哈希推断任意密码的强度，仍需你确认实际登录密码安全。
`.env.production` 使用 Compose 的 `raw` 格式：值不再额外加引号，`$` 与引号会作为值的一部分原样传入。请勿自行给原密钥加一对引号。
初次包默认关闭代理修正与后台调度，后面验证代理并验收账号后再分别开启。

## 4. 建立独立目录，并上传两个包

先在 **Windows PowerShell** 运行：

```powershell
ssh singapore-codex
```

进入 **服务器终端** 后运行：

```bash
uname -m
sudo -n docker compose version
sudo -n ss -lnt 'sport = :5001'
test ! -e /home/ubuntu/apps/outlook-email-plus
```

应看到 `aarch64`；端口没有监听项；最后一条退出码应为 0。如果目录已经存在，先确认内容，**不要继续覆盖**。
Compose 至少需支持 `env_file.format: raw`（2.30.0 或更新版本）；当前服务器已满足。

确认后运行：

```bash
sudo install -d -m 700 -o ubuntu -g ubuntu /home/ubuntu/apps/outlook-email-plus
mkdir -m 700 /home/ubuntu/apps/outlook-email-plus/upload
exit
```

回到 **Windows PowerShell** 上传：

```powershell
scp D:\outlook-deploy-upload-20261103\outlook-source.tar.gz singapore-codex:/home/ubuntu/apps/outlook-email-plus/upload/
scp D:\outlook-deploy-upload-20261103\outlook-private.tar.gz singapore-codex:/home/ubuntu/apps/outlook-email-plus/upload/
ssh singapore-codex
```

`scp` 通过 SSH 加密传输；不需要 FTP，不需要把整个项目目录拖到服务器。

## 5. 解包、设置目录权限

以下开始均在 **服务器终端** 执行。

```bash
cd /home/ubuntu/apps/outlook-email-plus
tar -tzf upload/outlook-source.tar.gz
tar -tzf upload/outlook-private.tar.gz
tar -xzf upload/outlook-source.tar.gz
tar -xzf upload/outlook-private.tar.gz
chmod 600 .env.production
sudo install -d -m 700 -o 1001 -g 1001 /home/ubuntu/apps/outlook-email-plus/.runtime
sudo chown -R 1001:1001 /home/ubuntu/apps/outlook-email-plus/data /home/ubuntu/apps/outlook-email-plus/.runtime
sudo find /home/ubuntu/apps/outlook-email-plus/data -type d -exec chmod 700 {} +
sudo find /home/ubuntu/apps/outlook-email-plus/data -type f -exec chmod 600 {} +
```

`tar -t` 只列文件名，不显示密钥值。仅解包你自己生成的可信归档。
容器以 UID/GID `1001:1001` 运行；只给这个项目的数据目录授权，不给其他应用目录递归改权限，不使用 `chmod 777`。
当前代码实际读取的插件路径是数据库旁的 `data/plugins`，不是项目根目录 `plugins`。

## 6. 在 ARM64 服务器构建、启动

```bash
cd /home/ubuntu/apps/outlook-email-plus
sudo -n docker compose -f compose.production.yaml config --quiet
sudo -n docker compose -f compose.production.yaml build --pull app
sudo -n docker compose -f compose.production.yaml up -d --no-build --wait --wait-timeout 120
sudo -n docker compose -f compose.production.yaml ps
curl -fsS http://127.0.0.1:5001/healthz
```

首次构建可能需要数分钟，取决于网络与依赖下载。这里构建出的就是 ARM64 镜像，无须先在 Windows 构建再上传。
最后应得到包含 `"status":"ok"` 的 JSON，容器状态应为 healthy。
不要打开云防火墙的 5001；公网只经过现有 80/443。`http://服务器IP:5001` 无法直接访问是预期设计。
此时尚未接入域名，后台调度也没有启动；不要把健康检查通过当作邮件收取验收通过。

失败时只查看本项目：

```bash
sudo -n docker compose -f compose.production.yaml logs --tail 80 app
```

不要运行不带 `-f compose.production.yaml` 的命令；不要执行系统级 Docker 清理。
`config --quiet` 不打印配置；不要把不带 `--quiet` 的完整 Compose 输出或包含账号信息的日志发给别人。

## 7. 确认真正的可信代理 IP

此时 `.env.production` 的 `PROXY_FIX_ENABLED=false`。在服务器发起一次与 OpenResty 相同的本机连接：

```bash
curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:5001/healthz
sudo -n docker compose -f compose.production.yaml logs --tail 15 app
```

查找刚才 `GET /healthz` 的访问日志；最前面是 Gunicorn 看到的连接方 IP。可能是 `127.0.0.1`，也可能是 Docker 网桥网关；不要照抄假设值。
本方案不允许 Gunicorn 先解释转发协议头，协议修正只由应用按可信连接方决定。

```bash
nano .env.production
```

只修改以下两项，`TRUSTED_PROXIES` 填刚才确认的单个 IP：

```dotenv
PROXY_FIX_ENABLED=true
TRUSTED_PROXIES=填入日志中确认的实际代理连接IP
```

不要填 `0.0.0.0/0`，也不要未经核实信任所有内网网段。`SCHEDULER_AUTOSTART=false` 暂时保留。
保存：`Ctrl+O`、回车；退出：`Ctrl+X`。之后重新创建容器加载环境配置：

```bash
sudo -n docker compose -f compose.production.yaml up -d --no-build --force-recreate --wait --wait-timeout 120
```

应用启用 ProxyFix 后，日志会显示修正后的客户端 IP。将来 Docker 网络重建可能改变网关 IP；若发生 CSRF 或代理异常，暂时关闭 ProxyFix 后按本步骤重新核实，不能简单扩大信任网段。

## 8. Cloudflare + 1Panel 配置域名和 HTTPS

### 8.1 Cloudflare 源站证书

DNS 解析正确不代表源站证书已配置；此前该域名出现过 525，需要给新域名配置 TLS。

建议首次采用 Cloudflare Origin CA：

1. 在 Cloudflare 选择 `ivano.cyou`，进入 SSL/TLS 的 Origin Server 页面，创建源站证书。
2. 确保证书 SAN 包含 `outlook.ivano.cyou`，只申请这个域名或确认相应通配符覆盖。
3. 保存证书 PEM 与私钥；**私钥只在面板和你自己的私密存储中使用，不放进源码包**。
4. 不要先修改影响其他站点的全域 SSL 模式；源站新站点证书安装好后再启用对应域名的 `Full (strict)`。

也可以使用 1Panel 申请受浏览器信任的 Let's Encrypt 证书；若采用 DNS 验证，需要你自己在面板配置最小权限的 Cloudflare API Token。本文不要求把 Token 放到应用中。

### 8.2 1Panel 只新增本站

1. 在 1Panel 的网站管理中，新建**反向代理网站**，域名填 `outlook.ivano.cyou`。
2. 后端目标填 `http://127.0.0.1:5001`。现有 OpenResty 为 host 网络，可访问宿主机回环端口。
3. 在本站 HTTPS 配置中导入刚才的证书与私钥，启用 HTTPS，并开启 HTTP 跳转 HTTPS。
4. 修改**这个网站**的反向代理配置，用 `deploy/openresty-location.conf` 的内容替换已有的对应 `location /`；不要重复添加两个同名 location，也不要替换整份全局 nginx.conf。

### 8.3 恢复 Cloudflare 真实客户端 IP

不要直接把任意请求的 `CF-Connecting-IP` 传给应用。仅信任 Cloudflare 官方 IP 段后才解释该头。
在服务器执行：

```bash
cd /home/ubuntu/apps/outlook-email-plus
python3 deploy/refresh_cloudflare_ips.py
sudo install -d -m 755 /opt/1panel/www/outlook-deploy
sudo install -m 644 deploy/cloudflare-realip.conf /opt/1panel/www/outlook-deploy/cloudflare-realip.conf
```

在 1Panel 的**本站 HTTPS server 块**内、`location` 块之外添加：

```nginx
include /www/outlook-deploy/cloudflare-realip.conf;
```

宿主机 `/opt/1panel/www` 已挂载到 OpenResty 容器的 `/www`，所以 include 使用容器内部路径。
脚本会校验 IPv4/IPv6 段，只有两份列表都成功才写文件；应定期重新生成、安装、测试并 reload。

完成后先检查配置，再平滑重载现有 OpenResty；不要 restart 整个面板或停止其他容器：

```bash
sudo -n docker exec 1Panel-openresty-nD6T nginx -t
sudo -n docker exec 1Panel-openresty-nD6T nginx -s reload
```

**只有上一条配置检查成功才执行 reload。** 如果容器名称已经变更，在 1Panel 中确认实际名称。
回到 Cloudflare，保持此 DNS 记录为橙云代理；为此域名启用 `Full (strict)`。若全域其他源站证书不满足严格验证，用针对该主机名的配置规则，避免影响已有网站。
给此域名设置缓存绕过规则，尤其不能缓存 `/api/*`、`/login`、OAuth 回调和私密邮件页面；首次部署可以整站绕过缓存。
不要为了修复 525 切换到 Flexible；应用要求源站与代理间也使用正确的 HTTPS。

Origin CA 是给 Cloudflare 验证源站用的；如果关闭橙云直接访问，浏览器可能不信任该证书。需要直连访问时使用公开可信证书，不要把这种情况误判为应用错误。

## 9. 公网验收与启用后台任务

在 Windows PowerShell 执行：

```powershell
curl.exe -fsS https://outlook.ivano.cyou/healthz
```

在浏览器打开 `https://outlook.ivano.cyou`，确认：

- HTTPS 无警告；HTTP 跳转到 HTTPS。
- 能登录，登录失败次数限制工作正常；Cookie 包含 `Secure`、`HttpOnly`、`SameSite=Lax`。
- 原有邮箱、分组和设置还在；先选择 1 个测试邮箱读信，不先对全部账号做大批量检测。
- 能看到新收到的邮件、打开邮件及全屏查看；没有被缓存成另一个会话的页面。
- 重启本应用后数据仍存在，登录及读信仍正常。

重启验证只执行：

```bash
cd /home/ubuntu/apps/outlook-email-plus
sudo -n docker compose -f compose.production.yaml restart app
curl -fsS http://127.0.0.1:5001/healthz
```

`restart` 后需等应用就绪，再运行 curl；环境配置更改则必须 `up --force-recreate`，仅 restart 不会重新加载 env_file。
如果启用了 OAuth Token 工具，在 `.env.production` 中把 `OAUTH_REDIRECT_URI` 改为 `https://outlook.ivano.cyou/token-tool/callback`，同时在你的微软应用注册中添加相同回调；不要继续保留本机回调地址。

单账号与通知验收通过后，停止本机同一批账号的后台任务，再把 `.env.production` 中 `SCHEDULER_AUTOSTART` 改成 `true`，重新创建容器。
这属于账号切换验收；可继续保持 false，不影响登录后手动读信。
微软可能因出口位置变化要求再次验证；遇到 429 需减小批量、降低频率，不应立即把并发扩大。

## 10. 备份、更新和回退

首次验收后执行：

```bash
cd /home/ubuntu/apps/outlook-email-plus
sh deploy/backup.sh
```

脚本仅短暂停止本项目，确保没有本应用写入 SQLite 时打包；完成或失败退出时尝试重新启动。本目录必须与教程一致，且不要让其他进程同时写入同一数据库。
备份包含密钥和私密数据，权限为 600，由 ubuntu 创建，可通过 FinalShell 直接下载，不需要更改所有权。保留到另一台设备。
示例中的时间戳需要替换为实际备份名，在 Windows 运行：

```powershell
scp singapore-codex:/home/ubuntu/apps/outlook-email-plus/backups/outlook-实际时间戳.tar.gz D:\你的私密备份目录\
```

在更新前给旧镜像增加保留标签：

```bash
cd /home/ubuntu/apps/outlook-email-plus
container_id=$(sudo -n docker compose -f compose.production.yaml ps -q app)
image_id=$(sudo -n docker inspect --format '{{.Image}}' "$container_id")
sudo -n docker image tag "$image_id" outlook-email-plus:rollback-20261103
```

更新上传新源码包，不重复上传初始私密包覆盖正在使用的数据库。上传前备份；更新使用新标签，例如：

```bash
sudo -n env OUTLOOK_IMAGE_TAG=2.7.0-public-20261105 docker compose -f compose.production.yaml build --pull app
sudo -n env OUTLOOK_IMAGE_TAG=2.7.0-public-20261105 docker compose -f compose.production.yaml up -d --no-build --wait --wait-timeout 120
```

`20261105` 只是未来升级标签示例，不是已发布或已部署的版本；以后所有重建命令都应继续指定你实际启用的标签，或更新 Compose 默认标签。
只回退代码且数据库兼容时，用 `OUTLOOK_IMAGE_TAG=rollback-20261103` 启动。发生数据库迁移时必须同时回退对应数据库和密钥备份；先停止应用，把现有 data 目录移到明确命名的故障保留目录，再恢复，不删除旧数据，不混用遗留 WAL 文件。
不要执行 `docker system prune`、`docker image prune -a` 或随意删除持久目录。保留旧镜像和数据备份比自动拉取 latest 更重要。

## 11. 另一种方式：Windows 先构建 ARM64 镜像

首次部署**不用这条路线**。仅在你以后有 Docker Desktop/Buildx，而且想离线传镜像时采用：

```powershell
docker buildx build --platform linux/arm64 -f deploy/Dockerfile -t outlook-email-plus:2.7.0-public-20261104 --load .
docker save -o outlook-arm64-image.tar outlook-email-plus:2.7.0-public-20261104
scp outlook-arm64-image.tar singapore-codex:/home/ubuntu/apps/outlook-email-plus/upload/
```

服务器运行 `sudo docker load -i upload/outlook-arm64-image.tar`，仍需生产 Compose、`.env.production` 和数据目录，再 `up -d --no-build`。
从 Windows 打包 x86/amd64 镜像不能直接当作 ARM64 原生镜像使用；镜像也不能替代独立的数据和密钥迁移。

## 常见错误

| 现象 | 先检查 |
| --- | --- |
| 525 / 526 | 源站 HTTPS、SNI 域名、证书 SAN/有效期、Cloudflare 严格模式 |
| 502 | 本机 5001 健康检查、容器日志、OpenResty 是否仍是 host 网络 |
| 登录循环或 CSRF 失败 | HTTPS、Secure Cookie、实际可信代理 IP、是否覆盖转发协议头 |
| 数据库 Permission denied | 仅本项目 data 目录的 UID/GID 和权限是否对应 1001 |
| no matching manifest / exec format error | 镜像是不是 linux/arm64 |
| 邮箱凭据解密失败 | 是否完整保留原 SECRET_KEY，raw 配置值是否多加了引号 |
| 429 / 账号验证要求 | 微软出口风控与请求频率，不是 DNS 或 Cloudflare 代理能解决的问题 |

## 依据

- Docker 原生/跨架构构建：https://docs.docker.com/build/building/multi-platform/
- Compose 配置与 raw env_file：https://docs.docker.com/reference/compose-file/services/
- Cloudflare Origin CA：https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/
- Cloudflare 真实客户端 IP：https://developers.cloudflare.com/support/troubleshooting/restoring-visitor-ips/restoring-original-visitor-ips/
- Cloudflare 官方地址列表：https://www.cloudflare.com/ips-v4 、https://www.cloudflare.com/ips-v6

实际 Docker/ARM64 构建、TLS 配置、真实邮箱验证仍需要按本文在服务器执行；本地部署测试不能代替这几项验收。
