# 验证码提取：空信箱误报 AUTH_EXPIRED（BUG）

**创建日期**: 2026-04-11  
**关联模块**: `outlook_web/controllers/emails.py` — `api_extract_verification()`  
**状态**: 🟢 已修复（2026-04-11）  
**优先级建议**: P1（功能可用性 — 验证码提取核心路径）

---

## 1. 问题概述

当 Outlook 账号满足以下两个条件时，验证码提取接口 `/api/emails/<email>/extract-verification` 返回 **401 ACCOUNT_AUTH_EXPIRED**，但实际授权并未失效：

1. Graph API 返回 401（Token 权限不足或过期）
2. IMAP 连接**成功**但收件箱为空（0 封邮件）

**错误表现**：用户看到"账号授权已失效，请重新授权"，但同一账号的邮件列表刷新（`get_emails`）正常返回 200。

---

## 2. 根因分析

### 2.1 `get_emails` 与 `extract_verification` 的回退逻辑不一致

| 维度 | `get_emails`（正确 ✅） | `extract_verification`（有 Bug ❌） |
|------|------------------------|-----------------------------------|
| IMAP 返回 `success=True` | **立即 return 200**（即使 emails 为空） | 只追加到 `emails` 列表，不算成功 |
| 判断 AUTH_EXPIRED 的前提 | Graph + IMAP New + IMAP Old **全部** `success=False` | `emails` 列表为空 + Graph 曾返回 401 |

### 2.2 Bug 触发路径

```
api_extract_verification()
  ├── Graph inbox → 401 → graph_auth_expired = True
  ├── Graph junk  → 401
  ├── IMAP New    → success=True, emails=[]  ← 连接成功，信箱空
  ├── IMAP Old    → success=True, emails=[]  ← 连接成功，信箱空
  └── if not emails:
        if graph_auth_expired:    ← True（因 Graph 401）
          return AUTH_EXPIRED ❌  ← 误报！IMAP 证明 Token 有效
```

### 2.3 为什么是"老 Bug"

1. **触发条件苛刻**：需要 Graph 返回 401 + 收件箱确实为空，两者同时成立
2. **大部分测试场景被掩盖**：测试账号通常有邮件，不会走到 `if not emails` 分支
3. **`get_emails` 不受影响**：IMAP `success=True` 直接返回 200，不检查 `graph_auth_expired`
4. **缺少诊断日志**：无法区分"IMAP 成功但空"和"IMAP 失败"

---

## 3. 诊断日志证据

### 3.1 正常账号（Terrance — 收件箱有 2 封邮件）

```
imap_search | total=2 | skip=0 | top=1 | slice=[1:2]
fetched=1 / requested=1
preferred_channel=imap_new | found=1
→ 总耗时=9401ms | path=preferred_imap_new | success=true
```

### 3.2 问题账号（Jesus — 收件箱为空）

```
imap_search | total=0 (空信箱)
imap_new | success=True | count=0
imap_old | success=True | count=0
邮件收集完毕 | total_emails=0 | graph_success=False | graph_auth_expired=True
→ 返回AUTH_EXPIRED ❌
```

同时 `get_emails` 对同一账号返回 200（IMAP 成功，空列表）。

---

## 4. 修复方案

### 4.1 核心修复

增加 `imap_connected` 标志位，追踪 IMAP 是否成功连接（不论返回邮件数量）：

```python
imap_connected = False

# IMAP New
if imap_new_result.get("success"):
    imap_connected = True
    ...

# IMAP Old
if imap_old_result.get("success"):
    imap_connected = True
    ...

# 最终判断
if not emails:
    if graph_auth_expired and not imap_connected:
        return AUTH_EXPIRED   # Graph 和 IMAP 都失败 → 真正的授权失效
    return EMAIL_NOT_FOUND    # IMAP 成功但无邮件 → 信箱为空
```

### 4.2 附带改进

- **PERF 日志降级为 DEBUG**：通过 `PERF_LOGGING=true` 环境变量控制，生产环境默认不输出
- **IMAP 搜索计数日志**：在 `imap.py` 中增加 `total=N` 和 `fetched=N/M` 日志，便于后续诊断

---

## 5. 影响范围

| 接口 | 影响 |
|------|------|
| `GET /api/emails/<email>/extract-verification` | ✅ 已修复 |
| `POST /api/external/extract-verification` | ⚠️ 同一 controller，同一逻辑，一并修复 |
| `GET /api/emails/<email>` | ❌ 不受影响（无此 Bug） |

---

## 6. 修改文件清单

| 文件 | 变更 |
|------|------|
| `outlook_web/controllers/emails.py` | 增加 `imap_connected` 追踪；PERF 日志 `info` → `debug` |
| `outlook_web/services/imap.py` | 增加 IMAP 搜索/结果诊断日志（DEBUG 级别） |
| `outlook_web/app.py` | 增加 `PERF_LOGGING` 环境变量支持 |
