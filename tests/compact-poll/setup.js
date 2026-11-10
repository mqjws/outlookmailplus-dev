/**
 * tests/compact-poll/setup.js — Jest 全局 Mock 设置
 *
 * 职责：
 *   1. 声明所有跨文件依赖的 Mock 函数（showToast、copyToClipboard 等）
 *   2. 设置 mailbox_compact.js 运行所需的全局变量（main.js 提供的部分）
 *   3. 使用方案 B（fs.readFileSync + eval）加载整个 mailbox_compact.js：
 *      - 将 let/const 转换为 var，使轮询引擎的状态变量可在测试中直接访问
 *      - 使用间接 eval，在全局作用域执行（var 变量挂载到 global）
 *   4. 在 eval 之后 override 需要被 Mock 的函数
 *   5. beforeEach / afterEach 钩子：重置状态
 *
 * 注意（RED 阶段）：
 *   mailbox_compact.js 尚未实现轮询引擎，eval 后全局中不存在
 *   compactPollMap、startCompactAutoPoll 等符号。
 *   此时所有 C 类测试预期失败（ReferenceError），这是 TDD 红灯阶段的正常现象。
 *   GREEN 阶段实现轮询引擎后，所有测试应通过。
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ══════════════════════════════════════════════════════════════════════════
// 1. 声明 Mock 函数（模块级，供 beforeEach 中重置 implementation 使用）
// ══════════════════════════════════════════════════════════════════════════

const mockShowToast                       = jest.fn();
const mockCopyToClipboard                 = jest.fn().mockResolvedValue(undefined);
const mockSyncAccountSummaryToAccountCache = jest.fn();
const mockGetCompactVisibleAccounts       = jest.fn().mockReturnValue([]);
const mockRefreshCompactAccount           = jest.fn();
const mockEscapeHtml                      = jest.fn((text) => String(text == null ? '' : text));
const mockHandleAccountSelectionChange    = jest.fn();
const mockUpdateBatchActionBar            = jest.fn();
const mockUpdateSelectAllCheckbox         = jest.fn();
const mockUpdateTopbar                    = jest.fn();
const mockRenderAccountList               = jest.fn();
const mockSelectGroup                     = jest.fn();
const mockCopyVerificationInfo            = jest.fn();
const mockShowEditAccountModal            = jest.fn();
const mockShowEditRemarkOnly              = jest.fn();
const mockDeleteAccount                   = jest.fn();
const mockShowBatchTagModal               = jest.fn();
const mockShowBatchMoveGroupModal         = jest.fn();
const mockCopyEmail                       = jest.fn();

// ══════════════════════════════════════════════════════════════════════════
// 2. 浏览器 API Mock
// ══════════════════════════════════════════════════════════════════════════

global.CSS = { escape: (s) => String(s) };

// localStorage Mock
class LocalStorageMock {
  constructor() { this.store = {}; }
  getItem(key)         { return Object.prototype.hasOwnProperty.call(this.store, key) ? this.store[key] : null; }
  setItem(key, value)  { this.store[key] = String(value); }
  removeItem(key)      { delete this.store[key]; }
  clear()              { this.store = {}; }
  get length()         { return Object.keys(this.store).length; }
  key(index)           { return Object.keys(this.store)[index] || null; }
}
global.localStorage = new LocalStorageMock();
try {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: global.localStorage });
} catch (_) { /* jsdom 可能已设置 */ }

// ══════════════════════════════════════════════════════════════════════════
// 3. main.js 提供的全局状态变量（eval 前设置，mailbox_compact.js 依赖这些变量）
// ══════════════════════════════════════════════════════════════════════════

global.accountsCache      = {};
global.currentGroupId     = 1;
global.groups             = [];
global.selectedAccountIds = new Set();
global.currentPage        = 'mailbox';
global.mailboxViewMode    = 'compact';
global.isTempEmailGroup   = false;

