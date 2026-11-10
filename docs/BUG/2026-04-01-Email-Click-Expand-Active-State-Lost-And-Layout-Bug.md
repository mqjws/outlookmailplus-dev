# BUG 记录

## 基本信息

- 记录日期：2026-04-01
- 状态：待修复
- 优先级：P0（高优先级）
- 主题：点击邮件无法展开内容 / 展开后 active 高亮丢失 / 无限滚动频繁触发
- 来源：GitHub Issue #24
- 提出者：@africa1207
- Issue 链接：https://github.com/ZeroPointSix/outlookEmailPlus/issues/24
- Owner 回复：「前端重写带来的问题，已经开始优化了」

---

## 问题描述

### 用户反馈

> "点击邮件无法展开内容，同时获取邮件和点击邮件获取内容较慢"

**补充评论（@yushangcl）：**
> "点击能展开邮件内容，在最下面，但是往下滑的时候会加载后续的邮件，导致邮件详情一直往下"

### 表现症状归纳

| 症状 | 严重程度 |
|------|----------|
| 点击邮件后，邮件详情出现在列表下方（不在视口内，需滚动） | 高 |
| 在邮件列表区域向下滚动时，触发"加载更多"，邮件列表重渲染后 active 高亮消失 | 高 |
| 用户感觉"邮件详情一直往下"，找不到已选中的邮件 | 高 |
| 无限滚动在邮件详情展开后更容易被频繁触发 | 中 |

---

## 根本原因分析（三个相互关联的缺陷）

### 缺陷一：renderEmailList 重渲染时未保留 active 状态

**定位：**
- `static/js/features/emails.js` 第 267–270 行（`selectEmail`）
- `static/js/features/emails.js` 第 131–169 行（`renderEmailList`）
- `static/js/main.js` 第 1017 行（`loadMoreEmails` 中调用 `renderEmailList`）

**代码片段（emails.js:267–270）：**
```javascript
async function selectEmail(messageId, index) {
    document.querySelectorAll('.email-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);  // 通过 index 设置 active
    });
    ...
}
```

**代码片段（emails.js:131–166）：**
```javascript
function renderEmailList(emails) {
    container.innerHTML = emails.map((email, index) => {
        return `
        <div class="email-item ${email.is_read === false ? 'unread' : ''}"
             onclick="${clickHandler}('${email.id}', ${index})">
        ...
        </div>
    `}).join('');
    // ❌ 没有判断 currentEmailDetail?.id，active 状态完全丢失
}
```

**代码片段（main.js:1016–1017）：**
```javascript
// 加载更多完成后重新渲染整个列表
renderEmailList(currentEmails);  // ❌ 这里触发了 active 状态丢失
```

**问题链路：**
```
用户点击邮件 → selectEmail(id, index) → 给 index 位置的 .email-item 加 active 类
     ↓
用户在邮件列表向下滚动
     ↓
initEmailListScroll 监听器触发 loadMoreEmails()
     ↓
API 返回新邮件 → currentEmails.concat(data.emails)
     ↓
renderEmailList(currentEmails)  ← 完全重写 container.innerHTML
     ↓
所有 .email-item 重新生成，没有 active 类 ← ❌ 用户看到高亮消失
```

---

### 缺陷二：邮件详情与邮件列表同列竖排，详情出现在视口外

**定位：**
- `templates/index.html` 第 218–267 行（HTML 结构）
- `static/css/main.css` 第 312–313 行（`.emails-column`）
- `static/css/main.css` 第 348 行（`.column-body`）
- `static/css/main.css` 第 963–964 行（`#emailDetailSection`）

**HTML 结构：**
```html
<!-- emails-column：flex 列容器 -->
<div class="workspace-panel emails-column" id="emailListPanel">
    
    <!-- ① 邮件列表 —— flex: 1; overflow-y: auto -->
    <div class="column-body" id="emailList">
        ...（邮件条目）...
    </div>
    
    <!-- ② 邮件详情 —— 默认 display:none，flex: 1 -->
    <div id="emailDetailSection" style="display:none;">
        <div id="emailDetailToolbar">...</div>
        <div id="emailDetail"></div>
    </div>
    
</div>
```

