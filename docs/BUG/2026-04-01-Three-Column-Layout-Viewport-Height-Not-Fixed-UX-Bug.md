# BUG 记录

## 基本信息

- 记录日期：2026-04-01
- 状态：待修复
- 优先级：P1（中高优先级）
- 主题：三栏布局高度不固定，整个页面可无限下滑（UX 体验问题）
- 来源：内部分析 + 用户反馈（Issue #22、#24 讨论中发现）
- 相关 Issue：https://github.com/ZeroPointSix/outlookEmailPlus/issues/24

---

## 问题描述

### 用户反馈

> "前端不是固定的用户展开的长度，而是我们的账号数量的长度，不断下滑，就会显得非常奇怪，只要有这个东西就会一直下滑下去，最好我们的三栏的下滑款都应该是独立自主的。"

### 预期效果（标准邮件客户端布局）

```
┌──────────────────────────────────────────────────────┐
│  Topbar（固定高度，不滚动）                              │
├────────┬──────────────┬──────────────────────────────┤
│        │ 账号列表      │ 邮件列表                      │
│ 分组   │（独立内滚）   │（独立内滚）                    │
│ 列表   │              │                               │
│（独立  │              ├──────────────────────────────┤
│ 内滚） │              │ 邮件详情                      │
│        │              │（独立内滚）                    │
└────────┴──────────────┴──────────────────────────────┘
         ↑ 三栏总高度 = 100vh - Topbar高度，不溢出
```

**三栏的每一栏都固定在视口内，账号再多、邮件再长，整个浏览器页面都不应该出现滚动条。只有各栏内部自己滚动。**

### 当前问题

| 场景 | 表现 |
|------|------|
| 账号较多（桌面端） | `min-height: 100vh` 允许页面随内容撑高，整个浏览器可以上下滚动 |
| 移动端（屏幕宽度 ≤ 768px） | workspace 高度改为 `height: auto`，三栏竖向堆叠，页面高度无限延伸 |
| 邮件详情 iframe 内容长 | iframe 动态高度设置超过容器高度，可能引发外层布局膨胀 |

---

## 根本原因分析

### 桌面端根因：`body` 和 `#app` 使用了 `min-height` 而非 `height`

**文件：** `static/css/main.css`

**问题代码（第 54–58 行、第 72 行）：**
```css
body {
  min-height: 100vh;   /* ← min-height，允许被内容撑高 */
  ...
}
#app { display: flex; min-height: 100vh; }   /* ← 同样是 min-height */
```

**问题链路：**
```
body { min-height: 100vh }
  └── #app { min-height: 100vh }
        └── .content { flex: 1 }          ← 高度跟随 #app
              ├── .topbar { flex-shrink: 0; height: ~52px }
              └── .page.page-workspace { flex: 1; overflow: hidden }
                    └── #page-mailbox { display: flex; min-height: 0 }
                          └── .workspace.workspace-mailbox {
                                height: calc(100vh - 52px)   ← 固定高度 ✅
                              }
```

当 `#app` 的 `min-height: 100vh` 被某些内容撑高到 100vh 以上时（如仪表盘、Modal、Toast 等），`.content` 随之变高，`.page-workspace` 的 `flex: 1` 高度超过 `100vh - 52px`，整个布局失去视口约束，页面产生整体滚动条。

---

### 移动端根因：workspace 高度被重置为 `auto`（严重）

**文件：** `static/css/main.css`

**问题代码（第 1384–1404 行）：**
```css
@media (max-width: 768px) {
  .workspace.workspace-mailbox,
  .workspace.workspace-temp-emails {
    flex-direction: column;
    height: auto;   /* ← ❌ 完全移除了固定高度！三栏变成自然流布局 */
  }
  
  .accounts-column {
    width: 100%; height: auto; max-height: 300px;
    /* ↑ height: auto + max-height 300px：只有最大高度限制，实际不固定 */
  }
  
  .emails-column {
    width: 100%;
    /* ↑ ❌ 完全没有高度限制！随邮件数量无限增长 */
  }
}
```

**问题链路：**
```
移动端用户打开邮件管理页面
  → workspace 变为竖向堆叠 flex-direction: column, height: auto
  → groups-column: max-height 200px  ← 部分限制 ✅
  → accounts-column: max-height 300px ← 部分限制 ✅
  → emails-column: 无高度限制 ← ❌ 随邮件数量无限延伸
  → 整个页面高度 = 200 + 300 + 邮件数 × 邮件行高（无上限）
  → 浏览器出现整体页面滚动条，用户可以无限下滑
```

---

### 附带问题：`emailDetailSection` 和 `emailList` 同列竖排，`flex: 1` 平分高度

