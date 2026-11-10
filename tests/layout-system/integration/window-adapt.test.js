/**
 * 集成测试 - 窗口尺寸适配（F5）
 *
 * 覆盖：
 * - TC-F5-001-P: <1200px 自动折叠分组面板
 * - TC-F5-002-P: <900px 自动折叠账号面板
 * - TC-F5-003-P: <700px 自动折叠邮件列表面板
 * - TC-F5-004-P: 窗口放大后自动恢复（仅恢复 autoCollapsed）
 * - TC-F5-005-N: 用户手动折叠的面板不自动恢复
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, setWindowSize } = require('../test-utils.js');

describe('窗口尺寸适配集成测试（F5）', () => {
  let layoutManager;

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
    jest.runOnlyPendingTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('TC-F5-001-P: 窗口宽度 < 1200px 自动折叠分组面板', () => {
    setWindowSize(1199, 800);
    jest.advanceTimersByTime(200);

    const groupsPanel = document.querySelector('[data-panel="groups"]');
    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(groupsPanel.dataset.autoCollapsed).toBe('true');
  });

  test('TC-F5-002-P: 窗口宽度 < 900px 自动折叠账号面板', () => {
    setWindowSize(899, 800);
    jest.advanceTimersByTime(200);

    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const accountsPanel = document.querySelector('[data-panel="accounts"]');

    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(accountsPanel.classList.contains('collapsed')).toBe(true);
    expect(accountsPanel.dataset.autoCollapsed).toBe('true');
  });

  test('TC-F5-003-P: 窗口宽度 < 700px 自动折叠邮件列表面板', () => {
    setWindowSize(699, 800);
    jest.advanceTimersByTime(200);

    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const accountsPanel = document.querySelector('[data-panel="accounts"]');
    const emailsPanel = document.querySelector('[data-panel="emails"]');

    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(accountsPanel.classList.contains('collapsed')).toBe(true);
    expect(emailsPanel.classList.contains('collapsed')).toBe(true);
    expect(emailsPanel.dataset.autoCollapsed).toBe('true');
  });

  test('TC-F5-004-P: 窗口放大后自动恢复面板（仅恢复 autoCollapsed）', () => {
    setWindowSize(699, 800);
    jest.advanceTimersByTime(200);

    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const accountsPanel = document.querySelector('[data-panel="accounts"]');
    const emailsPanel = document.querySelector('[data-panel="emails"]');
    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(accountsPanel.classList.contains('collapsed')).toBe(true);
    expect(emailsPanel.classList.contains('collapsed')).toBe(true);

    setWindowSize(1600, 900);
    jest.advanceTimersByTime(200);

    expect(groupsPanel.classList.contains('collapsed')).toBe(false);
    expect(accountsPanel.classList.contains('collapsed')).toBe(false);
    expect(emailsPanel.classList.contains('collapsed')).toBe(false);
    expect(groupsPanel.dataset.autoCollapsed).not.toBe('true');
    expect(accountsPanel.dataset.autoCollapsed).not.toBe('true');
    expect(emailsPanel.dataset.autoCollapsed).not.toBe('true');
  });

  test('TC-F5-005-N: 用户手动折叠的面板不自动恢复', () => {
    const groupsPanel = document.querySelector('[data-panel="groups"]');

    // 手动折叠：不打 autoCollapsed
    layoutManager.collapsePanel('groups', false);
    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(groupsPanel.dataset.autoCollapsed).not.toBe('true');

    // 小屏下不应把“手动折叠”改写成 autoCollapsed
    setWindowSize(1199, 800);
    jest.advanceTimersByTime(200);
    expect(groupsPanel.dataset.autoCollapsed).not.toBe('true');

    // 放大也不应恢复
    setWindowSize(1600, 900);
    jest.advanceTimersByTime(200);
    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
  });

  test('隐藏状态下的邮件列表不参与自动折叠/恢复（避免空白列回归）', () => {
    const emailsPanel = document.querySelector('[data-panel="emails"]');
    emailsPanel.classList.add('hidden');

    setWindowSize(699, 800);
    jest.advanceTimersByTime(200);
    expect(emailsPanel.dataset.autoCollapsed).not.toBe('true');

    setWindowSize(1600, 900);
    jest.advanceTimersByTime(200);
    expect(emailsPanel.dataset.autoCollapsed).not.toBe('true');
  });
});

