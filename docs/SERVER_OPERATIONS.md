# 公网服务器运行与 FinalShell 管理

目标域名：`https://outlook.ivano.cyou`。
部署目录：`/home/ubuntu/apps/outlook-email-plus`。
SSH 用户：`ubuntu`；本服务器 UID/GID：`1001:1001`。
编排：`compose.production.yaml`；镜像标签：`outlook-email-plus:2.7.0-public-20261104`。

## FinalShell 文件管理

使用 ubuntu 用户登录后，在文件面板打开部署目录。应用以相同 UID/GID 运行，数据、插件、运行目录和备份都由 ubuntu 拥有。
无需 root 或 chmod 777；开启显示隐藏文件可看到 `.env.production` 和 `.runtime`。

- `data/outlook_accounts.db`：正式数据库。不可在运行时删除、覆盖或混入旧 WAL 文件。
- `data/plugins`：实际安装的邮箱插件；位于数据库旁，不是源码根目录 plugins。
- `.env.production`：生产配置和原数据库加密密钥，权限 600。不要公开分享。
- `backups`：数据库、密钥与部署配置备份，目录 700、备份文件 600。
- `upload`：迁移或升级包；源码包和私密包必须区分，私密包不得公开。
- `docs`：操作说明；`deploy`：构建、备份及代理配置模板。

容器不挂载源码目录。上传源码不会立刻改变运行服务，必须重新构建镜像。
数据库和 `.runtime` 使用持久化绑定目录；删除这些宿主机文件会直接影响应用。
1Panel 的站点、反代和证书仍由 1Panel 管理，不给 ubuntu 放宽其他站点权限。

## 查看服务与日志

在 FinalShell 终端运行：

```bash
cd /home/ubuntu/apps/outlook-email-plus
sudo -n docker compose -f compose.production.yaml ps
curl -fsS http://127.0.0.1:5001/healthz
sudo -n docker compose -f compose.production.yaml logs --tail 60 app
```

应用只监听本机 5001，不开放云防火墙的 5001。公网由现有 OpenResty 80/443 提供入口。
日志可能包含账号或错误详情，不要直接公开粘贴。不要打印完整 Compose 配置；验证配置使用 `config --quiet`。

## 配置修改、停止与重启

```bash
cd /home/ubuntu/apps/outlook-email-plus
sudo -n docker compose -f compose.production.yaml stop app
sudo -n docker compose -f compose.production.yaml start app
```

修改 `.env.production` 后，仅 restart 不会加载新的环境值，需重新创建容器：

```bash
sudo -n docker compose -f compose.production.yaml up -d --no-build --force-recreate --wait --wait-timeout 120
```

此文件使用 raw 格式；不要给原密钥额外加引号。原 SECRET_KEY 必须稳定，不可因为更新或换域名重新生成。
现有数据库使用你在本地系统设置中修改的密码，`.env.production` 的 LOGIN_PASSWORD 仅用于新建数据库，不覆盖现有密码。

## 后台任务

初次切换的 `SCHEDULER_AUTOSTART=false`，避免与仍在运行的本地后台重复处理。
你确认网页能登录并正常读信、停止本地同一批账号的后台任务后，可改成 true 再重新创建容器。
手动登录及读信不需要启用后台调度。微软可能因出口位置变化要求验证或返回 429，应先小批量验收。

## 备份

```bash
cd /home/ubuntu/apps/outlook-email-plus
sh deploy/backup.sh
```

必须以 ubuntu 用户运行，不能 sudo 整个脚本。脚本仅使用 sudo 调用 Docker，备份文件由 ubuntu 写入，FinalShell 可直接下载。
脚本会短暂停止本应用，打包数据库、运行目录、原密钥与编排，退出时尝试重新启动。不要并发执行，也不要有其他进程写同一个数据库。
备份未加密，下载到私密存储中。保留对应旧镜像；禁止执行系统级 Docker 清理或删除数据目录。

## 源码升级与回退

先执行备份，保留当前镜像：

```bash
container_id=$(sudo -n docker compose -f compose.production.yaml ps -q app)
image_id=$(sudo -n docker inspect --format '{{.Image}}' "$container_id")
sudo -n docker image tag "$image_id" outlook-email-plus:rollback-你的日期
```

上传新的源码，不重新覆盖正式 data 或原密钥。先将 Compose 的默认镜像标签改为新的唯一标签，再执行：

```bash
sudo -n docker compose -f compose.production.yaml config --quiet
sudo -n docker compose -f compose.production.yaml build --pull app
sudo -n docker compose -f compose.production.yaml up -d --no-build --wait --wait-timeout 120
```

只回退兼容代码时，将标签改成已保留的 rollback 标签再 up --no-build。
发生数据库迁移时要同时恢复对应备份：停止应用，保留故障 data 目录，再恢复数据库及密钥，不混用遗留 WAL 文件。恢复前先确认备份和目标路径，不删除故障数据。
镜像保留在 Docker 中，不是可直接拖拽修改的 dist 目录。

## 站点与证书

本站 vhost：`/opt/1panel/www/conf.d/outlook.ivano.cyou.conf`。
反代：`/opt/1panel/www/sites/outlook.ivano.cyou/proxy/root.conf`。
证书：本站 ssl 目录，当前通配符证书到期时间为 2027-01-25。
已检查 1Panel 关联证书：手动 DNS 验证签发，自动续签关闭。用户确认本次保持不变；必须在到期前单独续签或配置自动续签，不能视为已自动维护。
Cloudflare 真实 IP 信任配置仅安装在本站 proxy 目录的子目录中，不修改全局 Nginx。

通过 1Panel 修改反代后，确认仍覆盖转发头、关闭私密页面缓存、保留必要超时和 Cloudflare 来源校验。
该面板可能重新生成配置；编辑后务必测试登录和请求协议。

```bash
sudo -n docker exec 1Panel-openresty-nD6T nginx -t
sudo -n docker exec 1Panel-openresty-nD6T nginx -s reload
```

只有测试成功才 reload；不 restart 整个 OpenResty 容器。证书续签在 1Panel 中管理，不要手动覆盖私钥或只复制一份证书后忘记续期。
将来换到 `outlook.ivanohub.com` 时，新建对应证书和站点、调整 Compose 的 TRUSTED_HOSTS，以及可选的 OAuth 回调和缓存规则；保留原数据库和原 SECRET_KEY。
新域名先验收，旧域名再下线。换域名后重新登录是正常现象。

## 本次部署与备份记录

部署验收记录见 `docs/DEPLOYMENT_RECORD_20261104.md`。
首次上线后备份为 `backups/outlook-20261103T163225Z.tar.gz`，文件名使用 UTC；对应台湾时间 2026-11-04 00:32:25。
此备份已在隔离临时目录中检查 SQLite 完整性、103 个账号与原生产配置，没有覆盖运行中的数据库。
本地私密备份位于 `D:\outlook-deploy-upload-20261104\outlook-20261103T163225Z.tar.gz`。
源码最终包 `upload/outlook-source-final-20261104.tar.gz` 不含数据库和密钥；不要用初始迁移包覆盖现有数据。