**关键 CSS：**
```css
.emails-column {
    flex: 1; display: flex; flex-direction: column;  /* 竖向 flex 容器 */
    overflow: hidden;
}
.column-body { flex: 1; overflow-y: auto; }          /* #emailList：弹性占满 */

#emailDetailSection {
    flex: 1; display: flex; flex-direction: column;  /* 详情区：同样 flex:1 */
    min-height: 0; overflow: hidden;
}
```

**问题链路：**
```
初始状态：
  emailListPanel（高度 100%）
      └── emailList（flex:1 → 占 100% 高度）
      └── emailDetailSection（display:none → 不占空间）

点击邮件后（showEmailDetailSection）：
  emailListPanel（高度 100%）
      └── emailList（flex:1 → 各占 50% 高度）  ← ❌ 邮件列表被压缩到一半
      └── emailDetailSection（flex:1 → 各占 50%，显示在下方）  ← ❌ 用户看不到
```

**表现：**
- 邮件详情出现在列表下方，需要滚动才能看到（"邮件内容在最下面"）
- 邮件列表可见区域被压缩到 50%，高度更小，内部 overflow 滚动更容易触发底部检测

---

### 缺陷三：无限滚动在详情展开后更容易被频繁触发

**定位：**
- `static/js/main.js` 第 966–975 行（`initEmailListScroll`）

**代码片段：**
```javascript
function initEmailListScroll() {
    const emailList = document.getElementById('emailList');
    emailList.addEventListener('scroll', function () {
        if (emailList.scrollHeight - emailList.scrollTop <= emailList.clientHeight + 50) {
            if (!isLoadingMore && hasMoreEmails && currentAccount && !isTempEmailGroup) {
                loadMoreEmails();
            }
        }
    });
}
```

**问题联动：**
```
缺陷二导致 emailList 高度被压缩到约 50%
    ↓
emailList.clientHeight 减小
    ↓
触发条件 (scrollHeight - scrollTop <= clientHeight + 50) 更容易满足
    ↓
用户轻微滚动即触发 loadMoreEmails()
    ↓
loadMoreEmails() 调用 renderEmailList() → 缺陷一：active 状态再次丢失
```

---

## 复现步骤

1. 打开应用，登录
2. 选择一个有 20 封以上邮件的邮箱账号，点击「获取邮件」
3. 等待邮件列表加载完成
4. 点击列表中任意一封邮件
5. **观察**：邮件详情出现在列表下方（而不是独立面板），被选中的邮件条目有蓝色高亮
6. 在邮件列表区域（上方列表）向下滚动
7. **观察**：
   - 触发"加载更多"API 请求
   - 请求完成后，整个邮件列表重新渲染
   - 步骤 4 选中的邮件的蓝色高亮消失（active 丢失）
   - 用户无法直观判断哪封邮件正在被查看

---

## 影响范围

| 维度 | 描述 |
|------|------|
| 受影响功能 | 邮件查看核心功能 |
| 受影响版本 | 1.10.0（前端重写版本起） |
| 严重程度 | 高——邮件展开体验是核心用户流程 |
| 是否影响数据 | 否（纯 UI 问题） |

---

## 修复方案

### 方案一（必须修复）：renderEmailList 保留 active 状态

**文件：** `static/js/features/emails.js`

**修改位置：** `renderEmailList` 函数，生成 `.email-item` 时，根据 `currentEmailDetail?.id` 判断是否加 `active` 类。

```javascript
function renderEmailList(emails) {
    const container = document.getElementById('emailList');
    // ...
    const currentActiveId = currentEmailDetail ? currentEmailDetail.id : null;

    container.innerHTML = emails.map((email, index) => {
        const isActive = currentActiveId && email.id === currentActiveId;
        return `
        <div class="email-item ${email.is_read === false ? 'unread' : ''} ${isActive ? 'active' : ''}"
             onclick="${clickHandler}('${email.id}', ${index})">
        ...
        </div>
    `}).join('');
    // ...
}
```

