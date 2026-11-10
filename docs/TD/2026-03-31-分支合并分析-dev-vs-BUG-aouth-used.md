# 分支合并分析：dev vs BUG-aouth-used

**分析日期**：2026-03-31  
**分析人**：AI 代理  
**目标**：将 `BUG-aouth-used` 分支的独有改动合入 `dev` 分支

---

## 一、分支基本信息

| 项目 | dev | BUG-aouth-used |
|------|-----|----------------|
| 分歧点 | `926c648` (release: prepare v1.10.0) | `926c648` |
| 分歧后提交数 | 25 | 2 |
| 最新提交 | `497eb26` (前端分页) | `d77fee6` (CI tag 触发) |

---

## 二、BUG-aouth-used 独有提交（2 个）

### 提交 1：`d77fee6` — CI: 将 Docker 发布切换为 tag 触发模式

**文件**：`.github/workflows/docker-build-push.yml`（1 文件，+7/-14）

**改动内容**：
- 删除了 branch 触发（main/master/dev）和 paths 过滤
- 只保留 tag 触发（`v*.*.*`）+ workflow_dispatch
- tags 改为 semver 格式：`type=semver,pattern={{version}}`、`type=semver,pattern={{major}}.{{minor}}`、`type=semver,pattern={{major}}`
- latest 标签仅在 tag 推送时生效

**与 dev 分支冲突**：
- dev 上已有提交 `609da32`（cherry-pick from Buggithubissue `b43211f`），该提交也加了 tag 触发，但**同时保留了** branch 触发和 paths 过滤
- 两个提交对 tags 元数据格式不同：
  - dev 版本：`type=ref,event=branch` + `type=sha,prefix={{branch}}-` + `type=raw,value=latest`
  - BUG-aouth-used 版本：`type=semver,pattern={{version}}` + `type=semver,pattern={{major}}.{{minor}}` + `type=sha,prefix=sha-`

**分析**：BUG-aouth-used 的 CI 策略更激进（仅 tag 触发），而 dev 版本同时支持 branch 构建和 tag 构建，灵活性更高。

### 提交 2：`54bb7c8` — 文档：扩展外部注册 API 文档

**文件**：`registration-mail-pool-api.en.md`、`注册与邮箱池接口文档.md`（2 文件，+659/-749）

**改动内容**：
- 将文档从仅覆盖 pool 端点（claim/release/complete/stats）扩展为覆盖**完整的 external API**
- 新增端点文档：
  - `GET /api/external/health` — 服务健康检查
  - `GET /api/external/capabilities` — 能力发现
  - `GET /api/external/account-status` — 账号状态查询
  - `GET /api/external/messages` — 消息列表
  - `GET /api/external/messages/latest` — 最新消息
  - `GET /api/external/messages/{message_id}` — 消息详情
  - `GET /api/external/messages/{message_id}/raw` — 原始内容
  - `GET /api/external/verification-code` — 验证码提取
  - `GET /api/external/verification-link` — 验证链接提取
  - `GET /api/external/wait-message` — 等待新消息
  - `GET /api/external/probe/{probe_id}` — 异步探测查询
- 新增推荐集成流程
- 新增完整错误码表
- 新增行为说明（租约过期、回调参数匹配、wait-message 语义等）

**与 dev 分支对比**：
- dev 当前文档（来自 `7e05176`）**只覆盖 pool 端点**，没有验证码、消息读取等 API 文档
- BUG-aouth-used 的文档**明显更完整**，对外部集成用户价值很高

---

## 三、与 dev 分支的完整差异统计

直接 diff 显示 97 文件、-20742 行差异，但这是因为 **dev 分支有大量 BUG-aouth-used 没有的新功能**，包括：
- temp_mail 平台化（provider_cf、provider_custom、provider_factory、temp_mail_service 等）
- poll-engine 统一轮询引擎
- compact-poll 测试
- mailbox_resolver 服务
- 大量新文档（TD、TDD、BUG 等）

**这些差异不影响合并方向**——我们是把 BUG-aouth-used 的 2 个独有提交合入 dev，不是反向合并。

---

## 四、合并策略推荐

### 策略：Cherry-pick `54bb7c8`（文档提交），跳过 `d77fee6`（CI 提交）

**理由**：

| 提交 | 推荐操作 | 理由 |
|------|----------|------|
| `d77fee6` (CI tag 触发) | ⏭️ **跳过** | dev 上已有 `609da32` 的 CI tag 触发配置，且 dev 版本更灵活（同时支持 branch 和 tag）。如果用户决定只保留 tag 触发，可以后续单独调整 |
| `54bb7c8` (API 文档扩展) | ✅ **Cherry-pick** | 文档独有价值很高，dev 当前文档只有 pool 端点，缺少完整 external API 文档 |

### 预期冲突

Cherry-pick `54bb7c8` 时可能在以下文件产生冲突：
- `registration-mail-pool-api.en.md` — 两个分支都修改过
- `注册与邮箱池接口文档.md` — 同上

冲突解决策略：**取 BUG-aouth-used 的版本**（因为它的文档更完整）。

---

## 五、风险评估

| 风险 | 等级 | 说明 |
|------|------|------|
| 代码冲突 | 🟢 低 | 只有文档文件，不影响功能代码 |
| 功能回归 | 🟢 无 | 纯文档改动 |
| CI 配置分歧 | 🟡 中 | 跳过 CI 提交后，dev 保持 branch+tag 双触发，后续可按需调整 |

---

## 六、执行清单

- [ ] Cherry-pick `54bb7c8`（API 文档）
- [ ] 解决文档文件冲突（取 BUG-aouth-used 版本）
- [ ] 全量测试确认无回归
- [ ] 确认文档内容与当前代码实现一致