// main.js 的工具函数（eval 前提供，eval 后部分会被 Mock 覆盖）
global.translateAppTextLocal     = (text) => text;
global.getUiLanguage             = () => 'zh';
global.formatSelectedItemsLabel  = (count) => `已选 ${count} 项`;
global.formatGroupDisplayName    = (name) => name;
global.formatGroupDescription    = (desc, defaultText) => desc || (defaultText || '');
global.formatAccountStatusLabel  = (status) => status || '';
global.isTempMailboxGroup        = () => false;
global.escapeJs = (text) => String(text == null ? '' : text)
  .replace(/\\/g, '\\\\')
  .replace(/'/g,  "\\'")
  .replace(/"/g,  '\\"')
  .replace(/</g,  '\\u003C')
  .replace(/>/g,  '\\u003E');

// ══════════════════════════════════════════════════════════════════════════
// 4. 方案 B：fs.readFileSync + eval 加载 poll-engine.js + mailbox_compact.js
//    - 先加载统一轮询引擎，再加载简洁模式 UI 适配层
//    - 将 let/const 替换为 var，使顶层状态变量挂载到 global
//    - 使用间接 eval (0, eval)() 在全局作用域执行
// ══════════════════════════════════════════════════════════════════════════

function loadAndEval(relativePath, label) {
  try {
    const filePath = path.resolve(__dirname, relativePath);
    const source   = fs.readFileSync(filePath, 'utf8');
    const processedSource = source.replace(/\b(let|const)\b(\s)/g, 'var$2');
    ;(0, eval)(processedSource);
    console.log(`[setup.js] ${label} 加载成功`);
  } catch (err) {
    console.warn(`[setup.js] ${label} 加载警告:`, err.message);
  }
}

// 顺序重要：先加载引擎，再加载 compact 适配层
loadAndEval('../../static/js/features/poll-engine.js', 'poll-engine.js');
loadAndEval('../../static/js/features/mailbox_compact.js', 'mailbox_compact.js');

// ══════════════════════════════════════════════════════════════════════════
// 5. eval 之后 override：将轮询引擎依赖的函数替换为 Mock
//    （顺序重要：必须在 eval 之后，否则 eval 会覆盖 Mock）
// ══════════════════════════════════════════════════════════════════════════

global.showToast                        = mockShowToast;
global.copyToClipboard                  = mockCopyToClipboard;
global.syncAccountSummaryToAccountCache  = mockSyncAccountSummaryToAccountCache;
global.getCompactVisibleAccounts        = mockGetCompactVisibleAccounts;
global.refreshCompactAccount            = mockRefreshCompactAccount;
global.escapeHtml                       = mockEscapeHtml;
global.handleAccountSelectionChange     = mockHandleAccountSelectionChange;
global.updateBatchActionBar             = mockUpdateBatchActionBar;
global.updateSelectAllCheckbox          = mockUpdateSelectAllCheckbox;
global.updateTopbar                     = mockUpdateTopbar;
global.renderAccountList                = mockRenderAccountList;
global.selectGroup                      = mockSelectGroup;
global.copyVerificationInfo             = mockCopyVerificationInfo;
global.showEditAccountModal             = mockShowEditAccountModal;
global.showEditRemarkOnly               = mockShowEditRemarkOnly;
global.deleteAccount                    = mockDeleteAccount;
global.showBatchTagModal                = mockShowBatchTagModal;
global.showBatchMoveGroupModal          = mockShowBatchMoveGroupModal;
global.copyEmail                        = mockCopyEmail;

// ══════════════════════════════════════════════════════════════════════════
// 6. beforeEach / afterEach 钩子
// ══════════════════════════════════════════════════════════════════════════

beforeEach(() => {
  // 启用假计时器（setInterval / setTimeout / Date.now 都被 Mock）
  jest.useFakeTimers();

  // 清空 Mock 调用记录（保留 implementation，在下面重新设置默认值）
  jest.clearAllMocks();

  // 清空 DOM
  document.body.innerHTML = '';

  // ── 重置全局状态变量 ──
  global.mailboxViewMode    = 'compact';
  global.isTempEmailGroup   = false;
  // 统一引擎变量
  global.pollEnabled    = false;
  global.pollInterval   = 10;
  global.pollMaxCount   = 5;
  // 向后兼容别名（测试代码可能使用旧名称）
  global.compactPollEnabled     = false;
  global.compactPollInterval    = 10;
  global.compactPollMaxCount    = 5;

  // ── 重置 Mock 默认返回值 ──
  mockGetCompactVisibleAccounts.mockReturnValue([]);
  mockCopyToClipboard.mockResolvedValue(undefined);
  mockEscapeHtml.mockImplementation((text) => String(text == null ? '' : text));

  // ── 重置轮询状态（直接操作，不调用 clearInterval 避免 fake/real timer 混用问题）──
  if (typeof pollMap !== 'undefined') {
    pollMap.clear();
  }
  if (typeof compactPollMap !== 'undefined' && compactPollMap !== pollMap) {
    compactPollMap.clear();
  }
  // pollCountdownTimer 和 compactPollCountdownTimer 重置为 null
  global.pollCountdownTimer = null;
  global.compactPollCountdownTimer = null;
});

afterEach(() => {
  // 恢复真实计时器（fake timers 的待处理任务被自动丢弃）
  jest.useRealTimers();

  // 清空 DOM
  document.body.innerHTML = '';

  // 清理剩余轮询状态（防止测试间泄漏）
  if (typeof pollMap !== 'undefined') {
    pollMap.clear();
  }
  if (typeof compactPollMap !== 'undefined' && compactPollMap !== pollMap) {
    compactPollMap.clear();
  }
  global.pollCountdownTimer = null;
  global.compactPollCountdownTimer = null;
});
