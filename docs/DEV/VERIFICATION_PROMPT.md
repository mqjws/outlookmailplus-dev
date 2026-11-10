# Outlook Email Plus — A2 方案功能验证提示词

## 项目背景

Outlook Email Plus 是一个基于 Flask 的 Outlook 邮箱管理 Web 应用，使用 Docker 部署。我们正在实现"一键更新"功能的改进——**A2 方案（按需 helper job 容器）**。

### 核心问题
原有的 Docker API 自更新存在"自杀问题"：容器在内部 stop 自己后，执行更新的后台线程也被杀死，导致后续步骤无法完成。

### A2 方案
- app 容器收到更新请求 → 通过 Docker API 创建临时 updater 容器 → 立即返回 HTTP 响应
- updater 容器执行完整更新流程（pull → create → stop 旧 → start 新 → healthcheck → rename → cleanup）
- updater 容器退出后 auto_remove 自动清理
- 用户视角：平时 1 容器，更新时短暂 2 容器，最终恢复 1 容器

---

## 请验证以下功能点

### 一、后端 API 功能验证

#### 1. healthz 端点增强
- **文件**: `outlook_web/controllers/system.py`
- **验证**: `healthz()` 函数是否返回 `status`、`boot_id`（`{timestamp}-{pid}` 格式）、`version` 三个字段
- **目的**: 前端通过 `boot_id` 变化判断容器是否真正发生了重启

#### 2. Docker API 更新触发入口
- **文件**: `outlook_web/controllers/system.py` → `_trigger_docker_api_update()`
- **验证**:
  - [ ] 是否检查 `DOCKER_SELF_UPDATE_ALLOW` 开关
  - [ ] 是否检查 docker.sock 可访问性
  - [ ] 是否通过 `HOSTNAME` 环境变量获取当前容器 ID
  - [ ] 是否调用 `spawn_update_helper_container()` 而非直接 `self_update()`
  - [ ] 是否在主线程记录审计日志（而非后台线程）
  - [ ] 是否快速返回 HTTP 响应（不阻塞等待更新完成）

#### 3. 部署信息 API 增强
- **文件**: `outlook_web/controllers/system.py` → `api_deployment_info()`
- **验证**:
  - [ ] 是否返回 `docker_api_available` 字段
  - [ ] 镜像名检测是否优先使用 Docker API（而非仅环境变量）
  - [ ] 警告信息是否根据当前 `update_method` 动态调整：
    - Watchtower 模式 + Watchtower 不可达 → severity=error
    - Docker API 模式 + Watchtower 不可达 → severity=info（可忽略）
    - Docker API 模式 + docker.sock 不可用 → severity=error
  - [ ] `can_auto_update` 逻辑是否同时考虑 Watchtower 和 Docker API 可用性

### 二、Docker 更新服务验证

#### 4. 新增函数 `get_container_info()`
- **文件**: `outlook_web/services/docker_update.py`
- **验证**:
  - [ ] 是否支持通过容器 ID/短 ID/名称查找
  - [ ] volumes 解析是否同时支持 bind mount 和 named volume
  - [ ] 是否从 `Mounts` 信息中提取完整的挂载详情

#### 5. 新增函数 `spawn_update_helper_container()`
- **文件**: `outlook_web/services/docker_update.py`
- **验证**:
  - [ ] 是否检查 docker.sock 可用性
  - [ ] 是否检查并发更新（已有 updater 在跑则拒绝）
  - [ ] 是否进行镜像白名单校验
  - [ ] 是否设置 `start_delay_seconds` 延迟（给 HTTP 响应留时间）
  - [ ] 是否配置 `auto_remove=True`
  - [ ] 是否透传 Docker 凭证（`DOCKER_AUTH_CONFIG` / `DOCKER_CONFIG`）
  - [ ] 是否添加 `com.centurylinklabs.watchtower.enable=false` 标签
  - [ ] 是否配置 `restart_policy={"Name": "no"}`

#### 6. 新增模块 `docker_update_helper.py`
- **文件**: `outlook_web/services/docker_update_helper.py`
- **验证**:
  - [ ] 入口函数 `main()` 是否读取环境变量
  - [ ] 是否先 sleep(delay) 再执行更新
  - [ ] 是否调用 `docker_update.self_update(target_container_id=...)`
  - [ ] 退出码是否正确（0=成功, 1=更新失败, 2=参数缺失）

