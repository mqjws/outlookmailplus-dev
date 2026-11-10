/**
 * 集成测试 - 状态持久化错误处理（TASK-04-005）
 *
 * 覆盖：
 * - TC-F4-006-N: localStorage 不可用
 * - TC-F4-007-N: localStorage 数据损坏
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable, simulateDrag } = require('../test-utils.js');

describe('状态持久化错误处理集成测试（TASK-04-005）', () => {
  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });
  });

  test('TC-F4-006-N: localStorage 不可用时应降级为默认布局且不影响拖动', () => {
    const originalLocalStorage = window.localStorage;

    // 模拟隐私模式/禁用 localStorage：访问/读写均抛错
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: () => {
          throw new Error('localStorage disabled');
        },
        setItem: () => {
          throw new Error('localStorage disabled');
        },
        removeItem: () => {
          throw new Error('localStorage disabled');
        },
        key: () => null,
        get length() {
          return 0;
        }
      }
    });

    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    try {
      const layoutManager = new LayoutManager();
      layoutManager.init();

      // 拖动仍应生效（只是无法持久化）
      jest.useFakeTimers();
      try {
        const resizer = document.querySelector('[data-resizer="groups"]');
        simulateDrag(resizer, 200, 250);
        expect(getCSSVariable('--group-panel-width')).toBe('250px');

        // 即使等待 500ms，也不应抛异常
        jest.advanceTimersByTime(600);
      } finally {
        jest.useRealTimers();
      }

      // “刷新页面”后应回到默认布局（无法持久化）
      createLayoutDOM();
      const layoutManager2 = new LayoutManager();
      layoutManager2.init();
      expect(getCSSVariable('--group-panel-width')).toBe('200px');
      expect(getCSSVariable('--account-panel-width')).toBe('260px');
      expect(getCSSVariable('--email-list-panel-width')).toBe('380px');
    } finally {
      warnSpy.mockRestore();
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: originalLocalStorage
      });
    }
  });

  test('TC-F4-007-N: localStorage 数据损坏时应清除并使用默认布局', () => {
    const storageKey = 'outlook_layout_state_guest';
    window.localStorage.setItem(storageKey, '{bad json');

    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const layoutManager = new LayoutManager();
      layoutManager.init();

      // 应使用默认布局（createLayoutDOM 初始化的 CSS 变量）
      expect(getCSSVariable('--group-panel-width')).toBe('200px');
      expect(getCSSVariable('--account-panel-width')).toBe('260px');
      expect(getCSSVariable('--email-list-panel-width')).toBe('380px');

      // 损坏数据应被清除
      expect(window.localStorage.getItem(storageKey)).toBeNull();
    } finally {
      errSpy.mockRestore();
    }
  });
});