（已在 Issue #24 的 Bug 文档中详细记录）

当邮件详情展开时，`.emails-column` 内两个 `flex: 1` 的元素平分高度，邮件列表被压缩到 50%，邮件详情也只有 50%。这不符合用户预期的"独立分区，各自管理自己的滚动"。

---

## 修复方案

### 方案一（必须）：桌面端 —— 限制根元素高度，防止整体页面滚动

**文件：** `static/css/main.css`

**当前代码：**
```css
html { font-size: 15px; scroll-behavior: smooth; }
body {
  ...
  min-height: 100vh;
}
#app { display: flex; min-height: 100vh; }
```

**修改方案：**
```css
html, body {
  height: 100%;
  overflow: hidden;   /* 禁止整体页面滚动 */
}
body {
  ...
  /* min-height: 100vh 改为 height: 100vh */
}
#app {
  display: flex;
  height: 100vh;      /* 改为固定高度 */
  overflow: hidden;
}
```

**注意：** 修改后，非 workspace 页面（如仪表盘、设置）的 `.page { flex: 1; overflow-y: auto; }` 仍然可以在自己的区域内滚动，不受影响。Modal 等绝对定位元素也不会撑高页面。

---

### 方案二（必须）：移动端 —— 给 `emails-column` 添加高度限制

**文件：** `static/css/main.css`

**当前代码（第 1400–1404 行）：**
```css
.workspace.workspace-mailbox .workspace-panel.emails-column,
.workspace.workspace-temp-emails .workspace-panel.emails-column,
.emails-column {
  width: 100%;
  /* ← 没有高度限制 */
}
```

**修改方案（方案 A：给 emails-column 添加最小高度和固定计算高度）：**
```css
/* 移动端：分组栏约 200px + 账号栏约 300px + topbar 52px */
.workspace.workspace-mailbox .workspace-panel.emails-column,
.emails-column {
  width: 100%;
  min-height: 300px;
  /* 可选：限制 emails-column 不超过可用高度 */
  max-height: calc(100vh - 52px - 200px - 300px);  /* 视口 - topbar - 分组 - 账号 */
  overflow-y: auto;
}
```

**修改方案（方案 B：移动端全屏单栏模式——推荐）：**
将移动端改为类似微信邮件客户端的"按需全屏展示"模式：
- 默认只显示账号列表（全屏）
- 点击账号后，全屏切换到邮件列表
- 点击邮件后，全屏切换到邮件详情
- 各页面固定高度，无整体滚动

---

### 方案三（建议）：邮件详情从 `emails-column` 内移出，成为第三独立面板

（详见 `2026-04-01-Email-Click-Expand-Active-State-Lost-And-Layout-Bug.md` 中的修复方案三）

将 `#emailDetailSection` 从 `#emailListPanel` 内部移到与 `#emailListPanel` 同级的独立 `#emailDetailPanel`，三列改为真正的四列（分组 / 账号 / 邮件列表 / 邮件详情）或三列（分组+账号 / 邮件列表 / 邮件详情）。

这样：
- 邮件列表和邮件详情各自独立，互不干扰
- 每列都有自己的固定高度和独立滚动条
- 完全符合"三栏各自独立"的 UX 预期

---

## 修复优先级

| 方案 | 优先级 | 工作量 | 描述 |
|------|--------|--------|------|
| 方案一：html/body/app 高度固定 | P1 | 小（4行 CSS） | 防止桌面端整体页面滚动 |
| 方案二 A：emails-column 添加高度限制 | P1 | 小（3行 CSS） | 快速修复移动端无限延伸 |
| 方案二 B：移动端全屏单栏模式 | P2 | 大 | 较好的移动端 UX，成本高 |
| 方案三：邮件详情独立面板 | P2 | 中 | 结合下次布局重构一起做 |

---

## 相关文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `static/css/main.css` | 54–58 | `body { min-height: 100vh }` |
| `static/css/main.css` | 72 | `#app { min-height: 100vh }` |
| `static/css/main.css` | 291–297 | `.workspace.workspace-mailbox { height: calc(100vh - 52px) }` |
| `static/css/main.css` | 1384–1404 | 移动端响应式：workspace `height: auto`，emails-column 无高度限制 |
| `static/css/main.css` | 963–964 | `#emailDetailSection { flex: 1 }` — 与 emailList 平分高度 |
| `templates/index.html` | 238–267 | emailList 和 emailDetailSection 同列 DOM 结构 |

---

## 关联 Bug

- `2026-04-01-Email-Click-Expand-Active-State-Lost-And-Layout-Bug.md` — 邮件详情与邮件列表同列竖排、active 状态丢失，根因有交叉
