/**
 * 集成测试 - 面板折叠/展开完整流程
 *
 * 覆盖：TD 文档 F2 用例（TC-F2-001 ~ TC-F2-005）
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, getCSSVariable } = require('../test-utils.js');

describe('面板折叠/展开集成测试（阶段三）', () => {
  let layoutManager;

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

  test('TC-F2-001-P: 点击折叠按钮折叠面板', () => {
    const panel = document.querySelector('[data-panel="groups"]');
    const btn = panel.querySelector('.collapse-btn');

    expect(getCSSVariable('--group-panel-width')).toBe('200px');
    expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
      '200px'
    );

    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

    // 宽度变为 0（布局生效宽度），保存宽度不丢失
    expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
      '0px'
    );
    expect(getCSSVariable('--group-panel-width')).toBe('200px');

    // 折叠状态与按钮状态更新
    expect(panel.classList.contains('collapsed')).toBe(true);
    expect(btn.textContent.trim()).toBe('→');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(btn.getAttribute('aria-label')).toBe('展开分组面板');

    // 指示器存在且可用于展开
    const indicator = panel.querySelector('.collapsed-indicator[data-panel="groups"]');
    expect(indicator).toBeTruthy();
    expect(indicator.getAttribute('role')).toBe('button');
    expect(indicator.getAttribute('tabindex')).toBe('0');
    expect(indicator.getAttribute('aria-label')).toBe('展开分组面板');
  });

  test('TC-F2-002-P: 点击折叠指示条展开面板', () => {
    const panel = document.querySelector('[data-panel="groups"]');
    const btn = panel.querySelector('.collapse-btn');
    const indicator = panel.querySelector('.collapsed-indicator[data-panel="groups"]');

    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(panel.classList.contains('collapsed')).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
      '0px'
    );

    indicator.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

    expect(panel.classList.contains('collapsed')).toBe(false);
    expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
      '200px'
    );
    expect(btn.textContent.trim()).toBe('←');
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    expect(btn.getAttribute('aria-label')).toBe('折叠分组面板');
  });

  test('TC-F2-003-N: 尝试折叠所有面板应提示并阻止', () => {
    // 先折叠另外两个面板（auto=true 绕过规则）
    layoutManager.collapsePanel('accounts', true);
    layoutManager.collapsePanel('emails', true);

    const groupsPanel = document.querySelector('[data-panel="groups"]');
    const groupsBtn = groupsPanel.querySelector('.collapse-btn');

    const originalToast = window.showToast;
    window.showToast = jest.fn();
    try {
      groupsBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(groupsPanel.classList.contains('collapsed')).toBe(false);
      expect(window.showToast).toHaveBeenCalledWith('至少需要保持一个面板展开', 'warning');
    } finally {
      window.showToast = originalToast;
    }
  });

  test('TC-F2-004-P/TC-F2-005-N: 折叠后 resizer 不可用且无法拖动', () => {
    const panel = document.querySelector('[data-panel="groups"]');
    const btn = panel.querySelector('.collapse-btn');
    const resizer = document.querySelector('[data-resizer="groups"]');

    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(panel.classList.contains('collapsed')).toBe(true);

    // 尝试拖动（startResize 内部应直接返回）
    resizer.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: 200, button: 0 })
    );
    document.dispatchEvent(
      new MouseEvent('mousemove', { bubbles: true, cancelable: true, clientX: 260 })
    );
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));

    expect(layoutManager.isResizing).toBe(false);
  });
});
