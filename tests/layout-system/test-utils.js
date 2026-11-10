/**
 * 测试辅助工具（布局系统）
 *
 * 说明：
 * - 本文件用于 Jest(jsdom) 环境下快速搭建 DOM、模拟事件、读取 CSS 变量。
 * - 测试用 DOM 结构尽量与 TDD 第八章的集成结构一致，便于后续集成/回归测试复用。
 */

/**
 * 创建完整的布局 DOM 结构
 */
function createLayoutDOM() {
  const html = `
    <div class="main-container">
      <!-- 分组面板 -->
      <div class="resizable-panel" data-panel="groups">
        <div class="panel-header">
          <h3>分组</h3>
          <button class="collapse-btn"
                  data-panel="groups"
                  aria-label="折叠分组面板"
                  aria-expanded="true">
            ←
          </button>
        </div>
        <div class="panel-content">
          <p>分组内容</p>
        </div>
        <div class="resizer"
             role="separator"
             aria-orientation="vertical"
             aria-label="调整分组面板宽度"
             aria-valuenow="200"
             aria-valuemin="150"
             aria-valuemax="400"
             tabindex="0"
             data-resizer="groups">
        </div>
      </div>

      <!-- 账号面板 -->
      <div class="resizable-panel" data-panel="accounts">
        <div class="panel-header">
          <h3>账号</h3>
          <button class="collapse-btn"
                  data-panel="accounts"
                  aria-label="折叠账号面板"
                  aria-expanded="true">
            ←
          </button>
        </div>
        <div class="panel-content">
          <p>账号内容</p>
        </div>
        <div class="resizer"
             role="separator"
             aria-orientation="vertical"
             aria-label="调整账号面板宽度"
             aria-valuenow="260"
             aria-valuemin="180"
             aria-valuemax="500"
             tabindex="0"
             data-resizer="accounts">
        </div>
      </div>

      <!-- 邮件列表面板 -->
      <div class="resizable-panel" data-panel="emails">
        <div class="panel-header">
          <h3>邮件列表</h3>
          <button class="collapse-btn"
                  data-panel="emails"
                  aria-label="折叠邮件列表面板"
                  aria-expanded="true">
            ←
          </button>
        </div>
        <div class="panel-content">
          <p>邮件列表内容</p>
        </div>
        <div class="resizer"
             role="separator"
             aria-orientation="vertical"
             aria-label="调整邮件列表面板宽度"
             aria-valuenow="380"
             aria-valuemin="280"
             aria-valuemax="600"
             tabindex="0"
             data-resizer="emails">
        </div>
      </div>

      <!-- 邮件详情面板（不可折叠） -->
      <div class="email-detail-panel">
        <div class="panel-header">
          <h3>邮件详情</h3>
        </div>
        <div class="panel-content">
          <p>邮件详情内容</p>
        </div>
      </div>
    </div>
  `;

  document.body.innerHTML = html;

  // 设置初始 CSS 变量（与 static/css/layout.css 命名保持一致）
  document.documentElement.style.setProperty('--group-panel-width', '200px');
  document.documentElement.style.setProperty('--account-panel-width', '260px');
  document.documentElement.style.setProperty('--email-list-panel-width', '380px');
}

/**
 * 创建简化的布局 DOM 结构（用于最小化单元测试场景）
 */
function createSimpleLayoutDOM() {
  const html = `
    <div class="main-container">
      <div class="resizable-panel" data-panel="groups">
        <div class="resizer" data-resizer="groups"></div>
      </div>
    </div>
  `;

  document.body.innerHTML = html;
  document.documentElement.style.setProperty('--group-panel-width', '200px');
}

/**
 * 获取 CSS 变量值
 * @param {string} varName 例如：--group-panel-width
 * @returns {string}
 */
function getCSSVariable(varName) {
  return document.documentElement.style.getPropertyValue(varName).trim();
}

/**
 * 设置 CSS 变量值
 * @param {string} varName
 * @param {string} value
 */
function setCSSVariable(varName, value) {
  document.documentElement.style.setProperty(varName, value);
}

/**
 * 模拟鼠标拖动事件
 * @param {HTMLElement} element 触发 mousedown 的元素
 * @param {number} startX 起始 clientX
 * @param {number} endX 结束 clientX
 */
function simulateDrag(element, startX, endX) {
  const mousedownEvent = new MouseEvent('mousedown', {
    bubbles: true,
    cancelable: true,
    clientX: startX
  });

  const mousemoveEvent = new MouseEvent('mousemove', {
    bubbles: true,
    cancelable: true,
    clientX: endX
  });

  const mouseupEvent = new MouseEvent('mouseup', {
    bubbles: true,
    cancelable: true
  });

  element.dispatchEvent(mousedownEvent);
  document.dispatchEvent(mousemoveEvent);
  document.dispatchEvent(mouseupEvent);
}

/**
 * 模拟键盘事件
 * @param {HTMLElement} element
 * @param {string} key
 * @param {boolean} shiftKey
 */
function simulateKeyPress(element, key, shiftKey = false) {
  const keydownEvent = new KeyboardEvent('keydown', {
    bubbles: true,
    cancelable: true,
    key,
    shiftKey
  });

  element.dispatchEvent(keydownEvent);
}

/**
 * 等待指定时间
 * @param {number} ms
 * @returns {Promise<void>}
 */
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 等待过渡动画完成（监听 transitionend）
 * @param {HTMLElement} element
 * @param {number} timeout
 * @returns {Promise<void>}
 */
function waitForTransition(element, timeout = 1000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('Transition timeout'));
    }, timeout);

    element.addEventListener(
      'transitionend',
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true }
    );
  });
}

/**
 * 创建测试用的 localStorage 数据（StateManager 相关测试会使用）
 * @param {string} userId
 * @param {Record<string, any>} overrides
 */
function createTestState(userId, overrides = {}) {
  return {
    version: '1.1',
    userId,
    timestamp: Date.now(),
    panels: {
      groups: { width: '200px', collapsed: false },
      accounts: { width: '260px', collapsed: false },
      emails: { width: '380px', collapsed: false },
      ...overrides
    }
  };
}

/**
 * 模拟窗口大小变化
 * @param {number} width
 * @param {number} height
 */
function setWindowSize(width, height) {
  Object.defineProperty(window, 'innerWidth', {
    writable: true,
    configurable: true,
    value: width
  });

  Object.defineProperty(window, 'innerHeight', {
    writable: true,
    configurable: true,
    value: height
  });

  window.dispatchEvent(new Event('resize'));
}

/**
 * 检查元素是否可见（基于 offset）
 * @param {HTMLElement} element
 * @returns {boolean}
 */
function isVisible(element) {
  return element.offsetWidth > 0 && element.offsetHeight > 0;
}

/**
 * 检查元素是否有焦点
 * @param {HTMLElement} element
 * @returns {boolean}
 */
function hasFocus(element) {
  return document.activeElement === element;
}

module.exports = {
  createLayoutDOM,
  createSimpleLayoutDOM,
  getCSSVariable,
  setCSSVariable,
  simulateDrag,
  simulateKeyPress,
  wait,
  waitForTransition,
  createTestState,
  setWindowSize,
  isVisible,
  hasFocus
};

