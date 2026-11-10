/**
 * 集成测试 - 账号面板首屏自适应初始化
 *
 * 覆盖：
 * - 首次进入 mailbox 页面时，无需手动 resize 即按当前宽度进入正确模式
 * - 后续 window.resize 仍保持正常响应
 * - requestAnimationFrame fallback 与重复调度时序
 */

const fs = require('fs');
const path = require('path');

describe('账号面板首屏自适应初始化', () => {
  let mainApi;
  let accountPanelWidth;

  const flushDensitySync = () => {
    jest.runOnlyPendingTimers();
    jest.runOnlyPendingTimers();
  };

  const createMainDOM = () => {
    document.body.innerHTML = `
      <div id="app">
        <aside id="sidebar"></aside>
        <div id="sidebarBackdrop"></div>
        <div id="topbarTitle"></div>
        <div id="topbarSubtitle"></div>
        <div id="topbar-actions"></div>
        <button class="nav-item active" data-page="dashboard"></button>
        <button class="nav-item" data-page="mailbox"></button>
        <div id="page-dashboard" class="page"></div>
        <div id="page-mailbox" class="page page-hidden">
          <div id="groupPanel" class="groups-column"></div>
          <div id="accountPanel" class="accounts-column"></div>
          <div id="emailListPanel" class="emails-column"></div>
        </div>
      </div>
    `;

    const accountPanel = document.getElementById('accountPanel');
    Object.defineProperty(accountPanel, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        const mailboxPage = document.getElementById('page-mailbox');
        const isVisible = mailboxPage && !mailboxPage.classList.contains('page-hidden');
        const width = isVisible ? accountPanelWidth : 0;
        return {
          width,
          height: 0,
          top: 0,
          left: 0,
          right: width,
          bottom: 0
        };
      }
    });
  };

  beforeAll(() => {
    const scriptPath = path.resolve(__dirname, '../../../static/js/main.js');
    const script = fs.readFileSync(scriptPath, 'utf8');
    window.eval(`${script}\nwindow.__mainResponsiveTestApi = { navigate, initResizeHandles, syncAccountPanelDensityIfVisible };`);
    mainApi = window.__mainResponsiveTestApi;
  });

  beforeEach(() => {
    jest.useFakeTimers();
    accountPanelWidth = 280;

    createMainDOM();

    window.loadGroups = jest.fn();
    window.loadAccountsByGroup = jest.fn();
    window.loadDashboard = jest.fn();
    window.loadSettings = jest.fn();
    window.loadRefreshLogPage = jest.fn();
    window.loadAuditLogPage = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('首次进入窄宽度 mailbox 页面时应直接进入紧凑模式', () => {
    accountPanelWidth = 160;

    mainApi.initResizeHandles();
    mainApi.navigate('mailbox');

    const accountPanel = document.getElementById('accountPanel');
    expect(accountPanel.classList.contains('is-narrow')).toBe(true);
    expect(accountPanel.classList.contains('is-compact')).toBe(true);

    flushDensitySync();
    expect(accountPanel.classList.contains('is-narrow')).toBe(true);
    expect(accountPanel.classList.contains('is-compact')).toBe(true);
  });

  test('隐藏态初始化时不应预先写入错误的紧凑类名', () => {
    accountPanelWidth = 280;

    mainApi.initResizeHandles();
    flushDensitySync();

    const accountPanel = document.getElementById('accountPanel');
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);
  });

  test('首次进入宽宽度 mailbox 页面时首次可见帧就应显示完整信息', () => {
    accountPanelWidth = 280;

    mainApi.initResizeHandles();
    mainApi.navigate('mailbox');

    const accountPanel = document.getElementById('accountPanel');
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);

    flushDensitySync();
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);
  });

  test('初始化修复后，后续 window.resize 仍应正常响应', () => {
    mainApi.initResizeHandles();
    mainApi.navigate('mailbox');
    flushDensitySync();

    const accountPanel = document.getElementById('accountPanel');
    expect(accountPanel.classList.contains('is-compact')).toBe(false);

    accountPanelWidth = 160;
    window.dispatchEvent(new Event('resize'));
    flushDensitySync();
    expect(accountPanel.classList.contains('is-narrow')).toBe(true);
    expect(accountPanel.classList.contains('is-compact')).toBe(true);

    accountPanelWidth = 280;
    window.dispatchEvent(new Event('resize'));
    flushDensitySync();
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);
  });

  test('mailbox 页面反复切换时应根据当前宽度重新同步且不残留旧类名', () => {
    const mailboxPage = document.getElementById('page-mailbox');
    const accountPanel = document.getElementById('accountPanel');

    mainApi.initResizeHandles();

    accountPanelWidth = 160;
    mainApi.navigate('mailbox');
    expect(accountPanel.classList.contains('is-compact')).toBe(true);

    mailboxPage.classList.add('page-hidden');
    document.getElementById('page-dashboard').classList.remove('page-hidden');

    accountPanelWidth = 280;
    mainApi.navigate('mailbox');
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);
  });

  test('requestAnimationFrame 不可用时仍应走 setTimeout fallback 收敛到正确状态', () => {
    const previousWindowRaf = window.requestAnimationFrame;
    const previousWindowCancel = window.cancelAnimationFrame;
    const previousGlobalRaf = global.requestAnimationFrame;
    const previousGlobalCancel = global.cancelAnimationFrame;

    window.requestAnimationFrame = undefined;
    window.cancelAnimationFrame = undefined;
    global.requestAnimationFrame = undefined;
    global.cancelAnimationFrame = undefined;

    try {
      accountPanelWidth = 280;
      mainApi.initResizeHandles();
      mainApi.navigate('mailbox');

      const accountPanel = document.getElementById('accountPanel');
      expect(accountPanel.classList.contains('is-narrow')).toBe(false);
      expect(accountPanel.classList.contains('is-compact')).toBe(false);

      jest.runOnlyPendingTimers();
      expect(accountPanel.classList.contains('is-narrow')).toBe(false);
      expect(accountPanel.classList.contains('is-compact')).toBe(false);
    } finally {
      window.requestAnimationFrame = previousWindowRaf;
      window.cancelAnimationFrame = previousWindowCancel;
      global.requestAnimationFrame = previousGlobalRaf;
      global.cancelAnimationFrame = previousGlobalCancel;
    }
  });

  test('旧同步任务已入队时，二次导航后的调度不应破坏最新宽度状态', () => {
    const accountPanel = document.getElementById('accountPanel');

    mainApi.initResizeHandles();

    accountPanelWidth = 160;
    mainApi.navigate('mailbox');
    expect(accountPanel.classList.contains('is-compact')).toBe(true);

    mainApi.navigate('dashboard');
    accountPanelWidth = 280;
    mainApi.navigate('mailbox');
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);

    flushDensitySync();
    expect(accountPanel.classList.contains('is-narrow')).toBe(false);
    expect(accountPanel.classList.contains('is-compact')).toBe(false);
  });
});
