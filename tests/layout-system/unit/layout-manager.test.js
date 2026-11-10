/**
 * LayoutManager 单元测试（TASK-02-001）
 *
 * 覆盖范围：
 * - 类基础结构与 init()
 * - getMinWidth() / getMaxWidth()
 * - updatePanelWidth()
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const {
  createLayoutDOM,
  getCSSVariable,
  simulateDrag,
  wait
} = require('../test-utils.js');

describe('LayoutManager 单元测试（TASK-02-001）', () => {
  let layoutManager;

  beforeEach(() => {
    createLayoutDOM();
    // jsdom 默认 innerWidth 较小会触发“详情面板最小宽度”约束，影响基础用例；
    // 这里统一设置为较宽的视口，避免非目标场景干扰。
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1600
    });
    layoutManager = new LayoutManager();
    layoutManager.init();
  });

  test('init() 应该缓存 panels 与 resizers', () => {
    expect(layoutManager.container).not.toBeNull();
    expect(layoutManager.panels.get('groups')).toBeTruthy();
    expect(layoutManager.panels.get('accounts')).toBeTruthy();
    expect(layoutManager.panels.get('emails')).toBeTruthy();
    expect(layoutManager.resizers.get('groups')).toBeTruthy();
    expect(layoutManager.resizers.get('accounts')).toBeTruthy();
    expect(layoutManager.resizers.get('emails')).toBeTruthy();
  });

  describe('getMinWidth() - 获取最小宽度', () => {
    test('应该返回分组面板的最小宽度', () => {
      expect(layoutManager.getMinWidth('groups')).toBe(150);
    });

    test('应该返回账号面板的最小宽度', () => {
      expect(layoutManager.getMinWidth('accounts')).toBe(180);
    });

    test('应该返回邮件列表面板的最小宽度', () => {
      expect(layoutManager.getMinWidth('emails')).toBe(280);
    });

    test('未知类型应该回退到默认最小宽度', () => {
      expect(layoutManager.getMinWidth('unknown')).toBe(150);
    });
  });

  describe('getMaxWidth() - 获取最大宽度', () => {
    test('应该返回分组面板的最大宽度', () => {
      expect(layoutManager.getMaxWidth('groups')).toBe(400);
    });

    test('应该返回账号面板的最大宽度', () => {
      expect(layoutManager.getMaxWidth('accounts')).toBe(500);
    });

    test('应该返回邮件列表面板的最大宽度', () => {
      expect(layoutManager.getMaxWidth('emails')).toBe(600);
    });

    test('未知类型应该回退到默认最大宽度', () => {
      expect(layoutManager.getMaxWidth('unknown')).toBe(600);
    });
  });

  describe('updatePanelWidth() - 更新面板宽度', () => {
    test('应该正确更新 CSS 变量并同步 aria-valuenow', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const resizer = document.querySelector('[data-resizer="groups"]');

      layoutManager.updatePanelWidth(panel, 250);

      expect(getCSSVariable('--group-panel-width')).toBe('250px');
      expect(resizer.getAttribute('aria-valuenow')).toBe('250');
    });

    test('无效参数不应抛错', () => {
      expect(() => layoutManager.updatePanelWidth(null, 200)).not.toThrow();
      expect(() => layoutManager.updatePanelWidth({}, 200)).not.toThrow();
      expect(() => {
        const panel = document.querySelector('[data-panel="groups"]');
        layoutManager.updatePanelWidth(panel, NaN);
      }).not.toThrow();
    });

    test('未知 panelType 不应修改 CSS 变量', () => {
      const before = getCSSVariable('--group-panel-width');
      const panel = document.createElement('div');
      panel.dataset.panel = 'unknown';

      layoutManager.updatePanelWidth(panel, 333);

      expect(getCSSVariable('--group-panel-width')).toBe(before);
    });
  });

  describe('折叠/展开（TASK-03-001）', () => {
    test('getExpandedPanels() 应返回当前展开的侧边栏面板（TASK-03-005）', () => {
      expect(layoutManager.getExpandedPanels()).toEqual(['groups', 'accounts', 'emails']);

      layoutManager.collapsePanel('accounts', true);
      expect(layoutManager.getExpandedPanels()).toEqual(['groups', 'emails']);

      layoutManager.collapsePanel('emails', true);
      expect(layoutManager.getExpandedPanels()).toEqual(['groups']);
    });

    test('TC-F2-003-N: 不能折叠最后一个展开的面板（仅限制手动折叠）', () => {
      // 先折叠其他两个面板（auto=true 不受限制）
      layoutManager.collapsePanel('accounts', true);
      layoutManager.collapsePanel('emails', true);

      const groupsPanel = document.querySelector('[data-panel="groups"]');
      expect(groupsPanel.classList.contains('collapsed')).toBe(false);

      // stub toast
      const originalToast = window.showToast;
      window.showToast = jest.fn();
      try {
        layoutManager.collapsePanel('groups', false);

        // 应保持展开并提示
        expect(groupsPanel.classList.contains('collapsed')).toBe(false);
        expect(window.showToast).toHaveBeenCalledWith('至少需要保持一个面板展开', 'warning');

        // auto=true 允许折叠（为后续窗口自适应留口子）
        layoutManager.collapsePanel('groups', true);
        expect(groupsPanel.classList.contains('collapsed')).toBe(true);
      } finally {
        window.showToast = originalToast;
      }
    });

    test('TC-F2-005-N: 折叠状态下不能拖动调整宽度（TASK-03-006）', async () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const resizer = document.querySelector('[data-resizer="groups"]');

      layoutManager.collapsePanel('groups', false);
      expect(panel.classList.contains('collapsed')).toBe(true);

      // 尝试触发拖动（应被 startResize 直接忽略）
      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
      );
      document.dispatchEvent(
        new MouseEvent('mousemove', { bubbles: true, clientX: 260 })
      );
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

      expect(layoutManager.isResizing).toBe(false);
      expect(document.body.classList.contains('layout-resizing')).toBe(false);
    });

    test('TASK-03-007: 自动折叠应设置 data-autoCollapsed 标记，展开/手动折叠应移除', () => {
      const panel = document.querySelector('[data-panel="groups"]');

      layoutManager.collapsePanel('groups', true);
      expect(panel.dataset.autoCollapsed).toBe('true');

      layoutManager.expandPanel('groups');
      expect(panel.dataset.autoCollapsed).toBeUndefined();

      layoutManager.collapsePanel('groups', false);
      expect(panel.dataset.autoCollapsed).toBeUndefined();
    });

    test('折叠/展开应更新按钮图标与 aria-label（TASK-03-002）', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      expect(btn.textContent.trim()).toBe('←');
      expect(btn.getAttribute('aria-label')).toBe('折叠分组面板');
      expect(btn.getAttribute('aria-expanded')).toBe('true');

      layoutManager.collapsePanel('groups');

      expect(btn.textContent.trim()).toBe('→');
      expect(btn.getAttribute('aria-label')).toBe('展开分组面板');
      expect(btn.getAttribute('aria-expanded')).toBe('false');

      layoutManager.expandPanel('groups');

      expect(btn.textContent.trim()).toBe('←');
      expect(btn.getAttribute('aria-label')).toBe('折叠分组面板');
      expect(btn.getAttribute('aria-expanded')).toBe('true');
    });

    test('collapsePanel() 应添加 collapsed 类并更新 aria-expanded', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      expect(panel.classList.contains('collapsed')).toBe(false);
      expect(btn.getAttribute('aria-expanded')).toBe('true');

      layoutManager.collapsePanel('groups');

      expect(panel.classList.contains('collapsed')).toBe(true);
      expect(btn.getAttribute('aria-expanded')).toBe('false');
    });

    test('expandPanel() 应移除 collapsed 类并更新 aria-expanded', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      layoutManager.collapsePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(true);

      layoutManager.expandPanel('groups');

      expect(panel.classList.contains('collapsed')).toBe(false);
      expect(btn.getAttribute('aria-expanded')).toBe('true');
    });

    test('togglePanel() 应在折叠/展开之间切换', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      layoutManager.togglePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(true);
      expect(btn.getAttribute('aria-expanded')).toBe('false');

      layoutManager.togglePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(false);
      expect(btn.getAttribute('aria-expanded')).toBe('true');
    });

    test('未知 panelType 应安全返回且不抛错', () => {
      expect(() => layoutManager.collapsePanel('unknown')).not.toThrow();
      expect(() => layoutManager.expandPanel('unknown')).not.toThrow();
      expect(() => layoutManager.togglePanel('unknown')).not.toThrow();
    });
  });

  describe('calculateNewWidth() - 计算新宽度', () => {
    test('TC-F1-001-P: 应该正确计算拖动后的宽度', () => {
      const newWidth = layoutManager.calculateNewWidth(200, 250, 200, 'groups');
      expect(newWidth).toBe(250);
    });

    test('TC-F1-002-B: 应该限制在最小宽度', () => {
      const newWidth = layoutManager.calculateNewWidth(200, 0, 200, 'groups');
      expect(newWidth).toBe(150);
    });

    test('TC-F1-003-B: 应该限制在最大宽度', () => {
      const newWidth = layoutManager.calculateNewWidth(200, 999, 200, 'groups');
      expect(newWidth).toBe(400);
    });

    test('TC-F1-004-B: 应该保证邮件详情面板至少 400px', () => {
      // 设置一个较窄窗口并调整其他面板宽度，让 groups 的最大允许宽度受到约束
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 1300
      });
      document.documentElement.style.setProperty('--account-panel-width', '300px');
      document.documentElement.style.setProperty('--email-list-panel-width', '280px');

      const newWidth = layoutManager.calculateNewWidth(0, 1000, 200, 'groups');
      // 1300 - (300+280) - 400 = 320
      expect(newWidth).toBe(320);
    });
  });

  describe('calculateOtherPanelsWidth() - 计算其他面板总宽度', () => {
    test('应返回除自身外的侧边栏宽度之和', () => {
      // 默认：200 / 260 / 380
      expect(layoutManager.calculateOtherPanelsWidth('groups')).toBe(260 + 380);
      expect(layoutManager.calculateOtherPanelsWidth('accounts')).toBe(200 + 380);
      expect(layoutManager.calculateOtherPanelsWidth('emails')).toBe(200 + 260);
    });
  });

  describe('折叠/展开（TASK-03-001）', () => {
    test('collapsePanel() 应添加 collapsed 类并更新 aria-expanded=false', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      expect(panel.classList.contains('collapsed')).toBe(false);
      expect(btn.getAttribute('aria-expanded')).toBe('true');

      layoutManager.collapsePanel('groups');

      expect(panel.classList.contains('collapsed')).toBe(true);
      expect(btn.getAttribute('aria-expanded')).toBe('false');
    });

    test('expandPanel() 应移除 collapsed 类并更新 aria-expanded=true', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const btn = panel.querySelector('.collapse-btn');

      layoutManager.collapsePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(true);

      layoutManager.expandPanel('groups');

      expect(panel.classList.contains('collapsed')).toBe(false);
      expect(btn.getAttribute('aria-expanded')).toBe('true');
    });

    test('togglePanel() 应在折叠/展开之间切换', () => {
      const panel = document.querySelector('[data-panel="groups"]');

      layoutManager.togglePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(true);

      layoutManager.togglePanel('groups');
      expect(panel.classList.contains('collapsed')).toBe(false);
    });

    test('未知 panelType 不应抛错', () => {
      expect(() => layoutManager.collapsePanel('unknown')).not.toThrow();
      expect(() => layoutManager.expandPanel('unknown')).not.toThrow();
      expect(() => layoutManager.togglePanel('unknown')).not.toThrow();
    });
  });

  describe('parsePx() - 解析 px 字符串', () => {
    test('应该解析有效 px', () => {
      expect(layoutManager.parsePx('200px')).toBe(200);
      expect(layoutManager.parsePx('  260px ')).toBe(260);
    });

    test('无效格式返回 null', () => {
      expect(layoutManager.parsePx('200')).toBeNull();
      expect(layoutManager.parsePx('abcpx')).toBeNull();
      expect(layoutManager.parsePx('')).toBeNull();
      expect(layoutManager.parsePx(null)).toBeNull();
    });
  });

  test('TC-F1-001-P: startResize/resize/stopResize 基本拖动流程应更新宽度', async () => {
    const resizer = document.querySelector('[data-resizer="groups"]');

    // 初始宽度
    expect(getCSSVariable('--group-panel-width')).toBe('200px');

    // 模拟拖动：从 200px 拖到 250px
    simulateDrag(resizer, 200, 250);
    await wait(50);

    // 宽度已更新
    expect(getCSSVariable('--group-panel-width')).toBe('250px');
  });

  describe('分支覆盖补充（保证覆盖率阈值）', () => {
    test('getPanelDisplayName() 应覆盖 accounts/emails/default 分支', () => {
      expect(layoutManager.getPanelDisplayName('accounts')).toBe('账号');
      expect(layoutManager.getPanelDisplayName('emails')).toBe('邮件列表');
      expect(layoutManager.getPanelDisplayName('unknown')).toBe('面板');
    });

    test('onCollapseButtonClick() 应根据 data-panel 调用 togglePanel', () => {
      const btn = document.querySelector('.collapse-btn[data-panel="groups"]');
      const spy = jest.spyOn(layoutManager, 'togglePanel');

      btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

      expect(spy).toHaveBeenCalledWith('groups');
    });

    test('onCollapseButtonClick() data-panel 缺失时应安全返回', () => {
      expect(() =>
        layoutManager.onCollapseButtonClick({
          currentTarget: { dataset: {} },
          preventDefault: () => {}
        })
      ).not.toThrow();

      expect(() => layoutManager.onCollapseButtonClick(null)).not.toThrow();
    });

    test('ensureCollapsedIndicators() 应创建指示器并避免重复创建', () => {
      const indicators = document.querySelectorAll('.collapsed-indicator');
      expect(indicators.length).toBe(3);

      const groupsIndicator = layoutManager.indicators.get('groups');
      expect(groupsIndicator).toBeTruthy();
      expect(groupsIndicator.getAttribute('role')).toBe('button');
      expect(groupsIndicator.getAttribute('tabindex')).toBe('0');
      expect(groupsIndicator.getAttribute('aria-label')).toBe('展开分组面板');
      expect(groupsIndicator.querySelector('.indicator-text').textContent).toBe('分组');

      const before = document.querySelectorAll('.collapsed-indicator').length;
      layoutManager.ensureCollapsedIndicators();
      const after = document.querySelectorAll('.collapsed-indicator').length;
      expect(after).toBe(before);
    });

    test('点击/键盘操作折叠指示器应展开面板（TASK-03-004）', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      const indicator = layoutManager.indicators.get('groups');

      layoutManager.collapsePanel('groups', true);
      expect(panel.classList.contains('collapsed')).toBe(true);

      indicator.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      expect(panel.classList.contains('collapsed')).toBe(false);

      layoutManager.collapsePanel('groups', true);
      expect(panel.classList.contains('collapsed')).toBe(true);

      indicator.dispatchEvent(
        new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter' })
      );
      expect(panel.classList.contains('collapsed')).toBe(false);
    });

    test('onIndicatorClick()/onIndicatorKeydown() 无效参数应安全返回', () => {
      expect(() => layoutManager.onIndicatorClick(null)).not.toThrow();
      expect(() =>
        layoutManager.onIndicatorClick({
          currentTarget: { dataset: {} },
          preventDefault: () => {}
        })
      ).not.toThrow();

      expect(() => layoutManager.onIndicatorKeydown(null)).not.toThrow();
      expect(() =>
        layoutManager.onIndicatorKeydown({
          key: 'ArrowRight',
          preventDefault: () => {},
          currentTarget: {}
        })
      ).not.toThrow();
    });

    test('updateCollapsedIndicatorOffsets() 多面板折叠时应设置不同偏移', () => {
      const groupsIndicator = layoutManager.indicators.get('groups');
      const accountsIndicator = layoutManager.indicators.get('accounts');

      layoutManager.collapsePanel('groups', true);
      layoutManager.collapsePanel('accounts', true);

      expect(groupsIndicator.style.getPropertyValue('--collapsed-indicator-offset')).toBe(
        '0px'
      );
      expect(accountsIndicator.style.getPropertyValue('--collapsed-indicator-offset')).toBe(
        '48px'
      );

      // 覆盖 parsed 分支：自定义指示器宽度
      document.documentElement.style.setProperty('--panel-collapsed-indicator-width', '60px');
      layoutManager.updateCollapsedIndicatorOffsets();
      expect(accountsIndicator.style.getPropertyValue('--collapsed-indicator-offset')).toBe(
        '60px'
      );
    });

    test('syncAllPanelsLayoutVars() 应覆盖折叠分支', () => {
      layoutManager.collapsePanel('groups', true);
      layoutManager.syncAllPanelsLayoutVars();
      expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
        '0px'
      );
    });

    test('getPanelLayoutWidth() 面板折叠时应返回 0', () => {
      const panel = document.querySelector('[data-panel="groups"]');
      layoutManager.collapsePanel('groups', true);
      expect(layoutManager.getPanelLayoutWidth('groups', panel)).toBe(0);
    });

    test('updatePanelWidth() 在折叠状态下不应覆盖布局宽度变量', () => {
      const panel = document.querySelector('[data-panel="groups"]');

      layoutManager.collapsePanel('groups', true);
      expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
        '0px'
      );

      layoutManager.updatePanelWidth(panel, 250);
      expect(document.documentElement.style.getPropertyValue('--group-panel-width')).toBe('250px');
      expect(document.documentElement.style.getPropertyValue('--group-panel-layout-width')).toBe(
        '0px'
      );
    });

    test('getContainerWidth() 应覆盖 rect 与 0 的分支', () => {
      layoutManager.container.getBoundingClientRect = () => ({ width: 999 });
      expect(layoutManager.getContainerWidth()).toBe(999);

      // 无容器 + innerWidth 非数字 => 0
      layoutManager.container = null;
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 'abc'
      });
      expect(layoutManager.getContainerWidth()).toBe(0);
    });

    test('startResize() 应忽略非左键点击', async () => {
      const resizer = document.querySelector('[data-resizer="groups"]');

      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 1 })
      );
      document.dispatchEvent(
        new MouseEvent('mousemove', { bubbles: true, clientX: 250 })
      );
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

      await wait(30);
      expect(getCSSVariable('--group-panel-width')).toBe('200px');
    });

    test('resize() 在未开始拖动时应直接返回', () => {
      expect(() => layoutManager.resize(new MouseEvent('mousemove'))).not.toThrow();
      expect(layoutManager.rafId).toBe(0);
    });

    test('resize() 同一帧内应只调度一次 requestAnimationFrame', async () => {
      const resizer = document.querySelector('[data-resizer="groups"]');
      const rafSpy = jest.spyOn(global, 'requestAnimationFrame');

      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
      );
      document.dispatchEvent(
        new MouseEvent('mousemove', { bubbles: true, clientX: 240 })
      );
      document.dispatchEvent(
        new MouseEvent('mousemove', { bubbles: true, clientX: 250 })
      );

      expect(rafSpy).toHaveBeenCalledTimes(1);

      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      await wait(30);
      rafSpy.mockRestore();
    });

    test('stopResize() 在未开始拖动时应直接返回', () => {
      expect(() => layoutManager.stopResize()).not.toThrow();
    });

    test('stopResize() 在无 mousemove 时不应进入 raf flush 分支', async () => {
      const resizer = document.querySelector('[data-resizer="groups"]');

      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
      );
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

      await wait(30);
      expect(getCSSVariable('--group-panel-width')).toBe('200px');
    });

    test('getPanelWidth() 在 CSS 变量无法解析时应回退到 getBoundingClientRect', () => {
      const panel = document.createElement('div');
      panel.getBoundingClientRect = () => ({ width: 123 });
      expect(layoutManager.getPanelWidth('unknown', panel)).toBe(123);
    });

    test('getPanelWidth() 在 rect 无效时应回退到 offsetWidth', () => {
      const panel = document.createElement('div');
      panel.getBoundingClientRect = () => ({ width: 0 });
      Object.defineProperty(panel, 'offsetWidth', { value: 88 });
      expect(layoutManager.getPanelWidth('unknown', panel)).toBe(88);
    });

    test('getPanelWidth() 在 CSS 变量不可解析且无元素宽度时返回 0', () => {
      document.documentElement.style.setProperty('--group-panel-width', 'auto');
      expect(layoutManager.getPanelWidth('groups', null)).toBe(0);
    });

    test('startResize() panelType 无效/面板不存在时应安全返回', () => {
      expect(() =>
        layoutManager.startResize({
          button: 0,
          currentTarget: { dataset: { resizer: 'unknown' } },
          clientX: 0,
          preventDefault: () => {}
        })
      ).not.toThrow();

      expect(() =>
        layoutManager.startResize({
          button: 0,
          currentTarget: {},
          clientX: 0,
          preventDefault: () => {}
        })
      ).not.toThrow();
    });

    test('拖动开始/结束应切换全局与 resizer 视觉反馈状态', async () => {
      const resizer = document.querySelector('[data-resizer="groups"]');

      expect(document.body.classList.contains('layout-resizing')).toBe(false);
      expect(resizer.classList.contains('active')).toBe(false);

      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
      );

      expect(document.body.classList.contains('layout-resizing')).toBe(true);
      expect(resizer.classList.contains('active')).toBe(true);

      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      await wait(30);

      expect(document.body.classList.contains('layout-resizing')).toBe(false);
      expect(resizer.classList.contains('active')).toBe(false);
    });
  });
});