#### 7. `self_update()` 步骤顺序
- **文件**: `outlook_web/services/docker_update.py` → `self_update()`
- **验证**:
  - [ ] 是否先 stop 旧容器再 start 新容器（避免端口冲突）
  - [ ] 新容器启动失败时是否尝试恢复旧容器
  - [ ] 健康检查失败时是否尝试恢复旧容器
  - [ ] 是否支持 `target_container_id` 参数（供 updater 容器指定目标）

#### 8. `validate_image_name()` 增强
- **文件**: `outlook_web/services/docker_update.py`
- **验证**:
  - [ ] 是否正确处理 digest 形式（`repo@sha256:...`）
  - [ ] 是否正确处理含 registry port 的镜像名（`myreg:5000/repo:tag`）

### 三、前端功能验证

#### 9. `waitForRestart()` 轮询优化
- **文件**: `static/js/main.js`
- **验证**:
  - [ ] 是否在轮询前记录 `initialBootId`
  - [ ] 是否通过 `boot_id` 变化判断重启完成（而非仅靠 HTTP 状态码）
  - [ ] Docker API 模式超时是否为 180s（Watchtower 为 90s）
  - [ ] 超时提示是否区分"Docker API 模式"和"Watchtower 模式"

#### 10. 部署信息警告渲染
- **文件**: `static/js/main.js`
- **验证**:
  - [ ] `loadDeploymentInfo()` 是否在 `loadSettings()` 中被调用
  - [ ] `renderDeploymentWarnings()` 是否支持中/英文切换重渲染
  - [ ] 警告样式是否区分 severity（error/warning/info）

#### 11. `triggerUpdate()` 统一逻辑
- **文件**: `static/js/main.js`
- **验证**:
  - [ ] Docker API 和 Watchtower 模式是否都走 `waitForRestart()`
  - [ ] 是否记录 `window.__lastUpdateMethod` 供超时判断

### 四、安全验证

- [ ] 白名单校验是否覆盖所有入口（API 层 + `spawn_update_helper_container` 内部）
- [ ] `DOCKER_SELF_UPDATE_ALLOW` 是否默认为 false
- [ ] updater 容器是否排除 Watchtower 自动更新
- [ ] 审计日志是否在主线程记录（避免后台线程无 request context）
- [ ] Docker 凭证透传是否只传递已存在的环境变量

### 五、边界条件验证

- [ ] `HOSTNAME` 为空时是否返回明确错误
- [ ] 已有 updater 运行时是否拒绝重复更新
- [ ] 本地构建镜像是否被正确识别并阻止自动更新
- [ ] 新容器启动失败 → 旧容器恢复流程是否完整
- [ ] healthcheck 失败 → 旧容器恢复流程是否完整

---

## 改动文件清单

| 文件 | 改动类型 | 改动量 |
|------|---------|--------|
| `outlook_web/services/docker_update_helper.py` | **新增** | +69 行 |
| `outlook_web/services/docker_update.py` | 修改 | +321/-27 行 |
| `outlook_web/controllers/system.py` | 修改 | +213/-58 行 |
| `static/js/main.js` | 修改 | +223/-36 行 |
| `templates/index.html` | 修改 | +43/-43 行（格式+新增容器） |
| `tests/test_error_and_trace.py` | 修改 | +48/-15 行 |
| `tests/test_smoke_contract.py` | 修改 | +3 行 |
| `docker-compose.docker-api-test.yml` | **新增** | +50 行 |
| `docker-compose.hotupdate-test.yml` | 修改 | +2 行 |
| `docs/DEV/hot-update-ai-prompt.md` | 修改 | +44/-4 行 |
| `docs/DEV/hot-update-baseline.md` | 修改 | +78/-24 行 |
| `WORKSPACE.md` | 修改 | +275 行 |

总计: **+1052 行 / -198 行**

---

## 已知限制（本地测试验证的结论）

1. 本地构建镜像无法完成完整 pull→create→stop→start→rename 流程（远程 registry 没有）
2. 端到端测试需在真实远程镜像环境下进行
3. healthz 的 `boot_id` 在非容器环境（如本地 Flask）下也会生成，但只有容器重启才会变化
