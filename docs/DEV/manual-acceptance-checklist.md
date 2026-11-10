# Docker API 自更新（策略A）人工验收清单

## 测试目标

验证策略A（彻底禁止本地构建镜像触发 Docker API 更新）是否正确实现：
- ✅ 官方远程镜像可以正常触发更新
- ✅ 本地构建镜像会被明确拦截（403/500 错误）
- ✅ 部署信息展示正确的镜像名和警告提示
- ✅ A2 updater 容器流程正常工作

## 前置准备

### 1. 构建测试镜像（模拟本地构建）
```bash
# 在 dev 分支构建一个本地测试镜像
docker build -t outlook-email-local:test .
```

### 2. 推送当前代码到远程镜像（可选，用于测试正向更新）
```bash
# 如果你有 DockerHub 推送权限
docker build -t guangshanshui/outlook-email-plus:test-a2 .
docker push guangshanshui/outlook-email-plus:test-a2
```

### 3. 准备环境变量文件
创建 `.env.test` 文件：
```env
SECRET_KEY=test-secret-key-for-acceptance
LOGIN_PASSWORD=admin123
DOCKER_SELF_UPDATE_ALLOW=true
WATCHTOWER_HTTP_API_TOKEN=test-token
```

---

## 测试用例

### 用例1：负向测试 - 本地构建镜像应被拦截

**目标**：验证本地构建镜像无法触发 Docker API 更新

**步骤**：
1. 使用本地构建镜像启动容器：
   ```bash
   docker run -d \
     --name outlook-local-test \
     -p 5001:5000 \
     -v /var/run/docker.sock:/var/run/docker.sock \
     -e SECRET_KEY=test-secret \
     -e LOGIN_PASSWORD=admin123 \
     -e DOCKER_SELF_UPDATE_ALLOW=true \
     outlook-email-local:test
   ```

2. 访问 `http://localhost:5001` 并登录

3. 进入 **系统设置 → 一键更新** 页面

4. 观察 **部署信息检测** 区域应显示：
   - ⚠️ 警告："当前为本地构建模式，一键更新将无法工作"
   - 建议："请使用远程镜像部署..."

5. 切换更新方式为 **Docker API**

6. 点击 **立即更新** 按钮

**预期结果**：
- ❌ 更新触发失败
- 错误提示：`"检测到本地构建镜像（RepoDigests 为空），已按安全策略禁止 Docker API 一键更新"`
- HTTP 状态码：403 或 500
- 容器继续正常运行（未被 stop）

**清理**：
```bash
docker stop outlook-local-test
docker rm outlook-local-test
```

---

### 用例2：负向测试 - 本地构建但伪装成官方名也应被拦截

**目标**：验证即使镜像名在白名单内，RepoDigests 为空也会被拦截

**步骤**：
1. 构建并标记为官方镜像名（仅本地，不推送）：
   ```bash
   docker build -t guangshanshui/outlook-email-plus:fake-local .
   ```

2. 使用 `docker-compose.docker-api-test.yml` 启动（它已配置为这种场景）：
   ```bash
   docker compose -f docker-compose.docker-api-test.yml up -d --build
   ```

3. 访问 `http://localhost:5003` 并登录

4. 进入 **系统设置 → 一键更新**，切换到 **Docker API** 模式

5. 点击 **立即更新**

**预期结果**：
- ❌ 更新触发失败
- 错误提示：`"检测到本地构建镜像（RepoDigests 为空），已按安全策略禁止 Docker API 一键更新"`
- 容器继续正常运行

**清理**：
```bash
docker compose -f docker-compose.docker-api-test.yml down
```

---

### 用例3：正向测试 - 官方远程镜像应能正常更新

**目标**：验证真正的远程镜像可以触发 Docker API 更新流程

**前提**：需要 DockerHub 上存在一个可 pull 的官方镜像（如 `guangshanshui/outlook-email-plus:latest`），且当前环境能访问 DockerHub。

> 说明：策略A会基于 **RepoDigests** 判断是否为“远程拉取镜像”。
> - `docker pull` 得到的镜像通常 RepoDigests 非空（允许触发更新）
> - `docker build` 得到的镜像通常 RepoDigests 为空（会被拦截）

