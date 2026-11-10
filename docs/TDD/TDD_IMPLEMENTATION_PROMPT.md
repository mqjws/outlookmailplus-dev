# 请根据以下 TDD 文档编写完整的测试代码

你是一位熟悉 Python unittest + Flask 测试客户端和 Jest + jsdom 的测试工程师。请根据下方的 TDD（测试设计文档）和 TD（技术设计文档）编写**可直接运行**的测试代码。

## 任务说明

需要编写 3 个测试文件 + 2 个配置文件，共 5 个文件：

| 文件 | 类型 | 用例数 |
|------|------|--------|
| `tests/test_compact_poll_settings.py` | Python unittest（后端 API 契约） | 12 |
| `tests/test_compact_poll_frontend_contract.py` | Python unittest（前端契约） | 14 |
| `tests/compact-poll/jest.config.js` | Jest 配置 | — |
| `tests/compact-poll/setup.js` | Jest 全局 Mock 设置 | — |
| `tests/compact-poll/compact-poll-engine.test.js` | Jest + jsdom（JS 单元） | 22 |

## 关键约束

1. **Python 测试必须与现有测试完全兼容**：使用 `tests._import_app` 模块的 `import_web_app_module()` 和 `clear_login_attempts()`，不要引入新依赖。
2. **Jest 测试必须能独立运行**：所有跨文件依赖（`showToast`、`copyToClipboard`、`syncAccountSummaryToAccountCache` 等）通过 `setup.js` 中的 `global` mock 提供。
3. **轮询引擎代码加载策略**：采用方案 B（`fs.readFileSync` + `eval`），在 `setup.js` 中读取 `static/js/features/mailbox_compact.js`，用正则提取 `// =+ 简洁模式自动轮询` 注释标记之后的所有代码并 `eval` 到全局作用域。这是最实用的方案——直接测试源文件，不需要提取独立模块。
4. **Jest 使用 `jest.useFakeTimers()`**：在 `beforeEach` 中启用 fake timers，`afterEach` 中恢复真实 timers。异步测试使用 `jest.advanceTimersByTimeAsync()`。
5. **测试代码中的中文注释/字符串**：保留中文（与项目现有风格一致），但测试函数名用英文。

## 现有测试模式参考

### Python 测试基类模式（参考 `tests/test_polling_settings.py`）

```python
import unittest
from tests._import_app import clear_login_attempts, import_web_app_module

class CompactPollSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo
            settings_repo.set_setting("enable_compact_auto_poll", "false")
            settings_repo.set_setting("compact_poll_interval", "10")
            settings_repo.set_setting("compact_poll_max_duration", "60")

    def _login(self, client, password="testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))
```

### 前端契约测试基类模式（参考 `tests/test_v191_compact_mode_frontend_contract.py`）

```python
class CompactPollFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password="testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def _get_text(self, client, path):
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()
```

### Jest setup 模式（参考 `tests/layout-system/setup.js`）

```javascript
// 模拟 localStorage
class LocalStorageMock { /* ... */ }
global.localStorage = new LocalStorageMock();
// 模拟 showToast
global.showToast = () => {};
// 模拟 requestAnimationFrame
global.requestAnimationFrame = (callback) => setTimeout(callback, 16);
```

## TDD 文档（完整内容）

以下是测试设计文档的完整内容，包含所有 48 个测试用例的详细描述和代码骨架：

### A 类：后端 Settings API 契约测试（12 用例）

