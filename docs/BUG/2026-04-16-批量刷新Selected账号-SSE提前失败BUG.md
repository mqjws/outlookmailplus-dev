# 批量刷新 Selected 账号：SSE 提前失败（BUG）

**创建日期**: 2026-04-16  
**关联 Issue**: https://github.com/ZeroPointSix/outlookEmailPlus/issues/45  
**关联模块**: `static/js/main.js`、`outlook_web/controllers/accounts.py`、`outlook_web/services/refresh.py`  
**状态**: 🟢 已恢复修复（2026-04-16，会话内二次落地并复验）  
**优先级建议**: P1（核心手动刷新链路）

---

## 1. 问题概述

用户在前端勾选账号后执行“刷新 Token”，请求 `POST /api/accounts/refresh/selected` 返回 200，但刷新流程未真正执行完成，前端表现为“失败/无有效后端细节”。

---

## 2. 现场证据

### 2.1 访问日志特征

日志可见：

- `POST /api/accounts/refresh/selected HTTP/1.1" 200 ...`
- 同时仅有健康检查 `GET /healthz`，未观察到后续可证明批量刷新完成的链路日志

结论：请求已到后端，不是前端在发起前被拦截。

### 2.2 前端调用链路

`static/js/main.js` 中：

- `showBatchRefreshConfirm()` 收集 `selectedAccountIds`
- `batchRefreshSelected(accountIds)` 发起 `fetch('/api/accounts/refresh/selected', { method: 'POST' ... })`
- 随后读取 `response.body` 并按 SSE `data: {...}` 事件推进 UI

---

## 3. 深度根因分析

### 3.1 后端进入点

`outlook_web/controllers/accounts.py`:

- `api_refresh_selected_accounts()` 接收 `account_ids`
- 返回 `Response(generate(), mimetype='text/event-stream')`
- `generate()` 内部 `yield from refresh_service.stream_refresh_selected_accounts(...)`

### 3.2 出错点（核心）

`outlook_web/services/refresh.py`:

- 查询语句（selected 刷新路径）取回 `all_rows`
- 过滤语句：

```python
accounts = [
    row for row in all_rows if is_refreshable_outlook_account(row["account_type"], provider=row.get("provider"))
]
```

这里的 `row` 实际类型为 `sqlite3.Row`（由 `outlook_web/db.py` 的 `conn.row_factory = sqlite3.Row` 决定），该类型**不支持 `.get()`**。

因此会触发：

- `AttributeError: 'sqlite3.Row' object has no attribute 'get'`

### 3.3 为什么“后端几乎没日志”

同函数最外层有 `except Exception as e`，异常会被转为 SSE `type=error` 返回；但当前分支缺少显式 stack trace 日志输出，导致现场常见表现是“请求 200 + 前端报失败 + 服务日志不直观”。

---

## 4. 影响范围

1. 仅影响 **指定账号批量刷新** 路径（`/api/accounts/refresh/selected`）
2. 不直接影响：
   - `/api/accounts/refresh-all`
   - `/api/accounts/refresh-failed`
   - 单账号刷新 `/api/accounts/<id>/refresh`
3. 若用户混选 IMAP/Outlook，理论上应“跳过 IMAP 并继续 Outlook”，但当前会在过滤阶段提前异常，导致整批任务不能按预期执行。

---

## 5. 修复方案（已落地）

### 已实施项

1. selected 刷新查询补齐 `provider` 列（与过滤规则一致）
2. `row.get("provider")` 改为 `sqlite3.Row` 可用的字段访问方式：`row["provider"]`
3. 补充 selected 刷新回归测试，覆盖混合账号（Outlook + IMAP）场景（新增独立测试文件）

> ✅ 2026-04-16 本会话已完成二次落地，当前工作树中上述两处问题已修复。

### 后续可选增强

1. 在 selected 刷新最外层异常分支增加结构化异常日志（含 trace_id/run_id）

---

## 6. 验证结果

### 6.1 历史验证记录

1. 单测（新增 selected 回归用例）：
   - `python -m unittest tests.test_refresh_outlook_only.RefreshOutlookOnlyTests.test_refresh_selected_mixed_accounts_streams_outlook_only_and_skips_imap -v`
   - 结果：`OK`
2. 模块回归：
   - `python -m unittest tests.test_refresh_outlook_only -v`
   - 结果：`Ran 8 tests ... OK`
3. 行为验证结论：
   - mixed 选择下 selected 刷新仅处理 Outlook
   - IMAP 被跳过
   - SSE `start/progress/complete` 事件完整返回

---

## 7. 当前真实状态（以当前工作树为准）

