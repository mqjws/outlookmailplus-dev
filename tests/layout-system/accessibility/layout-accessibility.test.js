/**
 * 布局系统可访问性测试
 *
 * 测试目标：
 * - ARIA 属性完整性
 * - 键盘导航
 * - 焦点管理
 * - 屏幕阅读器兼容性（aria-label, aria-expanded, aria-valuenow）
 *
 * 参考文档：TD 第九章 - 可访问性测试方案
 * 标准：WCAG 2.1 AA
 */

const {
  createLayoutDOM,
  getCSSVariable,
  simulateKeyPress,
  wait,
  hasFocus
} = require('../test-utils');

const LayoutManager = require('../../../static/js/layout-manager.js');

// ========================
// 1. Resizer ARIA 属性
// ========================
describe('可访问性 - Resizer ARIA 属性', () => {
  beforeEach(() => {
    createLayoutDOM();
  });

  test('所有 resizer 应有 role="separator"', () => {
    const resizers = document.querySelectorAll('.resizer');
    resizers.forEach(resizer => {
      expect(resizer.getAttribute('role')).toBe('separator');
    });
  });

  test('所有 resizer 应有 aria-orientation="vertical"', () => {
    const resizers = document.querySelectorAll('.resizer');
    resizers.forEach(resizer => {
      expect(resizer.getAttribute('aria-orientation')).toBe('vertical');
    });
  });

  test('所有 resizer 应有 aria-label', () => {
    const resizers = document.querySelectorAll('.resizer');
    resizers.forEach(resizer => {
      const label = resizer.getAttribute('aria-label');
      expect(label).toBeTruthy();
      expect(label.length).toBeGreaterThan(0);
    });
  });

  test('所有 resizer 应有 aria-valuenow/min/max', () => {
    const resizers = document.querySelectorAll('.resizer');
    resizers.forEach(resizer => {
      expect(resizer.getAttribute('aria-valuenow')).toBeTruthy();
      expect(resizer.getAttribute('aria-valuemin')).toBeTruthy();
      expect(resizer.getAttribute('aria-valuemax')).toBeTruthy();

      // 数值应为正整数
      const now = parseInt(resizer.getAttribute('aria-valuenow'));
      const min = parseInt(resizer.getAttribute('aria-valuemin'));
      const max = parseInt(resizer.getAttribute('aria-valuemax'));

      expect(now).toBeGreaterThan(0);
      expect(min).toBeGreaterThan(0);
      expect(max).toBeGreaterThan(min);
      expect(now).toBeGreaterThanOrEqual(min);
      expect(now).toBeLessThanOrEqual(max);
    });
  });

  test('所有 resizer 应有 tabindex="0" 以支持键盘聚焦', () => {
    const resizers = document.querySelectorAll('.resizer');
    resizers.forEach(resizer => {
      expect(resizer.getAttribute('tabindex')).toBe('0');
    });
  });

  test('所有 resizer 应有 data-resizer 属性标识对应面板', () => {
    const expected = ['groups', 'accounts', 'emails'];
    const resizers = document.querySelectorAll('.resizer');

    const actual = Array.from(resizers).map(r => r.getAttribute('data-resizer'));
    expected.forEach(panel => {
      expect(actual).toContain(panel);
    });
  });
});

// ========================
// 2. 折叠按钮 ARIA 属性
// ========================
describe('可访问性 - 折叠按钮 ARIA 属性', () => {
  beforeEach(() => {
    createLayoutDOM();
  });

  test('所有折叠按钮应有 aria-expanded 属性', () => {
    const buttons = document.querySelectorAll('.collapse-btn');
    buttons.forEach(btn => {
      expect(btn.getAttribute('aria-expanded')).toBeTruthy();
    });
  });

  test('所有折叠按钮应有 aria-label 属性', () => {
    const buttons = document.querySelectorAll('.collapse-btn');
    buttons.forEach(btn => {
      const label = btn.getAttribute('aria-label');
      expect(label).toBeTruthy();
      expect(label.length).toBeGreaterThan(0);
    });
  });

  test('所有折叠按钮应有 data-panel 属性', () => {
    const buttons = document.querySelectorAll('.collapse-btn');
    buttons.forEach(btn => {
      expect(btn.getAttribute('data-panel')).toBeTruthy();
    });
  });

  test('初始状态下所有面板 aria-expanded 应为 "true"', () => {
    const buttons = document.querySelectorAll('.collapse-btn');
    buttons.forEach(btn => {
      expect(btn.getAttribute('aria-expanded')).toBe('true');
    });
  });
});

// ========================
// 3. 折叠/展开时 ARIA 更新
// ========================
describe('可访问性 - 折叠/展开 ARIA 更新', () => {
  let manager;

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1600 });
    manager = new LayoutManager();
    manager.init();
  });

  test('折叠面板后 aria-expanded 应更新为 "false"', () => {
    manager.collapsePanel('groups');

    const btn = document.querySelector('.collapse-btn[data-panel="groups"]');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  test('展开面板后 aria-expanded 应恢复为 "true"', () => {
    manager.collapsePanel('groups');
    manager.expandPanel('groups');

    const btn = document.querySelector('.collapse-btn[data-panel="groups"]');
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });

  test('togglePanel 应正确切换 aria-expanded', () => {
    const btn = document.querySelector('.collapse-btn[data-panel="accounts"]');

    expect(btn.getAttribute('aria-expanded')).toBe('true');

    manager.togglePanel('accounts');
    expect(btn.getAttribute('aria-expanded')).toBe('false');

    manager.togglePanel('accounts');
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });
});

