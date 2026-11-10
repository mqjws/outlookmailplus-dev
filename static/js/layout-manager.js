/**
 * LayoutManager - 可调整布局系统的前端管理器
 *
 * 职责（按文档逐步实现）：
 * - 绑定 resizer 拖动事件，实时更新 CSS 变量（TASK-02-002 ~）
 * - 处理面板折叠/展开（TASK-03-001 ~）
 * - 与 StateManager 协作进行状态持久化（TASK-04-001 ~）
 * - 处理窗口断点自适应与键盘可访问性（TASK-06-001 ~）
 *
 * 当前文件实现范围：TASK-02-001（基础结构 + init + 宽度上下限 + 更新宽度）。
 *
 * 兼容性说明：
 * - 浏览器环境：通过 <script> 引入后，LayoutManager 挂载到 window.LayoutManager。
 * - 测试/Node 环境：如果存在 module.exports，则导出 LayoutManager 以便 Jest 直接 require。
 */

(function (global) {
  'use strict';

  // 为避免在 Jest/jsdom 多次 init() 时累积 beforeunload 监听器，这里用模块级变量记录最后一次绑定的处理函数。
  let LAST_BEFORE_UNLOAD_HANDLER = null;
  // 同上：避免多次 init() 叠加 window.resize 监听器导致测试/运行时重复执行。
  let LAST_WINDOW_RESIZE_HANDLER = null;

  /**
   * 将 data-panel 值映射到 CSS 变量名。
   * 注意：data-panel 使用复数（groups/accounts/emails），CSS 变量按 TDD 使用单数/固定命名。
   */
  const PANEL_WIDTH_VAR_MAP = {
    groups: '--group-panel-width',
    accounts: '--account-panel-width',
    emails: '--email-list-panel-width'
  };

  /**
   * 面板“布局生效宽度”CSS 变量映射。
   *
   * 说明：
   * - width 变量（--*-panel-width）用于“保存的宽度”（用于展开恢复/状态持久化）。
   * - layout-width 变量（--*-panel-layout-width）用于“当前参与 Grid 计算的宽度”。
   *   折叠时该值会变为 0，从而触发 Grid 列宽动画，但保存宽度不丢失。
   */
  const PANEL_LAYOUT_WIDTH_VAR_MAP = {
    groups: '--group-panel-layout-width',
    accounts: '--account-panel-layout-width',
    emails: '--email-list-panel-layout-width'
  };

  /**
   * 面板“布局生效最小宽度”CSS 变量映射（折叠时需要允许列宽收缩到 0）
   */
  const PANEL_LAYOUT_MIN_WIDTH_VAR_MAP = {
    groups: '--group-panel-layout-min-width',
    accounts: '--account-panel-layout-min-width',
    emails: '--email-list-panel-layout-min-width'
  };

  /**
   * LayoutManager
   */
  class LayoutManager {
    constructor() {
      /** @type {boolean} 是否处于拖动中（后续任务使用） */
      this.isResizing = false;

      /** @type {HTMLElement|null} 主容器 */
      this.container = null;

      /** @type {Map<string, HTMLElement>} data-panel -> panel element */
      this.panels = new Map();

      /** @type {Map<string, HTMLElement>} data-resizer -> resizer element */
      this.resizers = new Map();

      /** @type {Map<string, HTMLElement>} data-panel -> collapsed indicator element */
      this.indicators = new Map();

      /** @type {any|null} 状态管理器实例（TASK-04-001） */
      this.stateManager = null;

      /** @type {{debounced: Function, flush: Function}|null} 保存防抖器（TASK-04-002） */
      this.saveDebouncer = null;

      /** @type {HTMLElement|null} 当前正在调整的面板 */
      this.currentPanel = null;

      /** @type {HTMLElement|null} 当前正在拖动的 resizer */
      this.currentResizer = null;

      /** @type {string|null} 当前正在调整的面板类型（data-panel 值） */
      this.currentPanelType = null;

      /** @type {number} 拖动起始 X 坐标 */
      this.startX = 0;

      /** @type {number} 拖动起始宽度（px） */
      this.startWidth = 0;

      /** @type {number} requestAnimationFrame id */
      this.rafId = 0;

      /** @type {number} resize 期间最新的 clientX */
      this.pendingClientX = 0;

      // 绑定事件处理函数（避免反复 bind 造成性能开销）
      this._onStartResize = this.startResize.bind(this);
      this._onResize = this.resize.bind(this);
      this._onStopResize = this.stopResize.bind(this);
      this._onCollapseClick = this.onCollapseButtonClick.bind(this);
      this._onIndicatorClick = this.onIndicatorClick.bind(this);
      this._onIndicatorKeydown = this.onIndicatorKeydown.bind(this);
      this._onBeforeUnload = this.saveStateNow.bind(this);
      this._onResizerKeydown = this.onResizerKeydown.bind(this);
      this._onWindowResize = this.onWindowResize.bind(this);

      // 初始化状态管理器（浏览器环境优先使用 window.StateManager；Node/Jest 环境回退 require）
      this.stateManager = this.createStateManager();
      // 初始化防抖保存（拖动结束 500ms 后保存）
      this.saveDebouncer = this.debounce(() => this.saveState(), 500);
      // 窗口 resize 防抖（200ms，FD F5.1）
      this.windowResizeDebouncer = this.debounce(() => this.handleWindowResize(), 200);
    }

    /**
     * 初始化（缓存 DOM 引用；事件绑定在后续 TASK 中实现）
     * @returns {LayoutManager}
     */
    init() {
      this.container = document.querySelector('.main-container');

      // 缓存可调整面板
      this.panels.clear();
      document
        .querySelectorAll('.resizable-panel[data-panel]')
        .forEach((panel) => {
          this.panels.set(panel.dataset.panel, panel);
        });

      // 缓存 resizer
      this.resizers.clear();
      document.querySelectorAll('.resizer[data-resizer]').forEach((resizer) => {
        this.resizers.set(resizer.dataset.resizer, resizer);
      });

      // 绑定 resizer 的 mousedown 事件（mousemove/mouseup 在 startResize 中绑定到 document）
      this.resizers.forEach((resizer) => {
        resizer.removeEventListener('mousedown', this._onStartResize);
        resizer.addEventListener('mousedown', this._onStartResize);

        // 键盘支持（F6.1）：方向键调整宽度
        resizer.removeEventListener('keydown', this._onResizerKeydown);
        resizer.addEventListener('keydown', this._onResizerKeydown);
      });

      // 绑定折叠按钮点击事件（TASK-03-002）
      document.querySelectorAll('.collapse-btn[data-panel]').forEach((btn) => {
        btn.removeEventListener('click', this._onCollapseClick);
        btn.addEventListener('click', this._onCollapseClick);
      });

      // 初始化折叠指示器（TASK-03-004）
      this.ensureCollapsedIndicators();

      // 加载保存的状态（TASK-04-003）
      const loaded = this.loadState();
      if (!loaded) {
        // 初始化“布局生效”CSS 变量（避免折叠/展开后在无 CSS 环境下状态不一致；也便于测试）
        this.syncAllPanelsLayoutVars();

        // 初始化指示器偏移（避免多个折叠指示器重叠）
        this.updateCollapsedIndicatorOffsets();
      }

      // 页面卸载时强制保存（TASK-04-002）
      if (global && typeof global.addEventListener === 'function') {
        if (LAST_BEFORE_UNLOAD_HANDLER) {
          global.removeEventListener('beforeunload', LAST_BEFORE_UNLOAD_HANDLER);
        }
        LAST_BEFORE_UNLOAD_HANDLER = this._onBeforeUnload;
        global.addEventListener('beforeunload', LAST_BEFORE_UNLOAD_HANDLER);
      }

      // 窗口尺寸适配（F5）：resize 监听 + 初始适配
      if (global && typeof global.addEventListener === 'function') {
        if (LAST_WINDOW_RESIZE_HANDLER) {
          global.removeEventListener('resize', LAST_WINDOW_RESIZE_HANDLER);
        }
        LAST_WINDOW_RESIZE_HANDLER = this._onWindowResize;
        global.addEventListener('resize', LAST_WINDOW_RESIZE_HANDLER);
      }

      // 初始适配：避免页面加载时闪烁
      this.withNoTransition(() => {
        this.handleWindowResize();
      });

      return this;
    }

    /**
     * 创建 StateManager 实例（存在则返回，否则返回 null）
     * @returns {any|null}
     */
    createStateManager() {
      try {
        if (global && typeof global.StateManager === 'function') {
          return new global.StateManager();
        }

        // Jest/Node 环境下可直接 require（浏览器中 require 不存在）
        if (typeof require !== 'undefined') {
          // eslint-disable-next-line global-require, import/no-dynamic-require
          const StateManagerCtor = require('./state-manager.js');
          if (typeof StateManagerCtor === 'function') {
            return new StateManagerCtor();
          }
        }
      } catch (e) {
        try {
          // eslint-disable-next-line no-console
          console.warn('[LayoutManager] createStateManager failed:', e);
        } catch (_) {
          // ignore
        }
      }
      return null;
    }

    /**
     * 防抖工具（返回 { debounced, flush }），用于减少 localStorage 写入次数
     * @param {Function} func
     * @param {number} delay
     * @returns {{debounced: Function, flush: Function}}
     */
    debounce(func, delay) {
      let timerId = null;

      return {
        debounced: (...args) => {
          if (timerId) clearTimeout(timerId);
          timerId = setTimeout(() => {
            timerId = null;
            func(...args);
          }, delay);
        },
        flush: (...args) => {
          if (timerId) {
            clearTimeout(timerId);
            timerId = null;
          }
          func(...args);
        },
        cancel: () => {
          if (timerId) {
            clearTimeout(timerId);
            timerId = null;
          }
        }
      };
    }

    /**
     * 构建当前布局状态对象（LayoutState）
     * @param {string} userId
     * @returns {Record<string, any>}
     */
    buildLayoutState(userId) {
      const panels = {};
      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);

        // width：始终保存“保存宽度”变量（不是 0px 的 layout-width）
        const widthVar = PANEL_WIDTH_VAR_MAP[panelType];
        const rawWidth =
          (widthVar &&
            getComputedStyle(document.documentElement).getPropertyValue(widthVar)) ||
          '';
        const parsedWidth = this.parsePx(rawWidth);

        // 若无法解析，则回退到默认值（与 layout.css 一致）
        const defaultWidthMap = { groups: 200, accounts: 260, emails: 380 };
        const width = `${parsedWidth !== null ? parsedWidth : defaultWidthMap[panelType]}px`;

        // collapsed：仅保存用户手动折叠状态；自动折叠（data-autoCollapsed）不持久化
        const isCollapsed =
          !!panel &&
          panel.classList.contains('collapsed') &&
          panel.dataset.autoCollapsed !== 'true';

        panels[panelType] = { width, collapsed: isCollapsed };
      });

      return {
        version: '1.1',
        userId: userId || 'guest',
        timestamp: Date.now(),
        panels
      };
    }

    /**
     * 获取当前用户 ID（TASK-04-004）
     *
     * 说明（按 FD F4.3 / PRD 3.4.3）：
     * - localStorage key 需要包含用户 ID，以支持同一浏览器内的多用户隔离。
     * - 当前项目未必有完整的用户系统，因此这里提供多种“可选来源”，若均不可用则回退为 guest。
     *
     * 来源优先级：
     * 1) 页面元素：<body data-user-id="..."> 或 <html data-user-id="...">
     * 2) 全局变量：window.currentUserId
     * 3) meta：<meta name="outlook-user-id" content="...">
     *
     * @returns {string|null}
     */
    getCurrentUserId() {
      try {
        const normalize = (value) => {
          if (value === null || value === undefined) return null;
          const text = String(value).trim();
          return text ? text : null;
        };

        // 1) data-user-id（推荐：无需内联脚本即可由后端模板注入）
        if (typeof document !== 'undefined') {
          const bodyId =
            document.body && document.body.dataset ? document.body.dataset.userId : null;
          const normalizedBodyId = normalize(bodyId);
          if (normalizedBodyId) return normalizedBodyId;

          const htmlId =
            document.documentElement && document.documentElement.dataset
              ? document.documentElement.dataset.userId
              : null;
          const normalizedHtmlId = normalize(htmlId);
          if (normalizedHtmlId) return normalizedHtmlId;

          // 3) meta
          const meta =
            typeof document.querySelector === 'function'
              ? document.querySelector('meta[name="outlook-user-id"]')
              : null;
          const metaId = meta ? meta.getAttribute('content') : null;
          const normalizedMetaId = normalize(metaId);
          if (normalizedMetaId) return normalizedMetaId;
        }

        // 2) 全局变量
        const globalId = global ? global.currentUserId : null;
        const normalizedGlobalId = normalize(globalId);
        if (normalizedGlobalId) return normalizedGlobalId;
      } catch (_) {
        // ignore
      }

      return null;
    }

    /**
     * 保存当前布局状态到 localStorage（TASK-04-002）
     * @returns {boolean}
     */
    saveState() {
      if (!this.stateManager || typeof this.stateManager.save !== 'function') return false;

      const userId = this.getCurrentUserId() || 'guest';
      const state = this.buildLayoutState(userId);
      return !!this.stateManager.save(userId, state);
    }

    /**
     * 立即保存（用于 beforeunload / 折叠等需要“立刻落盘”的场景）
     * @returns {boolean}
     */
    saveStateNow() {
      if (!this.saveDebouncer) return this.saveState();

      // flush 会清理 pending timer，并立即执行保存
      return !!this.saveDebouncer.flush();
    }

    /**
     * 从 localStorage 加载并应用状态（TASK-04-003）
     *
     * 说明：
     * - StateManager 会负责 validate/migrate；此处只应用已验证的数据。
     * - 恢复时应禁用动画，避免页面加载时闪烁（FD F4.2）。
     *
     * @returns {boolean} 是否成功加载并应用
     */
    loadState() {
      if (!this.stateManager || typeof this.stateManager.load !== 'function') return false;

      const userId = this.getCurrentUserId() || 'guest';
      const state = this.stateManager.load(userId);
      if (!state || !state.panels) return false;

      this.withNoTransition(() => {
        this.applyLayoutState(state);

        // 应用完 collapsed 类后，再同步布局变量与指示器偏移（避免过渡动画）
        this.syncAllPanelsLayoutVars();
        this.updateCollapsedIndicatorOffsets();
      });

      return true;
    }

    /**
     * 临时禁用布局相关 transition，用于状态恢复时避免闪烁
     * @param {Function} fn
     */
    withNoTransition(fn) {
      const root =
        typeof document !== 'undefined' && document.documentElement
          ? document.documentElement
          : null;
      if (!root || !root.classList) {
        fn();
        return;
      }

      root.classList.add('layout-no-transition');
      try {
        fn();
      } finally {
        const remove = () => {
          try {
            root.classList.remove('layout-no-transition');
          } catch (_) {
            // ignore
          }
        };

        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(remove);
        } else {
          setTimeout(remove, 0);
        }
      }
    }

    /**
     * 临时开启“重置动画”时长（300ms），用于恢复默认布局（FD F3.4）
     * @param {Function} fn
     */
    withResettingAnimation(fn) {
      const root =
        typeof document !== 'undefined' && document.documentElement
          ? document.documentElement
          : null;
      if (!root || !root.classList) {
        fn();
        return;
      }

      root.classList.add('layout-resetting');
      try {
        fn();
      } finally {
        // 保持一小段时间，确保过渡动画完整执行；不依赖 transitionend（避免多属性触发复杂度）
        setTimeout(() => {
          try {
            root.classList.remove('layout-resetting');
          } catch (_) {
            // ignore
          }
        }, 350);
      }
    }

    /**
     * 恢复默认布局（F3）
     *
     * 说明：
     * - 清除 localStorage 中保存的布局状态
     * - 恢复默认宽度（200/260/380）并展开所有侧边栏面板
     * - 不主动写回 localStorage（保持“清除状态”的语义）
     *
     * @returns {void}
     */
    resetLayout() {
      // 避免 reset 过程中触发“拖动后 500ms 保存”的残留定时器把默认值又写回 storage
      if (this.saveDebouncer && typeof this.saveDebouncer.cancel === 'function') {
        this.saveDebouncer.cancel();
      }

      const userId = this.getCurrentUserId() || 'guest';
      try {
        if (this.stateManager && typeof this.stateManager.clear === 'function') {
          this.stateManager.clear(userId);
        }
      } catch (_) {
        // ignore
      }

      const defaultWidthMap = { groups: 200, accounts: 260, emails: 380 };

      this.withResettingAnimation(() => {
        ['groups', 'accounts', 'emails'].forEach((panelType) => {
          const panel = this.panels.get(panelType);
          if (!panel) return;

          // 展开所有面板，并清理自动折叠标记
          delete panel.dataset.autoCollapsed;
          panel.classList.remove('collapsed');

          // 恢复默认宽度（同时更新 aria-valuenow）
          this.updatePanelWidth(panel, defaultWidthMap[panelType]);

          // 同步按钮的 ARIA/图标（避免依赖 click 流程导致保存）
          this.updateCollapseButtonState(panelType, false);
        });

        // 同步布局变量与指示器偏移（确保 Grid 列宽立即恢复）
        this.syncAllPanelsLayoutVars();
        this.updateCollapsedIndicatorOffsets();
      });

      this.notify('已恢复默认布局', 'success');
    }

    /**
     * 将已加载的 LayoutState 应用到 DOM/CSS 变量（不触发保存）
     * @param {Record<string, any>} state
     */
    applyLayoutState(state) {
      const panels = state && state.panels ? state.panels : null;
      if (!panels) return;

      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);
        const panelState = panels[panelType];
        if (!panel || !panelState) return;

        // width：恢复保存宽度（并裁剪到最小/最大范围，避免异常数据破坏布局）
        const parsedWidth = this.parsePx(panelState.width);
        if (parsedWidth !== null) {
          const min = this.getMinWidth(panelType);
          const max = this.getMaxWidth(panelType);
          const clamped = Math.max(min, Math.min(max, parsedWidth));
          this.updatePanelWidth(panel, clamped);
        }

        // 状态恢复属于用户偏好：移除 autoCollapsed 标记（后续窗口适配会重新打标）
        delete panel.dataset.autoCollapsed;

        // collapsed：只恢复用户手动折叠状态（StateManager 已保证是 boolean）
        if (panelState.collapsed) {
          panel.classList.add('collapsed');
          this.updateCollapseButtonState(panelType, true);
        } else {
          panel.classList.remove('collapsed');
          this.updateCollapseButtonState(panelType, false);
        }
      });
    }

    /**
     * 更新折叠按钮的图标与 ARIA（用于状态恢复，不触发保存/焦点移动）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @param {boolean} collapsed
     */
    updateCollapseButtonState(panelType, collapsed) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      const btn = panel.querySelector('.collapse-btn');
      if (!btn) return;

      if (collapsed) {
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute('aria-label', `展开${this.getPanelDisplayName(panelType)}面板`);
        btn.setAttribute('title', `展开${this.getPanelDisplayName(panelType)}面板`);
        btn.textContent = '→';
        return;
      }

      btn.setAttribute('aria-expanded', 'true');
      btn.setAttribute('aria-label', `折叠${this.getPanelDisplayName(panelType)}面板`);
      btn.setAttribute('title', `折叠${this.getPanelDisplayName(panelType)}面板`);
      btn.textContent = '←';
    }

    /**
     * 获取面板中文名称（用于 aria-label / 提示文案）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @returns {string}
     */
    getPanelDisplayName(panelType) {
      switch (panelType) {
        case 'groups':
          return '分组';
        case 'accounts':
          return '账号';
        case 'emails':
          return '邮件列表';
        default:
          return '面板';
      }
    }

    /**
     * 折叠按钮点击处理
     * @param {MouseEvent} e
     */
    onCollapseButtonClick(e) {
      const btn = e && e.currentTarget ? e.currentTarget : null;
      const panelType = btn && btn.dataset ? btn.dataset.panel : null;
      if (!panelType) return;

      e.preventDefault();
      this.togglePanel(panelType);
    }

    /**
     * 确保三侧边栏面板都存在折叠指示器（在 HTML 未提供时由 JS 动态创建）
     * @returns {void}
     */
    ensureCollapsedIndicators() {
      this.indicators.clear();

      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);
        if (!panel) return;

        let indicator = panel.querySelector(
          `.collapsed-indicator[data-panel="${panelType}"]`
        );
        if (!indicator) {
          indicator = document.createElement('div');
          indicator.className = 'collapsed-indicator';
          indicator.dataset.panel = panelType;
          indicator.setAttribute('role', 'button');
          indicator.setAttribute('tabindex', '0');
          indicator.setAttribute(
            'aria-label',
            `展开${this.getPanelDisplayName(panelType)}面板`
          );
          indicator.setAttribute(
            'title',
            `展开${this.getPanelDisplayName(panelType)}面板`
          );

          const text = document.createElement('span');
          text.className = 'indicator-text';
          text.textContent = this.getPanelDisplayName(panelType);
          indicator.appendChild(text);

          panel.appendChild(indicator);
        }

        indicator.removeEventListener('click', this._onIndicatorClick);
        indicator.addEventListener('click', this._onIndicatorClick);
        indicator.removeEventListener('keydown', this._onIndicatorKeydown);
        indicator.addEventListener('keydown', this._onIndicatorKeydown);

        this.indicators.set(panelType, indicator);
      });
    }

    /**
     * 折叠指示器点击：展开对应面板
     * @param {MouseEvent} e
     */
    onIndicatorClick(e) {
      const indicator = e && e.currentTarget ? e.currentTarget : null;
      const panelType = indicator && indicator.dataset ? indicator.dataset.panel : null;
      if (!panelType) return;

      e.preventDefault();
      this.expandPanel(panelType);
    }

    /**
     * 折叠指示器键盘支持：Enter/Space 展开
     * @param {KeyboardEvent} e
     */
    onIndicatorKeydown(e) {
      if (!e) return;
      const key = e.key;
      if (key !== 'Enter' && key !== ' ') return;

      e.preventDefault();
      this.onIndicatorClick({
        currentTarget: e.currentTarget,
        preventDefault: () => {}
      });
    }

    /**
     * 更新折叠指示器偏移，避免多个折叠指示器在同一 x 坐标重叠
     * @returns {void}
     */
    updateCollapsedIndicatorOffsets() {
      const indicatorWidth = this.getCollapsedIndicatorWidth();
      let offset = 0;

      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);
        const indicator = this.indicators.get(panelType);
        if (!panel || !indicator) return;

        if (panel.classList.contains('collapsed')) {
          indicator.style.setProperty('--collapsed-indicator-offset', `${offset}px`);
          offset += indicatorWidth;
        } else {
          indicator.style.removeProperty('--collapsed-indicator-offset');
        }
      });
    }

    /**
     * 获取折叠指示器宽度（px）
     * @returns {number}
     */
    getCollapsedIndicatorWidth() {
      const raw = getComputedStyle(document.documentElement).getPropertyValue(
        '--panel-collapsed-indicator-width'
      );
      const parsed = this.parsePx(raw);
      return parsed !== null ? parsed : 48;
    }

    /**
     * 获取面板最小宽度（px）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @returns {number}
     */
    getMinWidth(panelType) {
      switch (panelType) {
        case 'groups':
          return 150;
        case 'accounts':
          return 180;
        case 'emails':
          return 280;
        default:
          return 150;
      }
    }

    /**
     * 获取面板最大宽度（px）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @returns {number}
     */
    getMaxWidth(panelType) {
      switch (panelType) {
        case 'groups':
          return 400;
        case 'accounts':
          return 500;
        case 'emails':
          return 600;
        default:
          return 600;
      }
    }

    /**
     * 更新面板宽度（通过 CSS 变量）
     * @param {HTMLElement} panel 目标面板元素（必须包含 data-panel）
     * @param {number} width 新宽度（px）
     */
    updatePanelWidth(panel, width) {
      if (!panel || !panel.dataset || !panel.dataset.panel) return;
      if (typeof width !== 'number' || Number.isNaN(width)) return;

      const panelType = panel.dataset.panel;
      const cssVarName = PANEL_WIDTH_VAR_MAP[panelType];
      if (!cssVarName) return;

      document.documentElement.style.setProperty(cssVarName, `${width}px`);

      // 如果面板当前是展开状态，同步更新“布局生效宽度”变量，保证 Grid 立即生效
      const layoutWidthVar = PANEL_LAYOUT_WIDTH_VAR_MAP[panelType];
      if (layoutWidthVar && !panel.classList.contains('collapsed')) {
        document.documentElement.style.setProperty(layoutWidthVar, `${width}px`);
      }

      // 同步更新 resizer 的 ARIA（便于后续键盘支持与可访问性测试）
      const resizer = this.resizers.get(panelType);
      if (resizer) {
        resizer.setAttribute('aria-valuenow', String(Math.round(width)));
      }
    }

    /**
     * 同步所有面板的“布局生效宽度/最小宽度”CSS 变量（TASK-03-003）
     *
     * 目的：
     * - 折叠时 Grid 列宽应允许收缩到 0（因此 layout-min-width 需要变为 0）
     * - 展开时 Grid 列宽应恢复为保存宽度（layout-width = saved width）
     */
    syncAllPanelsLayoutVars() {
      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);
        if (!panel) return;

        if (panel.classList.contains('collapsed')) {
          this.applyCollapsedLayoutVars(panelType);
        } else {
          this.applyExpandedLayoutVars(panelType);
        }
      });
    }

    /**
     * 获取“保存宽度”CSS 变量值（如 "200px"）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @returns {string|null}
     */
    getSavedWidthCssValue(panelType) {
      const varName = PANEL_WIDTH_VAR_MAP[panelType];
      if (!varName) return null;

      const raw = getComputedStyle(document.documentElement).getPropertyValue(varName);
      const parsed = this.parsePx(raw);
      if (parsed === null) return null;
      return `${parsed}px`;
    }

    /**
     * 应用展开状态下的布局变量（layout-width/layout-min-width）
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    applyExpandedLayoutVars(panelType) {
      const layoutWidthVar = PANEL_LAYOUT_WIDTH_VAR_MAP[panelType];
      const layoutMinVar = PANEL_LAYOUT_MIN_WIDTH_VAR_MAP[panelType];
      if (!layoutWidthVar || !layoutMinVar) return;

      const savedWidth = this.getSavedWidthCssValue(panelType);
      if (savedWidth) {
        document.documentElement.style.setProperty(layoutWidthVar, savedWidth);
      }
      document.documentElement.style.setProperty(
        layoutMinVar,
        `${this.getMinWidth(panelType)}px`
      );
    }

    /**
     * 应用折叠状态下的布局变量（layout-width/layout-min-width）
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    applyCollapsedLayoutVars(panelType) {
      const layoutWidthVar = PANEL_LAYOUT_WIDTH_VAR_MAP[panelType];
      const layoutMinVar = PANEL_LAYOUT_MIN_WIDTH_VAR_MAP[panelType];
      if (!layoutWidthVar || !layoutMinVar) return;

      document.documentElement.style.setProperty(layoutWidthVar, '0px');
      document.documentElement.style.setProperty(layoutMinVar, '0px');
    }

    /**
     * 获取当前参与布局计算的面板宽度（px）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @param {HTMLElement} panelElement
     * @returns {number}
     */
    getPanelLayoutWidth(panelType, panelElement) {
      if (
        panelElement &&
        panelElement.classList &&
        (panelElement.classList.contains('collapsed') ||
          panelElement.classList.contains('hidden'))
      ) {
        return 0;
      }

      // 展开状态下，“保存宽度”就是当前生效宽度（layout-width 主要用于折叠时置 0）
      return this.getPanelWidth(panelType, panelElement);
    }

    /**
     * 折叠指定面板
     *
     * 注意：折叠规则（至少保留一个面板展开）、自动折叠标记（data-autoCollapsed）、
     * 指示条（collapsed-indicator）等在后续 TASK 中实现。
     *
     * @param {'groups'|'accounts'|'emails'} panelType
     * @param {boolean} [auto=false] 预留参数（后续用于标记自动折叠）
     */
    collapsePanel(panelType, auto = false) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      // 折叠规则：至少保持一个侧边栏面板展开（仅限制用户手动折叠；自动折叠可例外）
      if (!auto && !panel.classList.contains('collapsed')) {
        const expandedPanels = this.getExpandedPanels();
        if (expandedPanels.length <= 1 && expandedPanels[0] === panelType) {
          this.notify('至少需要保持一个面板展开', 'warning');
          return;
        }
      }

      // 标记自动折叠（用于窗口适配时的“仅恢复自动折叠”逻辑，TASK-03-007）
      if (auto) {
        panel.dataset.autoCollapsed = 'true';
      } else {
        delete panel.dataset.autoCollapsed;
      }

      panel.classList.add('collapsed');
      this.applyCollapsedLayoutVars(panelType);
      this.updateCollapsedIndicatorOffsets();

      const btn = panel.querySelector('.collapse-btn');
      if (btn) {
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute(
          'aria-label',
          `展开${this.getPanelDisplayName(panelType)}面板`
        );
        btn.setAttribute(
          'title',
          `展开${this.getPanelDisplayName(panelType)}面板`
        );
        btn.textContent = '→';
      }

      // 焦点管理：用户手动折叠后，将焦点移到指示器（自动折叠不抢焦点）
      if (!auto) {
        const indicator = this.indicators.get(panelType);
        if (indicator && typeof indicator.focus === 'function') {
          indicator.focus();
        }
      }

      // 折叠后立即保存（自动折叠不保存，TASK-04-002 / FD F5.2）
      if (!auto) {
        this.saveStateNow();
      }
    }

    /**
     * 展开指定面板
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    expandPanel(panelType, auto = false) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      // 展开时移除自动折叠标记（TASK-03-007）
      delete panel.dataset.autoCollapsed;

      panel.classList.remove('collapsed');
      this.applyExpandedLayoutVars(panelType);
      this.updateCollapsedIndicatorOffsets();

      const btn = panel.querySelector('.collapse-btn');
      if (btn) {
        btn.setAttribute('aria-expanded', 'true');
        btn.setAttribute(
          'aria-label',
          `折叠${this.getPanelDisplayName(panelType)}面板`
        );
        btn.setAttribute(
          'title',
          `折叠${this.getPanelDisplayName(panelType)}面板`
        );
        btn.textContent = '←';
        // 展开后焦点回到折叠按钮（便于键盘连续操作）；自动展开不抢焦点
        if (!auto && typeof btn.focus === 'function') {
          btn.focus();
        }
      }

      // 自动展开属于响应式行为，不应持久化；手动展开才保存（TASK-04-002）
      if (!auto) {
        this.saveStateNow();
      }
    }

    /**
     * 获取当前处于展开状态的侧边栏面板列表
     * @returns {Array<'groups'|'accounts'|'emails'>}
     */
    getExpandedPanels() {
      /** @type {Array<'groups'|'accounts'|'emails'>} */
      const expanded = [];
      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        const panel = this.panels.get(panelType);
        if (!panel) return;
        if (!panel.classList.contains('collapsed')) {
          expanded.push(panelType);
        }
      });
      return expanded;
    }

    /**
     * 显示提示信息（优先使用主应用内置的 showToast；不可用时降级为 alert）
     * @param {string} message
     * @param {'info'|'success'|'warning'|'error'} [type='warning']
     */
    notify(message, type = 'warning') {
      try {
        if (typeof window !== 'undefined' && typeof window.showToast === 'function') {
          window.showToast(message, type);
          return;
        }
      } catch (_) {
        // ignore
      }

      try {
        if (typeof window !== 'undefined' && typeof window.alert === 'function') {
          window.alert(message);
        }
      } catch (_) {
        // ignore
      }
    }

    /**
     * 切换面板折叠状态
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    togglePanel(panelType) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      if (panel.classList.contains('collapsed')) {
        this.expandPanel(panelType);
      } else {
        this.collapsePanel(panelType, false);
      }
    }

    /**
     * window.resize 事件处理（防抖 200ms）
     */
    onWindowResize() {
      if (!this.windowResizeDebouncer) {
        this.handleWindowResize();
        return;
      }
      this.windowResizeDebouncer.debounced();
    }

    /**
     * 根据断点自动折叠/恢复面板（F5）
     *
     * 规则：
     * - <1200：自动折叠 groups
     * - <900：自动折叠 accounts
     * - <700：自动折叠 emails
     * - 仅恢复“自动折叠”的面板（data-autoCollapsed="true"），不恢复用户手动折叠
     */
    handleWindowResize() {
      if (typeof window === 'undefined' || typeof window.innerWidth !== 'number') return;

      const width = window.innerWidth;
      if (!Number.isFinite(width) || width <= 0) return;

      const shouldCollapseGroups = width < 1200;
      const shouldCollapseAccounts = width < 900;
      const shouldCollapseEmails = width < 700;

      if (shouldCollapseGroups) {
        this.autoCollapsePanelIfNeeded('groups');
      } else {
        this.restorePanelIfNeeded('groups');
      }

      if (shouldCollapseAccounts) {
        this.autoCollapsePanelIfNeeded('accounts');
      } else {
        this.restorePanelIfNeeded('accounts');
      }

      if (shouldCollapseEmails) {
        this.autoCollapsePanelIfNeeded('emails');
      } else {
        this.restorePanelIfNeeded('emails');
      }
    }

    /**
     * 自动折叠面板（不保存；且不覆盖用户手动折叠标记）
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    autoCollapsePanelIfNeeded(panelType) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      // emailListPanel 可能被业务逻辑临时隐藏（display:none）；此时不参与断点折叠/恢复
      if (panel.classList && panel.classList.contains('hidden')) return;

      // 已折叠（可能是用户手动折叠），不要改写为 autoCollapsed
      if (panel.classList && panel.classList.contains('collapsed')) return;

      this.collapsePanel(panelType, true);
    }

    /**
     * 恢复面板（仅恢复自动折叠的；不保存）
     * @param {'groups'|'accounts'|'emails'} panelType
     */
    restorePanelIfNeeded(panelType) {
      const panel = this.panels.get(panelType);
      if (!panel) return;

      if (panel.classList && panel.classList.contains('hidden')) return;

      const isAutoCollapsed = panel.dataset && panel.dataset.autoCollapsed === 'true';
      if (!isAutoCollapsed) return;

      if (panel.classList && panel.classList.contains('collapsed')) {
        this.expandPanel(panelType, true);
      }
    }

    /**
     * Resizer 键盘支持：方向键调整宽度（F6.1）
     * @param {KeyboardEvent} e
     */
    onResizerKeydown(e) {
      if (!e) return;

      const key = e.key;
      if (key !== 'ArrowLeft' && key !== 'ArrowRight') return;

      const resizer = e.currentTarget;
      const panelType = resizer && resizer.dataset ? resizer.dataset.resizer : null;
      if (!panelType) return;

      const panel = this.panels.get(panelType);
      if (!panel) return;
      if (panel.classList && panel.classList.contains('collapsed')) return;

      const step = e.shiftKey ? 50 : 10;
      const delta = key === 'ArrowLeft' ? -step : step;

      e.preventDefault();

      const startWidth = this.getPanelLayoutWidth(panelType, panel);
      const nextWidth = this.calculateNewWidth(0, delta, startWidth, panelType);
      this.updatePanelWidth(panel, nextWidth);

      // 键盘调整也应触发防抖保存（F6.1）
      if (this.saveDebouncer && this.stateManager) {
        this.saveDebouncer.debounced();
      }
    }

    /**
     * mousedown：开始拖动调整
     * @param {MouseEvent} e
     */
    startResize(e) {
      // 仅响应鼠标左键
      if (e && typeof e.button === 'number' && e.button !== 0) return;

      const resizer = e.currentTarget;
      const panelType = resizer && resizer.dataset ? resizer.dataset.resizer : null;
      if (!panelType) return;

      const panel = this.panels.get(panelType);
      if (!panel) return;
      // 折叠状态下禁止拖动（与 F2.5/F2.6 一致）
      if (panel.classList.contains('collapsed')) return;

      e.preventDefault();

      // 视觉反馈：全局光标 + 禁止选中文本
      if (document.body) {
        document.body.classList.add('layout-resizing');
      }

      this.isResizing = true;
      this.currentPanelType = panelType;
      this.currentPanel = panel;
      this.currentResizer = resizer;
      if (this.currentResizer && this.currentResizer.classList) {
        this.currentResizer.classList.add('active');
      }
      this.startX = e.clientX;
      this.pendingClientX = e.clientX;
      this.startWidth = this.getPanelLayoutWidth(panelType, panel);

      document.addEventListener('mousemove', this._onResize);
      document.addEventListener('mouseup', this._onStopResize);
      // 边界情况：鼠标移出窗口/窗口失焦时，确保拖动能正常结束（避免卡死在 resizing 状态）
      window.addEventListener('blur', this._onStopResize);
      document.addEventListener('mouseleave', this._onStopResize);
    }

    /**
     * mousemove：拖动中（使用 requestAnimationFrame 做节流）
     * @param {MouseEvent} e
     */
    resize(e) {
      if (!this.isResizing || !this.currentPanel || !this.currentPanelType) return;

      this.pendingClientX = e.clientX;

      if (this.rafId) return;
      this.rafId = requestAnimationFrame(() => {
        this.rafId = 0;
        if (!this.isResizing || !this.currentPanel || !this.currentPanelType) return;

        try {
          const newWidth = this.calculateNewWidth(
            this.startX,
            this.pendingClientX,
            this.startWidth,
            this.currentPanelType
          );
          this.updatePanelWidth(this.currentPanel, newWidth);
        } catch (err) {
          // 边界保护：任何异常都不应让页面卡在拖动状态
          try {
            // eslint-disable-next-line no-console
            console.error('[LayoutManager] resize failed:', err);
          } catch (_) {
            // ignore
          }
          this.stopResize();
        }
      });
    }

    /**
     * mouseup：结束拖动
     */
    stopResize() {
      if (!this.isResizing) return;

      // 如果在 mouseup 前还有一帧待执行，先同步刷新最终宽度，避免快速拖动时丢帧
      if (this.rafId && this.currentPanel && this.currentPanelType) {
        cancelAnimationFrame(this.rafId);
        this.rafId = 0;

        try {
          const finalWidth = this.calculateNewWidth(
            this.startX,
            this.pendingClientX,
            this.startWidth,
            this.currentPanelType
          );
          this.updatePanelWidth(this.currentPanel, finalWidth);
        } catch (err) {
          try {
            // eslint-disable-next-line no-console
            console.error('[LayoutManager] stopResize flush failed:', err);
          } catch (_) {
            // ignore
          }
        }
      }

      this.isResizing = false;
      this.currentPanel = null;
      this.currentPanelType = null;

      document.removeEventListener('mousemove', this._onResize);
      document.removeEventListener('mouseup', this._onStopResize);
      window.removeEventListener('blur', this._onStopResize);
      document.removeEventListener('mouseleave', this._onStopResize);

      // 清理视觉反馈
      if (this.currentResizer && this.currentResizer.classList) {
        this.currentResizer.classList.remove('active');
      }
      this.currentResizer = null;
      if (document.body) {
        document.body.classList.remove('layout-resizing');
      }

      // 拖动结束后 500ms 防抖保存（TASK-04-002）
      if (this.saveDebouncer && this.stateManager) {
        this.saveDebouncer.debounced();
      }
    }

    /**
     * 计算拖动后的新宽度（仅处理最小/最大约束；邮件详情 400px 约束在 TASK-02-003 实现）
     * @param {number} startX
     * @param {number} currentX
     * @param {number} startWidth
     * @param {'groups'|'accounts'|'emails'} panelType
     * @returns {number}
     */
    calculateNewWidth(startX, currentX, startWidth, panelType) {
      const delta = currentX - startX;
      let nextWidth = startWidth + delta;

      const minWidth = this.getMinWidth(panelType);
      const maxWidth = this.getMaxWidth(panelType);

      // 先按面板自身的最小/最大值裁剪
      nextWidth = Math.max(minWidth, Math.min(maxWidth, nextWidth));

      // 再保证邮件详情面板最小可见宽度（避免侧边栏把详情挤到不可读）
      const containerWidth = this.getContainerWidth();
      const detailMinWidth = this.getEmailDetailMinWidth();
      if (containerWidth > 0 && detailMinWidth > 0) {
        const otherPanelsWidth = this.calculateOtherPanelsWidth(panelType);
        const maxAllowedByDetail = containerWidth - otherPanelsWidth - detailMinWidth;
        if (Number.isFinite(maxAllowedByDetail)) {
          nextWidth = Math.min(nextWidth, maxAllowedByDetail);
          nextWidth = Math.max(minWidth, nextWidth);
        }
      }
      return nextWidth;
    }

    /**
     * 计算除当前面板外的其他侧边栏面板总宽度（px）
     * @param {'groups'|'accounts'|'emails'} excludePanelType
     * @returns {number}
     */
    calculateOtherPanelsWidth(excludePanelType) {
      let total = 0;
      ['groups', 'accounts', 'emails'].forEach((panelType) => {
        if (panelType === excludePanelType) return;
        const panel = this.panels.get(panelType);
        total += this.getPanelLayoutWidth(panelType, panel);
      });
      return total;
    }

    /**
     * 获取容器可用宽度（优先取 .main-container 的实际宽度；无布局时回退到 window.innerWidth）
     * @returns {number}
     */
    getContainerWidth() {
      if (this.container) {
        const rect = this.container.getBoundingClientRect
          ? this.container.getBoundingClientRect()
          : null;
        if (rect && typeof rect.width === 'number' && rect.width > 0) {
          return rect.width;
        }
      }
      if (typeof window !== 'undefined' && typeof window.innerWidth === 'number') {
        return window.innerWidth;
      }
      return 0;
    }

    /**
     * 获取邮件详情面板最小宽度（从 CSS 变量读取；缺失时默认 400）
     * @returns {number}
     */
    getEmailDetailMinWidth() {
      const raw = getComputedStyle(document.documentElement).getPropertyValue(
        '--email-detail-panel-min-width'
      );
      const parsed = this.parsePx(raw);
      return parsed !== null ? parsed : 400;
    }

    /**
     * 获取当前面板宽度（优先读取 CSS 变量，便于在 jsdom 中测试）
     * @param {'groups'|'accounts'|'emails'} panelType
     * @param {HTMLElement} panelElement
     * @returns {number}
     */
    getPanelWidth(panelType, panelElement) {
      const cssVarName = PANEL_WIDTH_VAR_MAP[panelType];
      const raw =
        (cssVarName &&
          getComputedStyle(document.documentElement).getPropertyValue(cssVarName)) ||
        '';
      const parsed = this.parsePx(raw);
      if (parsed !== null) return parsed;

      if (panelElement) {
        const rect = panelElement.getBoundingClientRect
          ? panelElement.getBoundingClientRect()
          : null;
        if (rect && typeof rect.width === 'number' && rect.width > 0) {
          return rect.width;
        }
        if (typeof panelElement.offsetWidth === 'number' && panelElement.offsetWidth > 0) {
          return panelElement.offsetWidth;
        }
      }

      return 0;
    }

    /**
     * 解析 "123px" 为 number；无法解析时返回 null
     * @param {string} value
     * @returns {number|null}
     */
    parsePx(value) {
      if (!value || typeof value !== 'string') return null;
      const trimmed = value.trim();
      if (!trimmed.endsWith('px')) return null;
      const num = Number.parseFloat(trimmed.slice(0, -2));
      return Number.isFinite(num) ? num : null;
    }
  }

  // 浏览器环境挂载
  global.LayoutManager = LayoutManager;

  // Jest/Node 环境导出
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = LayoutManager;
  }
})(typeof window !== 'undefined' ? window : globalThis);