1. **Issue #45 根因已完成恢复修复**：
   - `outlook_web/services/refresh.py` 的 selected 查询已包含 `provider` 列；
   - 过滤逻辑已从 `row.get("provider")` 改为 `row["provider"]`。
2. 新增回归测试：`tests/test_refresh_selected_issue45.py`
   - 用例：`test_selected_refresh_mixed_accounts_streams_outlook_only_and_skips_imap`
   - 覆盖混合选择时“Outlook 刷新、IMAP 跳过、SSE start/progress/complete 完整返回”。
3. 本会话内定向验证通过：
   - `python -m unittest tests.test_refresh_selected_issue45 -v` → `OK`
   - `python -m unittest tests.test_refresh_outlook_only tests.test_oauth_tool -v` → `Ran 78 tests ... OK`

4. 补充回归（2026-04-17，本会话续跑）：
   - 聚焦回归：
     - `python -m unittest tests.test_refresh_outlook_only tests.test_oauth_tool tests.test_refresh_selected_issue45 -v`
     - 结果：`Ran 79 tests ... OK`
   - 全量分片回归（严格 300000ms 上限）：
     - 分片1：`Ran 435 tests ... OK (skipped=6)`
     - 分片2：`Ran 168 tests ... OK (skipped=1)`
     - 分片3：首次超时（非失败），拆分后：
       - 3A：`Ran 210 tests in 216.372s ... OK`
       - 3B：`Ran 132 tests in 12.155s ... OK`
     - 分片4：`Ran 243 tests ... OK`
    - 结论：未观察到与 Issue #45 修复相关的新回归；超时问题来自分片时长而非断言失败。

5. 补充回归（2026-04-17，本会话继续）：
   - 再次按 4 分片执行全量 unittest：
     - 分片1：`Ran 303 tests in 140.802s`，`OK`
     - 分片2：`Ran 263 tests in 48.194s`，`OK`
     - 分片3：`Ran 270 tests in 45.180s`，`OK (skipped=7)`
     - 分片4：`Ran 352 tests in 74.162s`，`OK`
   - 结论：本轮再次全量分片回归通过，Issue #45 修复未引入新增回归。

6. 用户体验补强（2026-04-17）：selected 刷新失败提示统一化
   - 背景：人工验收中反馈“刷新失败”提示过于笼统，缺少可执行指引。
   - 本轮改造：
     - 后端 `outlook_web/services/refresh.py`
       - 冲突场景保留 `REFRESH_CONFLICT`，并补充更清晰 `message/message_en`
       - selected 流水线兜底异常码细化为 `REFRESH_SELECTED_STREAM_FAILED`
       - `details` 改为结构化（`cause + hint`）以便前端统一展示
     - 前端 `static/js/main.js`
       - SSE error 统一走模板化提示：
         - 显示错误码
         - 给出 3 步可执行处理建议
         - 附带 Trace ID 反馈指引（若存在）
    - 相关回归：
      - `python -m unittest tests.test_refresh_selected_issue45 -v` -> `OK`
      - `python -m unittest tests.test_refresh_outlook_only -v` -> `OK`
      - `python -m unittest tests.test_frontend_account_type_and_refresh_suggestions_contract -v` -> `OK`

7. 补充回归（2026-04-17，本会话继续）
   - 按“selected-refresh / oauth-tool / 前端错误提示契约”三组定向复跑：
     - `python -m unittest tests.test_refresh_selected_issue45 -v` -> `Ran 1 test ... OK`
     - `python -m unittest tests.test_oauth_tool.OAuthToolApiAccountListTests -v` -> `Ran 4 tests ... OK`
     - `python -m unittest tests.test_frontend_account_type_and_refresh_suggestions_contract -v` -> `Ran 6 tests ... OK`
   - 结论：
     - Issue #45 的 selected 混合账号刷新链路维持通过；
     - OAuth Tool 空态列表回归维持通过；
     - 前端失败提示统一化契约维持通过。

