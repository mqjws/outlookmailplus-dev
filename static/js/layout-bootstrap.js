/**
 * 可调整布局系统 - 页面初始化入口
 *
 * 约束：
 * - 不能在 HTML 中内联 <script>（符合 tests/test_smoke_contract.py 的零构建约束）。
 * - 仅在浏览器环境运行；Jest 单测直接 require layout-manager.js，不会加载本文件。
 */

document.addEventListener('DOMContentLoaded', () => {
  // ==================== F3：恢复默认布局（UI 绑定） ====================
  // 说明：即使布局系统初始化失败，也要保证 onclick 不抛错（仅降级为关闭/无操作）。
  window.showResetLayoutModal = function showResetLayoutModal() {
    const modal = document.getElementById('resetLayoutModal');
    if (!modal) return;
    modal.classList.add('show');
  };

  window.hideResetLayoutModal = function hideResetLayoutModal() {
    const modal = document.getElementById('resetLayoutModal');
    if (!modal) return;
    modal.classList.remove('show');
  };

  window.confirmResetLayout = function confirmResetLayout() {
    try {
      if (window.layoutManager && typeof window.layoutManager.resetLayout === 'function') {
        window.layoutManager.resetLayout();
      }
    } finally {
      window.hideResetLayoutModal();
    }
  };

  // ESC 关闭确认框（不影响主业务）
  document.addEventListener('keydown', (e) => {
    if (!e || e.key !== 'Escape') return;
    const modal = document.getElementById('resetLayoutModal');
    if (!modal || !modal.classList.contains('show')) return;
    window.hideResetLayoutModal();
  });

  try {
    if (typeof window.LayoutManager !== 'function') return;

    const layoutManager = new window.LayoutManager();

    // 标记布局系统已启用：用于禁用 main.css 中的移动端历史侧栏滑入样式（避免折叠指示器被移出屏幕）
    // 放在 init() 之前，减少窄屏下的闪烁/错位窗口期。
    try {
      if (document && document.documentElement && document.documentElement.classList) {
        document.documentElement.classList.add('layout-system-enabled');
      }
    } catch (_) {
      // ignore
    }

    layoutManager.init();

    // 暴露到全局，便于调试（后续状态管理/折叠等也复用同一实例）
    window.layoutManager = layoutManager;
  } catch (e) {
    // 初始化失败不应影响主业务功能
    console.warn('[LayoutManager] init failed:', e);
  }
});
