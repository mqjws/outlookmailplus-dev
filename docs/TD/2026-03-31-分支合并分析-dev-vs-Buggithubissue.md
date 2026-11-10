# 分支合并分析：dev ← Buggithubissue

**日期**：2026-03-31  
**分歧点**：`8854966` (共同祖先)  
**dev 分支**：48 个提交（`8854966..d07eca5`）  
**Buggithubissue 分支**：18 个提交（`8854966..42e230a`）  
**冲突文件数**：40+

---

## 一、两个分支功能清单

### dev 分支独有功能（48 个提交）

| 类别 | 提交 | 功能描述 | 保留? |
|------|------|----------|-------|
| **🔥 轮询系统重构** | `61d56f2..d07eca5`（11 个提交） | 统一轮询引擎 `poll-engine.js`、双模式 UI 回调、pollEnabled OR 兼容、视图切换轮询保持、Toast 防轰炸、分组切换停止轮询 | ✅ 必须保留 |
| **🔥 临时邮箱平台化** | `84c9ef8..75f7f45`（7 个提交） | temp_mail provider 平台化、DB v14→v15→v16 迁移、mailbox resolver、前端 UI、CF Worker 适配、完整测试 | ✅ 必须保留 |
| **认证后前端重构** | `a64943e` | workspace 语义统一、ui_layout_v2 状态管理 | ✅ 已保留 |
| **Compact 模式修复** | `8d51972` | mailbox compact mode 回归修复 | ✅ 已保留 |
| **内部 Pool 移除** | `369f529` | 移除旧内部 pool 路由，统一使用 external pool | ✅ 已保留 |
| **OAuth 注册** | `6843ccc`, `c7bcad1` | OAuth 路由注册、账号备注 PATCH 端点 | ✅ 已保留 |
| **Auth 修复** | `e521461`, `5e8218b` | legacy API key 优先级、auth error contracts | ✅ 已保留 |
| **版本发布** | `926c648` | v1.10.0 发布准备 | ✅ 已保留 |
| **测试** | `7050c50`, `bbee609`, `1d56948`, `d2405a4` | pool 测试隔离、oauth 回归、CSRF 状态清理 | ✅ 已保留 |
| **通知系统** | `c49029d..346cf78` | 统一通知分发、i18n 覆盖 | ✅ 已保留 |
| **v1.9.x** | `aed5b85..a54f86d`（含文档和样式） | v1.9.0 版本、compact 发布、登录密码防护 | ✅ 已保留 |
| **文档** | `cbbd5ef`, `28a722c`, 等 | 轮询方案文档、BUG 记录 | ✅ 已保留 |

### Buggithubissue 分支独有功能（18 个提交）

| 类别 | 提交 | 功能描述 | 保留? |
|------|------|----------|-------|
| **🔥 前端分页** | `42e230a` | 账号列表分页（50/页），groups.js + main.css | ✅ **需要合入** |
| **🔥 Graph API 401 修复** | `3e2a03b` | 401 静默回退修复、Token 轮换持久化、auth_expired 短路、loadDashboard 防抖 | ✅ **需要合入** |
| **CI 修复** | `b43211f` | Docker multi-arch tag trigger、版本号 1.10.1 | ✅ **需要合入** |
| **UI 修复** | `a149236`, `c4bbc3d` | compact 菜单裁剪修复、bug 分析文档 | ⚠️ dev 已有同等修复 `8d51972` |
| **认证后前端重构** | `f9bf6d9` | workspace 语义统一 | ⚠️ dev 已有同等提交 `a64943e` |
| **Pool 移除** | `edf7807` | 移除旧内部 pool 接口 | ⚠️ dev 已有同等提交 `369f529` |
| **Compact 模式修复** | `18effbd` | mailbox compact mode 回归修复 | ⚠️ dev 已有同等提交 `8d51972` |
| **测试/文档** | `58f4f73`, `d9eb443`, `7510a62`, `8476887` | oauth 回归测试、bug 分析文档 | ⚠️ dev 已有同等提交 |
| **杂项** | `0451fe6`, `f40a347`, `686734e`, `b1f398c`, `285a94e` | issue 记录、设计文档、checkpoint | ℹ️ 文档/杂项 |

---

## 二、关键对比分析

### 2.1 必须从 Buggithubissue 合入 dev 的功能

**仅 3 个提交包含 dev 没有的功能代码：**

#### 1. `42e230a` — 前端分页（50 per page）
- **改动文件**：`static/js/features/groups.js`（+55行）、`static/css/main.css`（+47行）
- **功能**：ACCOUNT_PAGE_SIZE=50 常量、分页状态、renderAccountList 切片、翻页按钮、切组/排序/筛选/搜索时重置页码
- **冲突风险**：**高** — `groups.js` 和 `main.css` 在 dev 分支也有大量修改（轮询启动、停止、reapply 逻辑）
- **合并建议**：手动 cherry-pick 或在 dev 的 groups.js 上重新实现分页逻辑