8. 针对用户现场问题的继续修复（2026-04-17，本会话继续）
   - 现场新增观察：
     - 人工验收日志出现 `POST /api/accounts/refresh-failed` -> `409`，`code=REFRESH_CONFLICT`。
     - 说明当前痛点不仅是 selected 失败提示，还包括“刷新冲突时文案与前端展示不够可执行”。
   - 本轮代码修复：
     - 后端 `outlook_web/services/refresh.py`
       - 统一 scheduled / selected / retry_failed 三条冲突分支：
         - `message`: `当前已有刷新任务执行中，请等待当前任务完成后再重试`
         - `message_en`: `Another refresh task is already running. Wait for it to finish and retry.`
     - 前端 `static/js/main.js`
       - `refreshAllAccounts()` 增加 SSE `type=error` 分支，冲突时展示 warning + 详情；
       - `retryFailedAccounts()` 对 `REFRESH_CONFLICT` 走单独可执行提示，不再只给通用“重试失败”。
   - 回归补强：
     - `tests/test_refresh_outlook_only.py` 新增 3 条冲突路径测试：scheduled / selected / retry_failed
     - `tests/test_frontend_account_type_and_refresh_suggestions_contract.py` 新增 2 条前端契约测试：
       - refresh-all 的 SSE error 分支
       - retry-failed 的冲突 warning 分支
   - 回归结果：
     - `python -m unittest tests.test_refresh_outlook_only -v` -> `Ran 10 tests ... OK`
     - `python -m unittest tests.test_frontend_account_type_and_refresh_suggestions_contract -v` -> `Ran 8 tests ... OK`
   - 结论：
     - 已把“冲突场景的可执行提示”从 selected 扩展到全量刷新/重试失败链路，前后端语义与展示保持一致。

9. 人工验收服务状态（2026-04-17，本会话继续）
   - 按用户要求直接启动本地服务用于现场点测。
   - 当前监听确认：`0.0.0.0:5000`（Listen，OwningProcess=`49344`）。
   - 可访问地址：`http://127.0.0.1:5000`
   - 启动过程日志（保留轨迹）：
     - `manual_acceptance_5000_20260417_110841.out.log/.err.log`
     - `manual_acceptance_5000_20260417_112303.out.log/.err.log`
   - 说明：前两次启动尝试虽未最终保持监听，但日志显示服务初始化成功；最终已通过后台包装进程稳定拉起并保持监听，可继续验证冲突提示体验。

10. 日志复盘后新增结论（2026-04-17，本会话继续）
   - 用户反馈“单次全量刷新也失败且提示不清晰”后，复读多轮验收日志发现：
     - 一类是冲突：`REFRESH_CONFLICT`（409）
     - 另一类是权限不足：`NO_MAIL_PERMISSION`（403）
       - 日志证据：`manual_acceptance_5000_20260417_110841.err.log` 中
         - `GET /api/accounts/trigger-scheduled-refresh?force=true` 后
         - `code=NO_MAIL_PERMISSION status=403 type=PermissionError details=scope=...`
   - 这说明“单次全量刷新失败”并不一定是锁冲突，也可能是账号 Graph 授权 scope 不含邮件读取权限。
   - 因此后续前端体验收敛目标应包含：
     - 冲突类（REFRESH_CONFLICT）提示“等待当前任务完成后再重试”
     - 权限类（NO_MAIL_PERMISSION）提示“重新授权并补齐 Mail.Read/Mail.ReadWrite scope 后再试”

11. 单次全量刷新权限失败提示补强（2026-04-17，本会话继续）
   - 目标：修复“单次全量刷新失败仅显示笼统报错”体验。
   - 前端更新：`static/js/main.js`
     - 新增 `buildRefreshAllPermissionErrorSummary(errorPayload)`；
     - 在 `refreshAllAccounts()` 的 SSE error 分支中，`NO_MAIL_PERMISSION` 走专门提示：
       - 显示 `[Code] NO_MAIL_PERMISSION`
       - 明确两步操作：重新授权 + 补齐 `Mail.Read / Mail.ReadWrite`
       - 提供 Trace ID 反馈指引
   - 测试更新：`tests/test_frontend_account_type_and_refresh_suggestions_contract.py`
     - 新增 `test_refresh_all_no_mail_permission_uses_actionable_summary`
   - 回归结果：
     - `python -m unittest tests.test_frontend_account_type_and_refresh_suggestions_contract -v` -> `Ran 9 tests ... OK`
     - `python -m unittest tests.test_refresh_outlook_only -v` -> `Ran 10 tests ... OK`
   - 结论：
     - 对“冲突失败”和“权限失败”两类现场问题均已提供可执行提示，不再只有通用“刷新失败”。

12. 当前验收服务状态（2026-04-17，本会话继续）
   - 端口监听：`0.0.0.0:5000`（Listen）
   - 应用进程：`python.exe start.py`（PID=`49344`）
   - 结论：可直接进行前端人工验收，无需重复拉起服务。

