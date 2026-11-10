/**
 * StateManager - 布局状态持久化管理器
 *
 * 职责（按文档逐步实现）：
 * - 将 LayoutState 保存到 localStorage（多用户隔离 key）
 * - 从 localStorage 加载并验证 LayoutState
 * - 提供版本迁移能力（migrate）
 *
 * 兼容性说明：
 * - 浏览器环境：通过 <script> 引入后，StateManager 挂载到 window.StateManager。
 * - 测试/Node 环境：如果存在 module.exports，则导出 StateManager 以便 Jest 直接 require。
 */

(function (global) {
  'use strict';

  const CURRENT_VERSION = '1.1';
  const STORAGE_KEY_PREFIX = 'outlook_layout_state_';

  class StateManager {
    /**
     * 安全获取 localStorage（某些浏览器/隐私模式下访问会抛错）
     * @returns {Storage|null}
     */
    getStorage() {
      try {
        if (!global) return null;
        // 访问 localStorage 属性本身也可能抛错，因此需要 try/catch
        return global.localStorage || null;
      } catch (_) {
        return null;
      }
    }

    /**
     * 生成 localStorage key
     * @param {string} userId
     * @returns {string}
     */
    getStorageKey(userId) {
      const safeUserId = userId && String(userId).trim() ? String(userId).trim() : 'guest';
      return `${STORAGE_KEY_PREFIX}${safeUserId}`;
    }

    /**
     * 保存状态到 localStorage
     * @param {string} userId
     * @param {Record<string, any>} state
     * @returns {boolean} 是否保存成功
     */
    save(userId, state) {
      const storage = this.getStorage();
      if (!storage) {
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] localStorage not available, using default layout');
        } catch (_) {
          // ignore
        }
        return false;
      }

      const payload = {
        ...state,
        version: state && state.version ? state.version : CURRENT_VERSION,
        userId: state && state.userId ? state.userId : userId,
        timestamp: Date.now()
      };

      if (!this.validate(payload)) {
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] invalid state, skip saving');
        } catch (_) {
          // ignore
        }
        return false;
      }

      const key = this.getStorageKey(userId);
      const json = JSON.stringify(payload);

      try {
        storage.setItem(key, json);
        return true;
      } catch (e) {
        // QuotaExceededError：清理旧数据后重试（TDD 7.3）
        if (this.isQuotaExceededError(e)) {
          try {
            // eslint-disable-next-line no-console
            console.warn('[StateManager] quota exceeded, clearing old states and retrying');
          } catch (_) {
            // ignore
          }
          try {
            this.clearOldStates(key);
            storage.setItem(key, json);
            return true;
          } catch (e2) {
            try {
              // eslint-disable-next-line no-console
              console.warn('[StateManager] save retry failed:', e2);
            } catch (_) {
              // ignore
            }
            return false;
          }
        }

        // localStorage 不可用等：降级为默认布局
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] save failed:', e);
        } catch (_) {
          // ignore
        }
        return false;
      }
    }

    /**
     * 从 localStorage 加载状态
     * @param {string} userId
     * @returns {Record<string, any>|null}
     */
    load(userId) {
      const storage = this.getStorage();
      if (!storage) {
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] localStorage not available, using default layout');
        } catch (_) {
          // ignore
        }
        return null;
      }

      const key = this.getStorageKey(userId);

      let raw = null;
      try {
        raw = storage.getItem(key);
      } catch (e) {
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] load failed (storage error):', e);
        } catch (_) {
          // ignore
        }
        return null;
      }

      if (!raw) return null;

      let parsed = null;
      try {
        parsed = JSON.parse(raw);
      } catch (e) {
        // JSON 损坏：清除并降级为默认布局（TDD 7.3）
        try {
          this.clear(userId);
        } catch (_) {
          // ignore
        }
        try {
          // eslint-disable-next-line no-console
          console.error('[StateManager] load failed (invalid json):', e);
        } catch (_) {
          // ignore
        }
        return null;
      }

      const migrated = this.migrate(parsed);
      if (!this.validate(migrated)) {
        try {
          this.clear(userId);
        } catch (_) {
          // ignore
        }
        try {
          // eslint-disable-next-line no-console
          console.warn('[StateManager] invalid state, cleared and fallback to default');
        } catch (_) {
          // ignore
        }
        return null;
      }

      return migrated;
    }

    /**
     * 清除保存的状态
     * @param {string} userId
     * @returns {void}
     */
    clear(userId) {
      try {
        const storage = this.getStorage();
        if (!storage) return;
        const key = this.getStorageKey(userId);
        storage.removeItem(key);
      } catch (_) {
        // ignore
      }
    }

    /**
     * 判断是否为 QuotaExceededError（不同浏览器实现不同）
     * @param {any} error
     * @returns {boolean}
     */
    isQuotaExceededError(error) {
      if (!error) return false;
      const name = typeof error.name === 'string' ? error.name : '';
      if (name === 'QuotaExceededError') return true;
      if (name === 'NS_ERROR_DOM_QUOTA_REACHED') return true;
      const code = typeof error.code === 'number' ? error.code : null;
      // 22/1014：常见的 quota 相关 code（Safari/Firefox）
      return code === 22 || code === 1014;
    }

    /**
     * 清理旧的布局状态（用于 QuotaExceededError 降级处理）
     * @param {string} excludeKey 当前写入 key（避免误删正在保存的 key）
     * @returns {void}
     */
    clearOldStates(excludeKey) {
      const storage = this.getStorage();
      if (!storage) return;

      const keys = [];
      try {
        for (let i = 0; i < storage.length; i += 1) {
          const k = storage.key(i);
          if (!k) continue;
          if (!k.startsWith(STORAGE_KEY_PREFIX)) continue;
          if (excludeKey && k === excludeKey) continue;
          keys.push(k);
        }
      } catch (_) {
        // ignore
      }

      // 按 timestamp 由旧到新清理（尽量保留最近的偏好）
      const items = keys.map((k) => {
        let ts = 0;
        try {
          const raw = storage.getItem(k);
          if (raw) {
            const parsed = JSON.parse(raw);
            ts = parsed && typeof parsed.timestamp === 'number' ? parsed.timestamp : 0;
          }
        } catch (_) {
          ts = 0;
        }
        return { key: k, ts };
      });

      items.sort((a, b) => a.ts - b.ts);

      items.forEach((item) => {
        try {
          storage.removeItem(item.key);
        } catch (_) {
          // ignore
        }
      });
    }

    /**
     * 校验状态数据格式
     * @param {Record<string, any>} state
     * @returns {boolean}
     */
    validate(state) {
      if (!state || typeof state !== 'object') return false;
      if (!state.version || !state.panels) return false;

      const panels = state.panels;
      for (const panelType of ['groups', 'accounts', 'emails']) {
        const panel = panels[panelType];
        if (!panel || typeof panel !== 'object') return false;
        if (!panel.width || !/^\d+px$/.test(panel.width)) return false;
        if (typeof panel.collapsed !== 'boolean') return false;
      }

      return true;
    }

    /**
     * 版本迁移（当前仅保证字段齐全；更复杂迁移在后续版本扩展）
     * @param {Record<string, any>} state
     * @returns {Record<string, any>}
     */
    migrate(state) {
      if (!state || typeof state !== 'object') return state;

      // 若缺少 version，认为是旧数据，补齐为当前版本
      if (!state.version) {
        return { ...state, version: CURRENT_VERSION };
      }

      // 已是当前版本则直接返回
      if (state.version === CURRENT_VERSION) return state;

      // 其他版本：暂做“兼容性兜底”，保留原结构并标记为当前版本
      return { ...state, version: CURRENT_VERSION };
    }
  }

  // 浏览器环境挂载
  global.StateManager = StateManager;

  // Jest/Node 环境导出
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = StateManager;
  }
})(typeof window !== 'undefined' ? window : globalThis);