**影响：** 最小化改动，只在 `renderEmailList` 中增加一个 active 判断，完全向后兼容。

---

### 方案二（必须修复）：loadMoreEmails 改为追加 DOM，不整体重渲染

**文件：** `static/js/main.js`

**修改位置：** `loadMoreEmails` 函数中的渲染逻辑。

**当前代码（第 1016–1017 行）：**
```javascript
// 重新渲染邮件列表  ← 全量重渲染，丢失 active 状态
renderEmailList(currentEmails);
```

**修改为：**
```javascript
// 仅追加新邮件到列表末尾，保留已有 DOM（包括 active 状态）
const newEmails = data.emails;
const appendHtml = newEmails.map((email, i) => {
    const index = currentEmails.length - newEmails.length + i;
    const clickHandler = isTempEmailGroup ? 'getTempEmailDetail' : 'selectEmail';
    const initial = (email.from || '?')[0].toUpperCase();
    return `
    <div class="email-item ${email.is_read === false ? 'unread' : ''}"
         onclick="${clickHandler}('${email.id}', ${index})">
        ...（与 renderEmailList 相同的模板）...
    </div>`;
}).join('');
emailList.insertAdjacentHTML('beforeend', appendHtml);
```

**注意：** 追加方案需要确保 index 正确（相对于整个 currentEmails 数组的位置）。

---

### 方案三（建议修复）：将邮件详情区域移为独立第三列

**文件：** `templates/index.html` + `static/css/main.css`

**当前布局（有问题）：**
```
[账号列表 | 邮件列表 + 邮件详情（同列竖排）]
```

**建议布局：**
```
[账号列表 | 邮件列表 | 邮件详情（独立第三列）]
```

将 `#emailDetailSection` 从 `#emailListPanel` 内部移出，作为与 `#emailListPanel` 同级的独立面板。这样：
- 邮件列表不再被压缩
- 邮件详情在右侧独立显示（符合常见邮件客户端 UX，如 Outlook、Gmail 三栏布局）
- `emailList` 的 `overflow-y: auto` 触发条件不受影响

**关于移动端：** 可保留当前"列表 + 详情同列"的方式（适合小屏幕），通过媒体查询区分：
```css
/* 桌面端：三列布局 */
@media (min-width: 768px) {
    #emailDetailSection { /* 独立第三列 */ }
}

/* 移动端：保持原有同列竖排，点击后自动滚动到详情 */
@media (max-width: 767px) {
    /* 当前行为 */
}
```

---

## 修复优先级

| 方案 | 优先级 | 工作量 | 描述 |
|------|--------|--------|------|
| 方案一：renderEmailList 保留 active | P0 | 小（5行代码） | 立即修复，消除核心体验 Bug |
| 方案二：loadMoreEmails 追加而非重渲染 | P0 | 中（重构追加逻辑） | 同步修复，避免不必要的全量重渲染 |
| 方案三：独立第三列布局 | P1 | 大（布局重构） | 结合下次布局迭代一起做 |

---

## 相关文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `static/js/features/emails.js` | 131–169 | `renderEmailList`：未保留 active |
| `static/js/features/emails.js` | 267–270 | `selectEmail`：通过 index 设 active |
| `static/js/main.js` | 966–975 | `initEmailListScroll`：滚动监听与触发 |
| `static/js/main.js` | 979–1038 | `loadMoreEmails`：全量重渲染触发点 |
| `templates/index.html` | 238–267 | DOM 结构：emailList 和 emailDetailSection 同列 |
| `static/css/main.css` | 963–964 | `#emailDetailSection { flex: 1 }` |
| `static/css/main.css` | 348 | `.column-body { flex: 1; overflow-y: auto }` |

---

## 附录：Owner 确认

来自 Issue #24 评论（@ZeroPointSix）：
> "前端重写带来的问题，已经开始优化了，至于获取邮件过慢可能是网络波动的原因"

这确认了该 Bug 是前端重写引入的布局与状态管理问题，与后端无关。
