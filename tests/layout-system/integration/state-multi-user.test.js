/**
 * 集成测试 - 多用户隔离（TASK-04-004）
 *
 * 覆盖：
 * - TC-F4-004-P: 多用户布局隔离
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable, simulateDrag } = require('../test-utils.js');

describe('多用户隔离集成测试（TASK-04-004）', () => {
  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });
  });

  test('TC-F4-004-P: 不同用户的布局应独立存储（save 使用 userId key）', () => {
    jest.useFakeTimers();
    try {
      window.currentUserId = 'userA';

      const layoutManager = new LayoutManager();
      layoutManager.init();

      const resizer = document.querySelector('[data-resizer="groups"]');
      simulateDrag(resizer, 200, 260);

      // 500ms 到达后写入 outlook_layout_state_userA
      jest.advanceTimersByTime(500);

      const savedRaw = window.localStorage.getItem('outlook_layout_state_userA');
      expect(savedRaw).toBeTruthy();

      const saved = JSON.parse(savedRaw);
      expect(saved.userId).toBe('userA');
      expect(saved.panels.groups.width).toBe('260px');

      // 不应污染 guest key
      expect(window.localStorage.getItem('outlook_layout_state_guest')).toBeNull();
    } finally {
      jest.useRealTimers();
      delete window.currentUserId;
    }
  });

  test('TC-F4-004-P: 用户切换后应加载各自的布局（userB 不应看到 userA 的布局）', () => {
    // userA 保存一个自定义布局
    window.currentUserId = 'userA';
    window.localStorage.setItem(
      'outlook_layout_state_userA',
      JSON.stringify({
        version: '1.1',
        userId: 'userA',
        timestamp: Date.now(),
        panels: {
          groups: { width: '250px', collapsed: false },
          accounts: { width: '320px', collapsed: false },
          emails: { width: '450px', collapsed: false }
        }
      })
    );

    // “切换用户”相当于换一个 userId 并重新进入页面
    createLayoutDOM();
    window.currentUserId = 'userB';

    const layoutManager = new LayoutManager();
    layoutManager.init();

    // userB 无保存数据，应保持默认宽度（createLayoutDOM 初始化的 CSS 变量）
    expect(getCSSVariable('--group-panel-width')).toBe('200px');
    expect(getCSSVariable('--account-panel-width')).toBe('260px');
    expect(getCSSVariable('--email-list-panel-width')).toBe('380px');

    delete window.currentUserId;
  });
});

