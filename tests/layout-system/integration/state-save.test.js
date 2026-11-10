/**
 * 集成测试 - 状态保存（TASK-04-002）
 *
 * 覆盖：
 * - TC-F4-001-P: 拖动后 500ms 保存状态
 * - TC-F4-002-P: 折叠后立即保存状态
 * - TC-F4-005-P: beforeunload 强制保存
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, simulateDrag } = require('../test-utils.js');

describe('状态保存集成测试（TASK-04-002）', () => {
  let layoutManager;
  const storageKey = 'outlook_layout_state_guest';

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });
    layoutManager = new LayoutManager();
    layoutManager.init();
  });

  test('TC-F4-001-P: 拖动后 500ms 保存状态', () => {
    jest.useFakeTimers();
    try {
      const resizer = document.querySelector('[data-resizer="groups"]');

      simulateDrag(resizer, 200, 250);

      // 500ms 内不应写入
      expect(window.localStorage.getItem(storageKey)).toBeNull();
      jest.advanceTimersByTime(499);
      expect(window.localStorage.getItem(storageKey)).toBeNull();

      // 500ms 到达后写入
      jest.advanceTimersByTime(1);
      const savedRaw = window.localStorage.getItem(storageKey);
      expect(savedRaw).toBeTruthy();

      const saved = JSON.parse(savedRaw);
      expect(saved.version).toBe('1.1');
      expect(saved.userId).toBe('guest');
      expect(saved.panels.groups.width).toBe('250px');
      expect(saved.panels.groups.collapsed).toBe(false);
    } finally {
      jest.useRealTimers();
    }
  });

  test('TC-F4-002-P: 折叠后立即保存状态', () => {
    const btn = document.querySelector('[data-panel="groups"] .collapse-btn');
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

    const savedRaw = window.localStorage.getItem(storageKey);
    expect(savedRaw).toBeTruthy();
    const saved = JSON.parse(savedRaw);
    expect(saved.panels.groups.collapsed).toBe(true);
  });

  test('TC-F4-005-P: 页面卸载时强制保存', () => {
    jest.useFakeTimers();
    try {
      const resizer = document.querySelector('[data-resizer="groups"]');

      simulateDrag(resizer, 200, 260);

      // 防抖尚未到达时触发 beforeunload，应立即落盘
      expect(window.localStorage.getItem(storageKey)).toBeNull();
      window.dispatchEvent(new Event('beforeunload'));

      const savedRaw = window.localStorage.getItem(storageKey);
      expect(savedRaw).toBeTruthy();
      const saved = JSON.parse(savedRaw);
      expect(saved.panels.groups.width).toBe('260px');
    } finally {
      jest.useRealTimers();
    }
  });
});

