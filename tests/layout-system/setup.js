/**
 * Jest 测试环境设置
 * 模拟浏览器 API 和 DOM 环境
 */

// 模拟 localStorage
class LocalStorageMock {
  constructor() {
    this.store = {};
  }

  clear() {
    this.store = {};
  }

  getItem(key) {
    return this.store[key] || null;
  }

  setItem(key, value) {
    this.store[key] = String(value);
  }

  removeItem(key) {
    delete this.store[key];
  }

  get length() {
    return Object.keys(this.store).length;
  }

  key(index) {
    const keys = Object.keys(this.store);
    return keys[index] || null;
  }
}

global.localStorage = new LocalStorageMock();
// jsdom 环境下 window.localStorage 可能是独立实例；这里统一指向 mock，避免跨用例污染
try {
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: global.localStorage
    });
  }
} catch (_) {
  // ignore
}

// 模拟主应用的 toast（避免 LayoutManager.notify() 退化到 window.alert，触发 jsdom 的 not implemented 报错）
global.showToast = () => {};
try {
  if (typeof window !== 'undefined') {
    window.showToast = global.showToast;
  }
} catch (_) {
  // ignore
}

// 模拟 requestAnimationFrame
global.requestAnimationFrame = (callback) => {
  return setTimeout(callback, 16);
};

global.cancelAnimationFrame = (id) => {
  clearTimeout(id);
};

// 模拟 performance.now
if (!global.performance) {
  global.performance = {};
}
global.performance.now = () => Date.now();

// 模拟 CSS.supports
if (!global.CSS) {
  global.CSS = {};
}
global.CSS.supports = (property, value) => {
  // 简单模拟，假设支持所有现代 CSS 特性
  return true;
};

// 模拟 getComputedStyle
global.getComputedStyle = (element) => {
  return {
    getPropertyValue: (prop) => {
      if (
        element &&
        element.style &&
        typeof element.style.getPropertyValue === 'function'
      ) {
        return element.style.getPropertyValue(prop) || '';
      }
      return '';
    }
  };
};

// 清理函数
afterEach(() => {
  // 清空 localStorage
  localStorage.clear();

  // 清空 document.body
  document.body.innerHTML = '';

  // 重置 CSS 变量
  if (document.documentElement.style) {
    document.documentElement.style.cssText = '';
  }
});