文件：`tests/test_compact_poll_settings.py`

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-A01 | GET 返回默认值 | GET /api/settings 包含 `enable_compact_auto_poll=false`、`compact_poll_interval=10`、`compact_poll_max_duration=60` |
| TC-A02 | PUT + GET 回环 | PUT 保存自定义值后 GET 能读到相同值 |
| TC-A03 | enable 非 bool 拒绝 | 传入 `"yes"` 时 errors 包含"简洁模式自动轮询开关必须是 true 或 false" |
| TC-A04 | interval 范围 3-60 | 2、61 拒绝；3、60 边界通过 |
| TC-A05 | max_duration 范围 10-600 | 9、601 拒绝；10、600 边界通过 |
| TC-A06 | 非数字值拒绝 | `"abc"` 触发"必须是数字"错误 |
| TC-A07 | DB 默认值 | 直接读 settings_repo 返回 "false"/"10"/"60" |
| TC-A08 | 字符串 "false" | PUT `False` 后 GET 返回 `false` |
| TC-A09 | 与标准轮询隔离 | 修改简洁轮询设置后 `polling_interval`、`polling_count` 不变 |
| TC-A10 | 部分字段 | 只传 enable，interval/duration 保持默认 |
| TC-A11 | updated 列表 | PUT 成功后 updated 包含"简洁轮询开关/间隔/时长" |
| TC-A12 | 未登录拒绝 | 未登录 GET 返回非 200 |

### B 类：前端契约测试（14 用例）

文件：`tests/test_compact_poll_frontend_contract.py`

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-B01 | 设置面板元素 | index.html 包含 `id="enableCompactAutoPoll"`、`id="compactPollInterval"`、`id="compactPollMaxDuration"` |
| TC-B02 | i18n 属性 | 设置面板有 `data-i18n="简洁模式自动轮询"`、`data-i18n="复制邮箱后自动监听"`、`data-i18n="轮询间隔"`、`data-i18n="最大监听时长"`、`data-i18n="简洁模式轮询内存提示"` |
| TC-B03 | JS 变量声明 | main.js 包含 `let compactPollEnabled = false;`、`let compactPollInterval = 10;`、`let compactPollMaxDuration = 60;` |
| TC-B04 | applyCompactPollSettings 调用 | main.js 包含 `applyCompactPollSettings` |
| TC-B05 | email-copied 派发 | emails.js 包含 `email-copied` 和 `CustomEvent` |
| TC-B06 | email-copied 监听 | mailbox_compact.js 包含 `addEventListener('email-copied'` |
| TC-B07 | 核心函数声明 | mailbox_compact.js 包含 11 个核心函数声明 |
| TC-B08 | .mail-row 选择器 | mailbox_compact.js 不含 `.compact-account-row`，包含 `.mail-row` |
| TC-B09 | 无 CSS.escape | mailbox_compact.js 不含 `CSS.escape(email)` |
| TC-B10 | i18n 词条完整 | i18n.js 包含 16 个必要的中英文翻译词条 |
| TC-B11 | CSS 类名 | main.css 包含 `.compact-poll-dot`、`.compact-poll-active`、`pulse-dot` |
| TC-B12 | 暗色模式 | main.css 包含 `[data-theme="dark"] .pull-button.compact-poll-active` |
| TC-B13 | Toast 常量 | mailbox_compact.js 包含 `COMPACT_POLL_TOAST_DURATION` 和 `5000` |
| TC-B14 | visibilitychange | mailbox_compact.js 包含 `visibilitychange` 和 `document.hidden` |

### C 类：JS 单元测试（22 用例）

文件：`tests/compact-poll/compact-poll-engine.test.js`

#### 守卫条件（5 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C01 | enabled=false 不触发 | dispatch email-copied 后 compactPollMap.size === 0 |
| TC-C02 | enabled=true + compact 触发 | dispatch 后 compactPollMap.has(email) === true |
| TC-C03 | 非 compact 不触发 | mailboxViewMode='standard' 时不触发 |
| TC-C04 | tempEmailGroup 不触发 | isTempEmailGroup=true 时不触发 |
| TC-C05 | 未知邮箱不触发 | accountsCache 无该邮箱时不触发 |

#### 状态管理（4 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C06 | 同一邮箱重置 | 再次 dispatch 后 startTime 更新 |
| TC-C07 | 多邮箱并行 | 3 个邮箱 dispatch 后 Map.size === 3 |
| TC-C08 | stopCompactAutoPoll | 停止后 Map 无该条目，按钮恢复 |
| TC-C09 | stopAllCompactAutoPolls | 停止后 Map.size === 0 |