13. “单次全量刷新立即冲突”根因确认（2026-04-17，本会话继续）
   - 按用户要求继续读取日志与数据库后确认：
     - `distributed_locks` 中存在 `refresh_all_tokens` 有效锁（`owner_id=361421e017704da395890e5543c6aabe`，`expires_at` 尚未到期）
     - `refresh_runs` 中存在遗留 `running` 记录：
       - `id=f2da7e91a4ef43d9ad10b0533d7ea737`
       - `trigger_source=scheduled_manual`
       - `status=running`、`finished_at=NULL`
   - 结论：
     - 用户“单次全量刷新就提示前面有人”是由**遗留运行态锁未释放**导致，而非仅由重复点击触发。
   - 后续处置方向：
     - 先做现场恢复（清理陈旧锁并收尾遗留 run），再继续验证提示体验；
     - 并评估补充代码级自愈，避免 run 异常退出后长时间锁死。

14. 现场恢复执行记录（2026-04-17，本会话继续）
   - 已执行前置备份：
     - `data/outlook_accounts.before_lock_cleanup_20260417_114329.db`
   - 已执行恢复：
     - 删除 `refresh_all_tokens` 遗留锁（`DELETED_LOCKS=1`）
     - 将遗留 `running` 刷新任务收尾为 `failed`（`UPDATED_RUNS=1`）
   - 恢复后核验：
     - `distributed_locks` 中 `refresh_all_tokens` 已清空（`AFTER_LOCKS=0`）
     - 目标 run（`f2da7e91a4ef43d9ad10b0533d7ea737`）已变更为：
       - `status=failed`
       - `finished_at=2026-04-17 03:44:30`
       - `message=Recovered after stale running lock cleanup`

15. 风险补充（TTL 导致卡锁窗口较长）
   - 当前环境测得：
     - `refresh_delay_seconds=5`
     - 可刷新 Outlook 活跃账号约 `101`
   - 计算得到锁 TTL 约 `7200s`（120 分钟，上限策略生效）。
   - 这解释了为何一旦 run 异常中断，用户会较长时间持续命中 `REFRESH_CONFLICT`。

16. 本次用户触发后的实时后台跟踪（2026-04-17，本会话继续）
   - 在用户“已开始全量刷新”后即时读取数据库状态：
     - `distributed_locks`：存在当前有效锁（`owner_id=cb396ea3e1e1400c9bae1bf8546e7902`）
     - 最新 `refresh_runs`：
       - `id=9e56581aef1544168d254b1a32cedb59`
       - `trigger_source=scheduled_manual`
       - `status=running`
       - `total=101`
   - 同时 `account_refresh_logs` 最新记录显示：
     - 同一 `run_id=9e56581aef1544168d254b1a32cedb59` 持续写入 `scheduled + success`
   - 结论：
     - 本次并非“单次触发立即冲突失败”，而是任务已真实执行中；
     - 执行中的互斥锁会让并发刷新请求命中冲突提示，属于预期行为。

17. 全量自动化回归（2026-04-17，本会话继续）
   - 执行：`python -m unittest discover -v`（timeout=300000ms）
   - 结果：
     - `Ran 1194 tests in 290.291s`
     - `OK (skipped=7)`
   - 结论：
     - 本会话关于刷新冲突/权限提示/现场恢复相关改动未引入新的全量回归失败。

18. 验收进行中实时观察（2026-04-17，本会话继续）
   - 用户继续点测期间，后台状态显示：
     - `refresh_runs` 当前 `scheduled_manual` run 仍为 `running`（`total=101`）
     - `distributed_locks` 对应锁正常持有（运行中互斥）
   - `account_refresh_logs` 最新 15 条均为：
     - `refresh_type=scheduled`
     - `status=success`
     - `run_id` 与当前运行任务一致
   - 结论：
     - 当前验收过程中的全量刷新链路在持续成功推进，未再出现“点击即失败”的异常现象。

19. 验收完成态快照（2026-04-17，本会话继续）
   - 目标 run：`9e56581aef1544168d254b1a32cedb59`
   - 完成状态：
     - `status=completed`
     - `total=101`
     - `success_count=100`
     - `failed_count=1`
     - `message=完成：成功 100，失败 1`
   - 锁状态：
     - 刷新结束后 `refresh_all_tokens` 锁已释放（`LOCK_EXISTS=False`）
   - 单失败明细：
     - 账号：`MistyBaker7602@hotmail.com`
     - 错误：`SSLError(SSLEOFError ... UNEXPECTED_EOF_WHILE_READING)`
   - 结论：
     - 刷新链路本身闭环正常（可启动、可执行、可收尾、可释放锁）；
     - 单失败归因为外部网络/SSL 波动，不属于本 BUG 的“卡死/提示不清晰”主链路回归。

