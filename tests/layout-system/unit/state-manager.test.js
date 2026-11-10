/**
 * StateManager 单元测试（TASK-04-001）
 */

const StateManager = require('../../../static/js/state-manager.js');
const { createTestState } = require('../test-utils.js');

describe('StateManager 单元测试（TASK-04-001）', () => {
  let stateManager;

  beforeEach(() => {
    stateManager = new StateManager();
  });

  test('getStorageKey() 应支持 userId 与 guest', () => {
    expect(stateManager.getStorageKey('user123')).toBe('outlook_layout_state_user123');
    expect(stateManager.getStorageKey('  userA  ')).toBe('outlook_layout_state_userA');
    expect(stateManager.getStorageKey('')).toBe('outlook_layout_state_guest');
    expect(stateManager.getStorageKey(null)).toBe('outlook_layout_state_guest');
  });

  test('save()/load() 应能完成状态保存与读取', () => {
    const userId = 'user123';
    const state = createTestState(userId);

    const ok = stateManager.save(userId, state);
    expect(ok).toBe(true);

    const loaded = stateManager.load(userId);
    expect(loaded).toBeTruthy();
    expect(loaded.version).toBe('1.1');
    expect(loaded.userId).toBe(userId);
    expect(loaded.panels.groups.width).toBe('200px');
    expect(loaded.panels.groups.collapsed).toBe(false);
  });

  test('clear() 应清除指定用户的状态', () => {
    const userId = 'user123';
    const state = createTestState(userId);

    stateManager.save(userId, state);
    expect(stateManager.load(userId)).toBeTruthy();

    stateManager.clear(userId);
    expect(stateManager.load(userId)).toBeNull();
  });

  test('validate() 应验证数据格式', () => {
    const good = createTestState('u1');
    expect(stateManager.validate(good)).toBe(true);

    const badWidth = createTestState('u1');
    badWidth.panels.groups.width = '200';
    expect(stateManager.validate(badWidth)).toBe(false);

    const badCollapsed = createTestState('u1');
    badCollapsed.panels.groups.collapsed = 'yes';
    expect(stateManager.validate(badCollapsed)).toBe(false);

    expect(stateManager.validate(null)).toBe(false);
    expect(stateManager.validate({ version: '1.1' })).toBe(false);
  });

  test('migrate() 应补齐/修正 version', () => {
    const migrated1 = stateManager.migrate({ panels: createTestState('u1').panels });
    expect(migrated1.version).toBe('1.1');

    const migrated2 = stateManager.migrate({ version: '1.0', panels: createTestState('u1').panels });
    expect(migrated2.version).toBe('1.1');
  });

  test('load() JSON 损坏时应清除并返回 null', () => {
    const userId = 'u1';
    const key = stateManager.getStorageKey(userId);
    window.localStorage.setItem(key, '{bad json');

    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const loaded = stateManager.load(userId);
    expect(loaded).toBeNull();
    expect(window.localStorage.getItem(key)).toBeNull();
    errSpy.mockRestore();
  });

  test('save() localStorage 不可用时应返回 false', () => {
    const userId = 'u1';
    const state = createTestState(userId);

    const originalLocalStorage = window.localStorage;
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: null
    });

    try {
      const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
      expect(stateManager.save(userId, state)).toBe(false);
      warnSpy.mockRestore();
    } finally {
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: originalLocalStorage
      });
    }
  });

  test('getStorage() 在访问 localStorage 抛错时应返回 null', () => {
    const originalLocalStorage = window.localStorage;

    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('blocked');
      }
    });

    expect(stateManager.getStorage()).toBeNull();

    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: originalLocalStorage
    });
  });

  test('isQuotaExceededError() 应识别不同浏览器的 quota 错误形态', () => {
    expect(stateManager.isQuotaExceededError(null)).toBe(false);
    expect(stateManager.isQuotaExceededError({ name: 'QuotaExceededError' })).toBe(true);
    expect(stateManager.isQuotaExceededError({ name: 'NS_ERROR_DOM_QUOTA_REACHED' })).toBe(true);
    expect(stateManager.isQuotaExceededError({ code: 22 })).toBe(true);
    expect(stateManager.isQuotaExceededError({ code: 1014 })).toBe(true);
    expect(stateManager.isQuotaExceededError({ name: 'OtherError', code: 123 })).toBe(false);
  });

  test('clearOldStates() 应清理旧状态并保留 excludeKey', () => {
    const k1 = 'outlook_layout_state_u1';
    const k2 = 'outlook_layout_state_u2';
    const excludeKey = 'outlook_layout_state_keep';
    const otherKey = 'not_outlook_key';

    window.localStorage.setItem(k1, JSON.stringify({ timestamp: 1 }));
    window.localStorage.setItem(k2, '{bad json'); // 解析失败应仍被清理
    window.localStorage.setItem(excludeKey, JSON.stringify({ timestamp: 999 }));
    window.localStorage.setItem(otherKey, 'x');

    stateManager.clearOldStates(excludeKey);

    expect(window.localStorage.getItem(k1)).toBeNull();
    expect(window.localStorage.getItem(k2)).toBeNull();
    expect(window.localStorage.getItem(excludeKey)).toBeTruthy();
    expect(window.localStorage.getItem(otherKey)).toBe('x');
  });

  test('save() 遇到 QuotaExceededError 时应清理旧数据并重试', () => {
    const userId = 'u1';
    const state = createTestState(userId);
    const key = stateManager.getStorageKey(userId);

    // 使用可控的 storage stub：第一次 setItem 抛 QuotaExceededError，第二次成功
    const store = {};
    let throwOnce = true;
    const storageStub = {
      setItem: jest.fn((k, v) => {
        if (throwOnce) {
          throwOnce = false;
          const err = new Error('quota');
          err.name = 'QuotaExceededError';
          throw err;
        }
        store[k] = String(v);
      }),
      getItem: jest.fn((k) => store[k] || null),
      removeItem: jest.fn((k) => {
        delete store[k];
      })
    };

    const getStorageSpy = jest.spyOn(stateManager, 'getStorage').mockReturnValue(storageStub);
    const clearSpy = jest.spyOn(stateManager, 'clearOldStates').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    try {
      const ok = stateManager.save(userId, state);
      expect(ok).toBe(true);
      expect(storageStub.setItem).toHaveBeenCalledTimes(2);
      expect(clearSpy).toHaveBeenCalledWith(key);
      expect(storageStub.getItem(key)).toBeTruthy();
    } finally {
      warnSpy.mockRestore();
      clearSpy.mockRestore();
      getStorageSpy.mockRestore();
    }
  });

  test('save() 数据格式无效时应返回 false（不写入 storage）', () => {
    const userId = 'u1';
    const badState = createTestState(userId);
    badState.panels.groups.width = '200'; // 非 px

    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const ok = stateManager.save(userId, badState);
      expect(ok).toBe(false);
      expect(window.localStorage.getItem(stateManager.getStorageKey(userId))).toBeNull();
    } finally {
      warnSpy.mockRestore();
    }
  });

  test('load() 数据校验失败时应清除并返回 null', () => {
    const userId = 'u1';
    const key = stateManager.getStorageKey(userId);
    window.localStorage.setItem(
      key,
      JSON.stringify({
        version: '1.1',
        userId,
        timestamp: Date.now(),
        panels: {
          groups: { width: '200', collapsed: false }, // invalid
          accounts: { width: '260px', collapsed: false },
          emails: { width: '380px', collapsed: false }
        }
      })
    );

    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const loaded = stateManager.load(userId);
      expect(loaded).toBeNull();
      expect(window.localStorage.getItem(key)).toBeNull();
    } finally {
      warnSpy.mockRestore();
    }
  });

  test('load() storage.getItem 抛错时应返回 null（不抛异常）', () => {
    const userId = 'u1';

    const originalLocalStorage = window.localStorage;
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: () => {
          throw new Error('denied');
        },
        setItem: () => {},
        removeItem: () => {},
        key: () => null,
        get length() {
          return 0;
        }
      }
    });

    try {
      expect(stateManager.load(userId)).toBeNull();
    } finally {
      warnSpy.mockRestore();
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: originalLocalStorage
      });
    }
  });
});