#### 超时与错误处理（4 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C10 | 超时自动停止 | maxDuration=5，快进 6s 后 Map 无该条目 + 超时 Toast |
| TC-C11 | 连续 3 次失败停止 | fetch 返回 ok:false 3 次后停止 |
| TC-C12 | 成功后 errorCount 归零 | 2 次失败 + 1 次成功后 errorCount === 0 |
| TC-C13 | 404 自动停止 | fetch 返回 status=404 后停止 + 删除 Toast |

#### 防重入（1 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C14 | isPolling 锁 | fetch 永不 resolve 时，第二次轮询不触发 fetch |

#### 发现新邮件（2 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C15 | 有验证码 | 发现新邮件 → extract-verification 返回 code → copyToClipboard + Toast |
| TC-C16 | 无验证码 fallback | extract-verification 返回 success:false → "发现新邮件" Toast |

#### 设置变更（2 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C17 | enabled=false 停止所有 | applyCompactPollSettings({enabled:false}) 后 Map.size === 0 |
| TC-C18 | interval 重建定时器 | applyCompactPollSettings({interval:5}) 后 timer !== oldTimer |

#### 页面可见性（2 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C19 | hidden 暂停 | 切后台后 timer === null、countdownTimer === null |
| TC-C20 | visible 恢复 | 切回前台后 timer !== null、countdownTimer !== null |

#### DOM 与 UI（2 用例）

| 用例 ID | 名称 | 验证内容 |
|---------|------|---------|
| TC-C21 | findCompactAccountRow | 创建 mail-row DOM 后能找到对应行 |
| TC-C22 | updateCompactPollUI | polling 状态按钮显示"停止监听" + 倒计时；stopped 状态恢复"拉取" |

## TD 关键实现细节（测试需要匹配的代码结构）

### 轮询引擎核心函数签名（mailbox_compact.js 末尾新增）

```javascript
// 状态变量
const compactPollMap = new Map();
let compactPollEnabled = false;
let compactPollInterval = 10;
let compactPollMaxDuration = 60;
let compactPollCountdownTimer = null;
const COMPACT_POLL_TOAST_DURATION = 5000;

// 函数签名
function getCompactAccountByEmail(email) { ... }
function findCompactAccountRow(email) { ... }       // 使用 .mail-row，不使用 CSS.escape
function ensurePollDot(rowElement) { ... }
function updateCompactPollUI(email, state, remaining) { ... }
function startCompactAutoPoll(email, accountId) { ... }
function pollSingleEmail(email) { ... }
function stopCompactAutoPoll(email, silent = false) { ... }
function stopAllCompactAutoPolls() { ... }
function startGlobalCountdown() { ... }
function updateSingleRowFromCache(email) { ... }
function reapplyAllCompactPollUI() { ... }
function applyCompactPollSettings(settings) { ... }
function applyCompactPollSettingsToRunningPolls() { ... }
```

### startCompactAutoPoll 关键行为（影响 TC-C02, TC-C06）

1. **先更新 UI 再拉 baseline**：`compactPollMap.set()` 和 `updateCompactPollUI()` 在 baseline fetch 之前
2. 首次轮询 `pollSingleEmail(email)` 是同步调用（非 setInterval 等待）
3. 重复触发同一邮箱时先 `stopCompactAutoPoll(email, true)` 再重新启动

### pollSingleEmail 关键行为（影响 TC-C10~C16）

1. 防重入：`if (state.isPolling) return;`
2. 超时检查：`elapsed >= compactPollMaxDuration` 时调用 `stopCompactAutoPoll(email)`
3. 404 检查：`result.value.status === 404` 时停止
4. 失败计数：`!hasSuccess` 时 `errorCount++`，`errorCount >= 3` 时停止；成功后 `errorCount = 0`
5. 发现新邮件后调用 `/api/emails/{email}/extract-verification`
6. 所有轮询 Toast 传入 `COMPACT_POLL_TOAST_DURATION`（5000）
7. `finally` 中检查 `compactPollMap.has(email)` 再重置 `isPolling`