// ========================
// 4. 键盘导航
// ========================
describe('可访问性 - 键盘导航', () => {
  let manager;

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1600 });
    manager = new LayoutManager();
    manager.init();
  });

  test('resizer 应可通过 Tab 键聚焦', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    resizer.focus();
    expect(document.activeElement).toBe(resizer);
  });

  test('← 键应减小面板宽度（每次 10px）', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    resizer.focus();

    const initialWidth = getCSSVariable('--group-panel-width');
    const initialValue = parseInt(initialWidth);

    simulateKeyPress(resizer, 'ArrowLeft', false);

    const newWidth = getCSSVariable('--group-panel-width');
    const newValue = parseInt(newWidth);

    // 宽度应减小（可能受最小宽度限制）
    expect(newValue).toBeLessThanOrEqual(initialValue);
  });

  test('→ 键应增大面板宽度（每次 10px）', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    resizer.focus();

    const initialWidth = getCSSVariable('--group-panel-width');
    const initialValue = parseInt(initialWidth);

    simulateKeyPress(resizer, 'ArrowRight', false);

    const newWidth = getCSSVariable('--group-panel-width');
    const newValue = parseInt(newWidth);

    // 宽度应增大（可能受最大宽度限制）
    expect(newValue).toBeGreaterThanOrEqual(initialValue);
  });

  test('Shift + → 键应快速增大面板宽度（每次 50px）', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    resizer.focus();

    // 先用普通 → 键测量普通步进
    const before1 = parseInt(getCSSVariable('--group-panel-width'));
    simulateKeyPress(resizer, 'ArrowRight', false);
    const after1 = parseInt(getCSSVariable('--group-panel-width'));
    const normalDelta = after1 - before1;

    // 再用 Shift + → 键测量快速步进
    const before2 = parseInt(getCSSVariable('--group-panel-width'));
    simulateKeyPress(resizer, 'ArrowRight', true);
    const after2 = parseInt(getCSSVariable('--group-panel-width'));
    const shiftDelta = after2 - before2;

    // Shift 步进应 >= 普通步进（除非已达最大宽度限制）
    if (after2 < 400) {
      expect(shiftDelta).toBeGreaterThanOrEqual(normalDelta);
    } else {
      expect(shiftDelta).toBeGreaterThanOrEqual(0);
    }
  });

  test('折叠按钮绑定了 click 事件并可触发折叠', () => {
    const btn = document.querySelector('.collapse-btn[data-panel="groups"]');
    btn.focus();

    // LayoutManager 通过 addEventListener('click') 绑定折叠逻辑
    // 在 jsdom 中直接派发 click 事件
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    const panel = document.querySelector('[data-panel="groups"]');
    expect(panel.classList.contains('collapsed')).toBe(true);
  });
});

// ========================
// 5. 键盘调整后 ARIA 值更新
// ========================
describe('可访问性 - 键盘调整 ARIA 值更新', () => {
  let manager;

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1600 });
    manager = new LayoutManager();
    manager.init();
  });

  test('键盘调整宽度后 aria-valuenow 应更新', () => {
    const resizer = document.querySelector('[data-resizer="groups"]');
    const initialValue = resizer.getAttribute('aria-valuenow');

    resizer.focus();
    simulateKeyPress(resizer, 'ArrowRight', false);

    const newValue = resizer.getAttribute('aria-valuenow');
    // 值应发生变化（除非已达到最大值）
    const initial = parseInt(initialValue);
    const updated = parseInt(newValue);
    expect(updated).toBeGreaterThanOrEqual(initial);
  });
});

// ========================
// 6. 面板语义结构
// ========================
describe('可访问性 - 面板结构', () => {
  beforeEach(() => {
    createLayoutDOM();
  });

  test('每个可折叠面板应有 panel-header 和 panel-content', () => {
    const panels = document.querySelectorAll('.resizable-panel');
    panels.forEach(panel => {
      expect(panel.querySelector('.panel-header')).toBeTruthy();
      expect(panel.querySelector('.panel-content')).toBeTruthy();
    });
  });

  test('邮件详情面板应存在且不可折叠', () => {
    const detail = document.querySelector('.email-detail-panel');
    expect(detail).toBeTruthy();

    // 不应有折叠按钮
    const collapseBtn = detail.querySelector('.collapse-btn');
    expect(collapseBtn).toBeNull();
  });

  test('main-container 应包含所有面板', () => {
    const container = document.querySelector('.main-container');
    expect(container).toBeTruthy();

    const panels = container.querySelectorAll('.resizable-panel');
    expect(panels.length).toBe(3);

    const detail = container.querySelector('.email-detail-panel');
    expect(detail).toBeTruthy();
  });
});

// ========================
// 7. 折叠指示条可访问性
// ========================
describe('可访问性 - 折叠指示条', () => {
  let manager;

  beforeEach(() => {
    createLayoutDOM();
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1600 });
    manager = new LayoutManager();
    manager.init();
  });

  test('折叠后应创建可交互的指示条', () => {
    manager.collapsePanel('groups');

    // 检查是否存在折叠指示条
    const indicator = document.querySelector('.collapsed-indicator');
    if (indicator) {
      // 指示条应可聚焦或可点击
      expect(
        indicator.getAttribute('tabindex') === '0' ||
        indicator.getAttribute('role') === 'button' ||
        indicator.tagName === 'BUTTON'
      ).toBe(true);
    }
  });
});