**步骤**：
1. 从远程拉取镜像并启动：
   ```bash
   docker pull guangshanshui/outlook-email-plus:latest
   
   docker run -d \
     --name outlook-remote-test \
     -p 5004:5000 \
     -v /var/run/docker.sock:/var/run/docker.sock \
     -v outlook-remote-data:/app/data \
     -e SECRET_KEY=test-secret \
     -e LOGIN_PASSWORD=admin123 \
     -e DOCKER_SELF_UPDATE_ALLOW=true \
     guangshanshui/outlook-email-plus:latest
   ```

2. 访问 `http://localhost:5004` 并登录

3. 进入 **系统设置 → 一键更新**

4. 观察 **部署信息检测** 区域应显示：
   - ✅ 镜像名：`guangshanshui/outlook-email-plus:latest`
   - ✅ 无 "本地构建" 警告
   - ✅ "Docker API 可用" 提示

5. 切换更新方式为 **Docker API**

6. 点击 **立即更新** 按钮

**预期结果**：
- ✅ 返回成功提示：`"更新任务已启动: oep-updater-xxxxx (短ID)"`
- ✅ 后台创建了 updater 容器（可通过 `docker ps -a` 看到短暂存在的 `oep-updater-` 容器）
- ✅ updater 容器会执行自更新流程：
  - 如果 `docker pull` 后镜像 digest 与当前一致：**不会 stop 旧容器**，返回 `"镜像已是最新，无需更新"`
  - 如果 digest 不一致：会进入 stop/start/healthcheck/rename/cleanup 流程（此时旧容器会被 stop，页面会断开）

**验证 updater 日志**：
```bash
# 查找最近的 updater 容器（如果设置了 auto_remove，可能已被删除）
docker ps -a | grep oep-updater

# 如果容器还存在，查看日志
docker logs <updater-container-id>

# 应看到类似输出：
# {'success': True, 'message': '容器自更新完成', ...}
# 或
# {'success': True, 'message': '镜像已是最新，无需更新', ...}
```

**清理**：
```bash
docker stop outlook-remote-test
docker rm outlook-remote-test
docker volume rm outlook-remote-data
```

---

### 用例4：部署信息检测准确性

**目标**：验证 `/api/system/deployment-info` 接口返回的镜像信息准确

**步骤**：
1. 分别使用本地镜像和远程镜像启动容器（参考用例1和用例3）

2. 通过浏览器开发者工具或 curl 调用接口：
   ```bash
   # 本地镜像容器
   curl -H "Cookie: session=<your-session>" http://localhost:5001/api/system/deployment-info
   
   # 远程镜像容器
   curl -H "Cookie: session=<your-session>" http://localhost:5004/api/system/deployment-info
   ```

**预期结果**：

**本地镜像容器**：
```json
{
  "success": true,
  "deployment": {
    "image": "outlook-email-local:test",
    "is_local_build": true,
    "docker_api_available": true,
    "can_auto_update": false,
    "warnings": [
      {
        "type": "local_build",
        "severity": "warning",
        "message": "当前为本地构建模式，一键更新将无法工作",
        "suggestion": "请使用远程镜像部署..."
      }
    ]
  }
}
```

**远程镜像容器**：
```json
{
  "success": true,
  "deployment": {
    "image": "guangshanshui/outlook-email-plus:latest",
    "is_local_build": false,
    "docker_api_available": true,
    "can_auto_update": true,
    "warnings": []
  }
}
```

---

## 验收标准

### 必须通过的检查项

- [x] **负向用例1**：本地构建镜像触发更新被 403/500 拦截
- [x] **负向用例2**：本地构建伪装官方名触发更新被拦截
- [x] **正向用例3**：官方远程镜像可以成功触发更新流程（A2 helper 真实切换验证已完成）
- [x] **部署信息**：本地镜像显示警告，远程镜像无警告/不标记为 local build
- [x] **错误提示**：被拦截时错误消息明确提示 "本地构建" 和 "RepoDigests 为空"
- [x] **容器安全**：触发更新失败时，原容器不会被 stop（继续运行）

---

## 附录：本次实际验收记录（2026-04-07）

> 说明：以下为一次完整的“正向热更新切换”实测结果摘要，用于证明用例3不只是“触发成功”，而是完成了 stop/start/rename/backup 的全链路。

