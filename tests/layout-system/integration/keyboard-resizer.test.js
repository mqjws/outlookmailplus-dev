/**
 * 集成测试 - 键盘可访问性（F6）
 *
 * 覆盖：
 * - TC-F6-002-P: 方向键调整宽度
 * - TC-F6-003-P: Shift + 方向键快速调整
 * - 键盘调整后触发 500ms 防抖保存（F6.1）
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable, simulateKeyPress } = require('../test-utils.js');

describe('键盘可访问性集成测试（F6）', () => {
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
    jest.runOnlyPendingTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('TC-F6-002-P: 方向键调整宽度（10px）', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    expect(getCSSVariable('--group-panel-width')).toBe('200px');

    simulateKeyPress(resizer, 'ArrowRight');
    expect(getCSSVariable('--group-panel-width')).toBe('210px');
    expect(resizer.getAttribute('aria-valuenow')).toBe('210');

    simulateKeyPress(resizer, 'ArrowLeft');
    expect(getCSSVariable('--group-panel-width')).toBe('200px');
    expect(resizer.getAttribute('aria-valuenow')).toBe('200');
  });

  test('TC-F6-003-P: Shift + 方向键快速调整（50px）', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    expect(getCSSVariable('--group-panel-width')).toBe('200px');

    simulateKeyPress(resizer, 'ArrowRight', true);
    expect(getCSSVariable('--group-panel-width')).toBe('250px');
    expect(resizer.getAttribute('aria-valuenow')).toBe('250');
  });

  test('键盘调整后应触发 500ms 防抖保存', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');

    simulateKeyPress(resizer, 'ArrowRight');

    // 500ms 内不应写入
    expect(window.localStorage.getItem(storageKey)).toBeNull();
    jest.advanceTimersByTime(499);
    expect(window.localStorage.getItem(storageKey)).toBeNull();

    // 500ms 到达后写入
    jest.advanceTimersByTime(1);
    const savedRaw = window.localStorage.getItem(storageKey);
    expect(savedRaw).toBeTruthy();
    const saved = JSON.parse(savedRaw);
    expect(saved.panels.groups.width).toBe('210px');
  });
});