### visibilitychange 关键行为（影响 TC-C19, TC-C20）

- hidden 时：清空 `state.timer = null`，清空 `compactPollCountdownTimer = null`
- visible 时：检查超时、立即 `pollSingleEmail`、恢复定时器

### Mock DOM 结构（影响 TC-C21, TC-C22）

```javascript
// 创建模拟邮箱行 DOM
function createMockMailRow(email, accountId) {
  const row = document.createElement('div');
  row.className = 'mail-row';

  const mailCard = document.createElement('div');
  mailCard.className = 'mail-card';

  const button = document.createElement('div');
  button.className = 'mail-card-button';

  const pullBtn = document.createElement('button');
  pullBtn.className = 'pull-button';
  pullBtn.textContent = '拉取';
  pullBtn.setAttribute('onclick', `refreshCompactAccount(${accountId}, this)`);

  button.appendChild(pullBtn);
  mailCard.appendChild(button);
  row.appendChild(mailCard);
  document.body.appendChild(row);
  return row;
}
```

### 后端 settings.py 校验规则（影响 TC-A03~A06）

- `enable_compact_auto_poll`：`str(val).lower()` 必须是 `"true"` 或 `"false"`
- `compact_poll_interval`：`int()` 转换，范围 3-60，非数字报"简洁模式轮询间隔必须是数字"
- `compact_poll_max_duration`：`int()` 转换，范围 10-600，非数字报"最大监听时长必须是数字"
- PUT 返回的 `updated` 列表包含："简洁轮询开关"、"简洁轮询间隔"、"简洁轮询时长"
- PUT 返回的 `errors` 列表包含具体的中文错误消息

## 输出要求

请按以下格式输出**每个文件的完整代码**：

```
### 文件 1：tests/test_compact_poll_settings.py

```python
# 完整可运行的 Python 测试代码
...
```

### 文件 2：tests/test_compact_poll_frontend_contract.py

```python
# 完整可运行的 Python 测试代码
...
```

### 文件 3：tests/compact-poll/jest.config.js

```javascript
// 完整的 Jest 配置
...
```

### 文件 4：tests/compact-poll/setup.js

```javascript
// 完整的 setup 代码（含 fs.readFileSync + eval 加载轮询引擎）
...
```

### 文件 5：tests/compact-poll/compact-poll-engine.test.js

```javascript
// 完整可运行的 Jest 测试代码
...
```
```

## 额外注意事项

1. **Python 测试**：不需要 `if __name__ == '__main__'` 块，通过 `python -m unittest discover -s tests -v` 运行。
2. **Jest 测试**：每个 test 使用 `jest.clearAllMocks()` 或在 `beforeEach` 中清理。使用 `jest.useFakeTimers()` 和 `jest.advanceTimersByTimeAsync()`。
3. **setup.js 中的 eval 加载**：需要同时 eval 轮询引擎依赖的 `mailbox_compact.js` 前半部分代码（至少包含 `getCompactVisibleAccounts`、`translateCompactText`、`renderCompactAccountList`、`refreshCompactAccount` 等函数声明），否则轮询引擎中的 `getCompactAccountByEmail` 和 `translateCompactText` 会报 ReferenceError。建议 eval 整个 `mailbox_compact.js` 文件。
4. **fetch mock**：TC-C14 中 fetch 返回 `new Promise(() => {})`（永不 resolve）来模拟慢请求，此时 fake timers 下需要确保 `pollSingleEmail` 不会在第一次未完成时再次触发。
5. **document.hidden mock**：TC-C19/TC-C20 中使用 `Object.defineProperty(document, 'hidden', { value: true, configurable: true })` 来模拟页面隐藏/显示。
6. **不要修改任何源文件**，只编写测试文件。
7. **不要省略任何用例**，TDD 中列出的 48 个用例（12+14+22）必须全部实现。