### 正向热更新切换（远程镜像 + tag 同名但 digest 变更）

- 目标容器：`outlook-canary`（端口 `5005->5000`，挂载 docker.sock，`DOCKER_SELF_UPDATE_ALLOW=true`）
- 使用镜像：`guangshanshui/outlook-email-plus:a2-strategyA-canary`
- 更新触发接口：`POST /api/system/trigger-update?method=docker_api`

触发返回：
```json
{"success": true, "message": "更新任务已启动: oep-updater-1775571256 (e21bf4afbbdb)"}
```

更新后容器状态：
- 新 `outlook-canary`：Up(healthy)，image id 变更为 `sha256:21aba8bda26d...`
- 旧容器：被 rename 为 `outlook-canary_backup_1775571270`，Exited(0)，image id 为 `sha256:056f69613d8d...`

应用可用性验证：
- `GET /healthz` 返回 `status=ok`，证明新容器已接管服务。

### 可选检查项

- [ ] updater 容器日志清晰（通过 `docker logs` 查看）
- [ ] 新容器 healthcheck 通过后旧容器才被重命名/删除（如果触发了真正的更新）
- [ ] UI 上的警告提示支持中英文切换

---

## 回退计划

如果验收失败，需要回退代码：
```bash
git reset --hard HEAD~1  # 回退最近一次 commit
# 或
git checkout <previous-commit-hash>
```

---

## 附录：快速测试脚本

创建 `test-docker-api-update.sh`：
```bash
#!/bin/bash
set -e

echo "=== 测试用例1: 本地构建镜像应被拦截 ==="
docker build -t outlook-email-local:test .
docker run -d --name test-local -p 5001:5000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SECRET_KEY=test -e LOGIN_PASSWORD=admin123 \
  -e DOCKER_SELF_UPDATE_ALLOW=true \
  outlook-email-local:test

echo "等待容器启动..."
sleep 10

echo "请手动访问 http://localhost:5001 测试更新触发是否被拦截"
read -p "按 Enter 继续清理..."

docker stop test-local && docker rm test-local

echo "=== 测试用例3: 远程镜像应能正常更新 ==="
docker pull guangshanshui/outlook-email-plus:latest
docker run -d --name test-remote -p 5004:5000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SECRET_KEY=test -e LOGIN_PASSWORD=admin123 \
  -e DOCKER_SELF_UPDATE_ALLOW=true \
  guangshanshui/outlook-email-plus:latest

echo "等待容器启动..."
sleep 10

echo "请手动访问 http://localhost:5004 测试更新触发是否成功"
read -p "按 Enter 继续清理..."

docker stop test-remote && docker rm test-remote

echo "=== 验收测试完成 ==="
```

运行：
```bash
chmod +x test-docker-api-update.sh
./test-docker-api-update.sh
```

---

## 问题排查

### 1. "无法连接 Docker API"
- 确认 `/var/run/docker.sock` 已挂载
- 确认容器内有读写权限：`ls -l /var/run/docker.sock`

### 2. "镜像名不在白名单内"
- 确认镜像名包含 `guangshanshui/outlook-email-plus` 前缀
- 检查 `ALLOWED_IMAGE_PREFIXES` 配置

### 3. updater 容器立即退出
- 查看 updater 日志：`docker logs <updater-id>`
- 确认 `DOCKER_UPDATE_TARGET_CONTAINER_ID` 环境变量正确传递

### 4. 更新后无法访问
- 检查新容器是否正常启动：`docker ps`
- 检查新容器 healthcheck 状态：`docker inspect <container>`
    - 如果旧容器被保留为备份，可手动恢复：`docker start <old-container-name>_backup_<timestamp>`

### 5. 通过脚本调用 trigger-update 返回 CSRF_TOKEN_INVALID

现象：
- POST `/api/system/trigger-update` 返回 400，错误码 `CSRF_TOKEN_INVALID`，提示 "The CSRF token is missing"

原因：
- 该接口受 `flask-wtf` CSRF 保护，非浏览器脚本调用需要显式携带 CSRF token

解决：
1. 先登录：`POST /login`
2. 获取 token：`GET /api/csrf-token`
3. 再调用更新：`POST /api/system/trigger-update?method=docker_api` 并在 header 中加入：
   - `X-CSRFToken: <token>`