#### 2. `3e2a03b` — Graph API 401 修复
- **改动文件**：`outlook_web/controllers/emails.py`（+300-66行）、`outlook_web/errors.py`（+14行）、`outlook_web/services/graph.py`（+48行）、`static/js/main.js`（+7行）
- **功能**：ACCOUNT_AUTH_EXPIRED 错误码、auth_expired 短路响应、Token 轮换持久化、loadDashboard 防抖
- **冲突风险**：**中** — emails.py 是大改动，但后端代码两边重叠较少；main.js 有冲突
- **合并建议**：cherry-pick 为主，手动解决 main.js 冲突（仅 loadDashboard 防抖）

#### 3. `b43211f` — CI tag trigger
- **改动文件**：`.github/workflows/docker-build-push.yml`（+2行）、`outlook_web/__init__.py`（版本号）
- **功能**：Docker workflow 添加 tag 触发器
- **冲突风险**：**低** — 仅 2 行变更
- **合并建议**：直接 cherry-pick

### 2.2 两边重复功能（dev 已有）

以下功能在两个分支中都独立实现了，dev 版本更新更完整：

| 功能 | Buggithubissue | dev | 保留哪个 |
|------|---------------|-----|---------|
| 认证后前端重构 | `f9bf6d9` | `a64943e` | dev（更新） |
| Compact 模式回归修复 | `18effbd` | `8d51972` | dev（更新） |
| 内部 Pool 移除 | `edf7807` | `369f529` | dev（更新） |
| OAuth 回归测试 | `58f4f73` | `bbee609` | dev（更新） |
| 邮件图片测试 | `d9eb443` | `1d56948` | dev（更新） |
| OAuth/通知回归修复 | `7510a62` | `4fdf7c0` | dev（更新） |

---

## 三、推荐合并策略

### 方案 A（推荐）：Cherry-pick 3 个独有提交

**原理**：dev 分支是主力开发线，Buggithubissue 的大部分功能 dev 都已经有了。只需把 3 个独有提交 cherry-pick 过来。

**步骤**：
1. `git cherry-pick b43211f` — CI tag trigger（冲突极低）
2. `git cherry-pick 3e2a03b` — Graph API 401 修复（中等冲突，主要在 emails.py）
3. `git cherry-pick 42e230a` — 前端分页（高冲突，groups.js/main.css 需手动解决）
4. 全量测试
5. 提交

**优点**：最小改动、风险可控、保留 dev 的完整历史  
**缺点**：cherry-pick 可能有冲突需手动解决

### 方案 B：直接合并 + 解决 40+ 冲突

**原理**：`git merge Buggithubissue` 后手动解决所有冲突。

**优点**：保留完整合并历史  
**缺点**：40+ 文件冲突，大部分是重复功能的冲突（两边独立实现了相同功能），解决工作量大且容易出错

### 方案 C：合并 ours + cherry-pick

**原理**：`git merge -X ours Buggithubissue` 保留 dev 代码为主，然后 cherry-pick 3 个独有提交。

**优点**：记录了合并历史，且独有功能通过 cherry-pick 保证正确  
**缺点**：merge ours 可能丢失 Buggithubissue 的一些文档和小改动

---

## 四、冲突热点文件

以下文件在两个分支都有大量改动，是合并的主要冲突来源：

| 文件 | dev 改动 | Buggithubissue 改动 | 冲突难度 |
|------|----------|---------------------|----------|
| `static/js/main.js` | 轮询设置、标准模式 UI | loadDashboard 防抖 | 🟡 中 |
| `static/js/features/groups.js` | 轮询启动/停止、reapply | 分页逻辑 | 🔴 高 |
| `static/css/main.css` | 轮询指示器样式 | 分页样式 | 🟡 中 |
| `static/js/features/accounts.js` | selectAccount 轮询 | 无独有改动 | 🟢 低 |
| `static/js/features/mailbox_compact.js` | 轮询 UI 适配层 | compact 修复 | 🟡 中 |
| `outlook_web/controllers/emails.py` | 无大改动 | 401 修复大改 | 🟢 低（cherry-pick 即可） |
| `outlook_web/errors.py` | 无大改动 | auth_expired 错误码 | 🟢 低 |
| `outlook_web/services/graph.py` | 无大改动 | token 轮换 | 🟢 低 |
| 后端其他文件 | temp_mail 平台化 | 重复的重构 | 🔴 高（但用 dev 版本即可） |

---

## 五、结论

**推荐方案 A：Cherry-pick 3 个独有提交**

Buggithubissue 分支 18 个提交中，只有 3 个包含 dev 没有的代码功能。其余 15 个要么是文档、要么是 dev 已经独立实现的重复功能。直接 cherry-pick 这 3 个提交是最高效、最安全的策略。
