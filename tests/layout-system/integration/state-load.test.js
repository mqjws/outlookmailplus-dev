/**
 * 集成测试 - 状态加载（TASK-04-003）
 *
 * 覆盖：
 * - TC-F4-003-P: 页面刷新后恢复状态
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable } = require('../test-utils.js');

describe('状态加载集成测试（TASK-04-003）', () => {
  const storageKey = 'outlook_layout_state_guest';

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });
  });

  test('TC-F4-003-P: 页面刷新后状态恢复（宽度 + 折叠）', () => {
    const state = {
      version: '1.1',
      userId: 'guest',
      timestamp: Date.now(),
      panels: {
        groups: { width: '250px', collapsed: true },
        accounts: { width: '300px', collapsed: false },
        emails: { width: '420px', collapsed: false }
      }
    };

    window.localStorage.setItem(storageKey, JSON.stringify(state));

    const layoutManager = new LayoutManager();
    layoutManager.init();

    // 宽度恢复
    expect(getCSSVariable('--group-panel-width')).toBe('250px');
    expect(getCSSVariable('--account-panel-width')).toBe('300px');
    expect(getCSSVariable('--email-list-panel-width')).toBe('420px');

    // 折叠状态恢复（groups）
    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const groupsBtn = groupsPanel.querySelector('.collapse-btn');
    expect(groupsPanel.classList.contains('collapsed')).toBe(true);
    expect(groupsPanel.dataset.autoCollapsed).toBeUndefined();
    expect(groupsBtn.getAttribute('aria-expanded')).toBe('false');
    expect(groupsBtn.textContent.trim()).toBe('→');
    expect(groupsBtn.getAttribute('aria-label')).toBe('展开分组面板');

    // 布局变量应同步（折叠列宽为 0）
    expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
      '0px'
    );
  });
});

