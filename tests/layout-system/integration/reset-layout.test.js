/**
 * 集成测试 - 恢复默认布局（F3）
 *
 * 覆盖：
 * - TC-F3-001-P: 恢复默认布局（宽度/折叠状态恢复 + localStorage 清除 + 300ms 动画开关）
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable } = require('../test-utils.js');

describe('恢复默认布局集成测试（F3）', () => {
  let layoutManager;
  const storageKey = 'outlook_layout_state_guest';

  beforeEach(() => {
    jest.useFakeTimers();
    createLayoutDOM();

    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });

    layoutManager = new LayoutManager();
    layoutManager.init();

    // 清掉 init() 里 requestAnimationFrame/withNoTransition 的残留计时器
    jest.runOnlyPendingTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('TC-F3-001-P: resetLayout() 应恢复默认宽度、展开面板并清除 localStorage', () => {
    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const accountsPanel = document.querySelector('[data-panel="accounts"]');
    const emailsPanel = document.querySelector('[data-panel="emails"]');

    // 先制造“非默认状态”并写入 localStorage
    layoutManager.updatePanelWidth(groupsPanel, 250);
    layoutManager.collapsePanel('accounts', false); // 手动折叠会立即保存
    expect(window.localStorage.getItem(storageKey)).toBeTruthy();

    // 再制造一个“尚未到期的保存防抖”，用于验证 reset 会 cancel
    layoutManager.saveDebouncer.debounced();

    layoutManager.resetLayout();

    // 立即生效：localStorage 被清空
    expect(window.localStorage.getItem(storageKey)).toBeNull();

    // 默认宽度恢复
    expect(getCSSVariable('--group-panel-width')).toBe('200px');
    expect(getCSSVariable('--account-panel-width')).toBe('260px');
    expect(getCSSVariable('--email-list-panel-width')).toBe('380px');

    // 面板展开
    expect(groupsPanel.classList.contains('collapsed')).toBe(false);
    expect(accountsPanel.classList.contains('collapsed')).toBe(false);
    expect(emailsPanel.classList.contains('collapsed')).toBe(false);

    // 300ms 动画开关：class 先存在，随后移除
    expect(document.documentElement.classList.contains('layout-resetting')).toBe(true);
    jest.advanceTimersByTime(350);
    expect(document.documentElement.classList.contains('layout-resetting')).toBe(false);

    // 防抖保存应被取消：推进 500ms 不应重新写入
    jest.advanceTimersByTime(1000);
    expect(window.localStorage.getItem(storageKey)).toBeNull();
  });
});