20. 单失败账号复盘（2026-04-17，本会话继续）
   - 失败账号：`MistyBaker7602@hotmail.com`（`account_id=226`）
   - 失败错误：
     - `HTTPSConnectionPool ... SSLError(SSLEOFError ... UNEXPECTED_EOF_WHILE_READING)`
   - 账号上下文：
     - `provider=outlook`、`account_type=outlook`、`status=active`
     - 所属分组 `group_id=1`，`proxy_url=null`（非代理分组导致）
   - 历史分布：
     - 当前库内 `scheduled + failed` 仅此 1 条（`fail_count=1`）
   - 结论：
     - 该失败更符合外部 TLS/网络瞬时异常的单点事件，暂无系统性回归迹象。

21. 单账号重试验证阻塞点（2026-04-17，本会话继续）
   - 按用户要求尝试对失败账号 `MistyBaker7602@hotmail.com`（id=226）执行单独重试验证。
   - 脚本态调用受限于登录态：
     - `POST /login`（password=`12345678`）返回 `401 LOGIN_INVALID_PASSWORD`
     - 随后 `POST /api/accounts/226/retry-refresh` 返回 `401 AUTH_REQUIRED`
   - 结论：
     - 当前验收环境登录口令已非默认值，导致脚本无法直接代用户触发重试。
   - 后续可行方案：
     - 由用户在已登录前端手工点击“重试该账号”，我后台同步抓取日志结果；
     - 或提供当前口令后继续脚本化验证。

22. 分支同步状态（2026-04-17，本会话继续）
    - 已按用户要求执行推送：`git push origin Buggithubissue`
    - 远端更新：`772d540..402c04a`（`Buggithubissue -> Buggithubissue`）
    - 当前本地与远端分支已对齐。

23. 本地 `main` 合并后回归状态补充（2026-04-17，本会话继续）
    - 当前 `main` 最近提交确认：
      - `3c08745 merge: integrate Buggithubissue into main`
    - 已在 `main` 执行全量命令：
      - `python -m unittest discover -v`（timeout=300000ms）
    - 结果：本轮因超时中断，未输出最终 unittest 汇总行（无 `Ran X tests ...` / `OK` / `FAILED`）。
    - 说明：目前不能据此宣称“main 合并后全量已通过”；会按分批方案继续完成回归闭环。

24. 本地 `main` 分批全量回归结果（2026-04-17，本会话继续）
    - 按 4 分片执行（每批 timeout=300000ms）后结果：
      - 分片1：`Ran 303 tests in 189.896s`，`OK`
      - 分片2：`Ran 266 tests in 47.230s`，`OK`
      - 分片3：`Ran 273 tests in 43.359s`，`OK (skipped=7)`
      - 分片4：`Ran 352 tests in 82.976s`，`OK`
    - 结论：
      - `main` 合并后的全量回归已在分批模式下完成，未发现 FAIL/ERROR。

25. 人工验收容器重建状态（2026-04-17，本会话继续）
    - 按用户要求执行“本地构建 + 启动 + 人工验收”，并选择复用 `5002` 端口。
    - 已执行：
      - 停止并删除旧容器 `outlook-email-plus-local-main`
      - 本地重构建镜像：`ghcr.io/zeropointsix/outlook-email-plus:local-main-20260417`
      - 使用隔离数据目录重新启动同名容器并映射 `5002->5000`
    - 启动后核验：
      - 容器状态：`Up ... (healthy)`
      - 健康检查：`GET http://127.0.0.1:5002/healthz` 返回
        - `{"boot_id":"1776406310777-7","status":"ok","version":"1.18.0"}`
    - 当前人工验收地址：`http://127.0.0.1:5002`

26. 人工验收结果（2026-04-17，本会话继续）
    - 用户已确认：`验收通过了`
    - 结论：
      - `main` 合并后的分批全量回归结果与本地 Docker 人工点测结果一致，当前未观察到与本 BUG 相关的新增回归问题。

27. 发布后 CI 门禁补充（2026-04-17，本会话继续）
    - 在 `v1.19.0` 发布后巡检发现：远端 `Code Quality / Build and Push Docker Image` 在 formatter gate 失败。
    - 失败根因：`Run Black (Code Formatter Check)`。
    - 已按远端日志对以下文件执行 Black 格式化并本地复核通过：
      - `outlook_web/services/refresh.py`
      - `tests/test_refresh_outlook_only.py`
      - `tests/test_refresh_selected_issue45.py`
      - `tests/test_frontend_account_type_and_refresh_suggestions_contract.py`
    - 本地复核结果：
      - `black --check` 通过
      - `isort --check-only` 通过
      - 相关定向 unittest：`Ran 20 tests ... OK`
    - 随后已推送触发新一轮 CI，当前以该轮远端结果为准。
