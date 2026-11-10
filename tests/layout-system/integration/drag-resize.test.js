/**
 * 集成测试 - 拖动调整宽度完整流程（TASK-02-002）
 *
 * 说明：
 * - 该文件聚焦 TC-F1-001-P：从 mousedown 到 mouseup 的完整链路。
 * - 其他边界/性能用例将在后续 TASK 中逐步补齐（避免影响阶段性迭代）。
 */

const LayoutManager = require('../../../static/js/layout-manager.js');
const { createLayoutDOM, simulateDrag, wait, getCSSVariable } = require('../test-utils.js');

describe('拖动调整宽度集成测试（TASK-02-002）', () => {
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

  test('TC-F1-001-P: 完整的拖动流程', async () => {
    const resizer = document.querySelector('[data-resizer="groups"]');

    // 初始宽度
    expect(getCSSVariable('--group-panel-width')).toBe('200px');

    // 模拟拖动：从 200px 拖到 250px（+50）
    simulateDrag(resizer, 200, 250);

    // 等待 requestAnimationFrame 执行
    await wait(50);

    // 验证宽度已更新
    expect(getCSSVariable('--group-panel-width')).toBe('250px');
  });

  test('TC-F1-005-N: 快速拖动导致鼠标移出窗口后应正常结束', async () => {
    const resizer = document.querySelector('[data-resizer="groups"]');

    // 开始拖动
    resizer.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
    );
    expect(document.body.classList.contains('layout-resizing')).toBe(true);

    // 模拟快速拖动到窗口外（以超大 clientX 表示）
    document.dispatchEvent(
      new MouseEvent('mousemove', { bubbles: true, clientX: 5000 })
    );

    // 模拟窗口失焦（等价于鼠标移出/切到其他窗口）
    window.dispatchEvent(new Event('blur'));
    await wait(50);

    // 应结束拖动并清理全局状态
    expect(layoutManager.isResizing).toBe(false);
    expect(document.body.classList.contains('layout-resizing')).toBe(false);
  });

  test('TC-F1-006-PF: 拖动更新频率应接近 60fps（基于 updatePanelWidth 调用间隔模拟）', () => {
    jest.useFakeTimers();
    try {
      const resizer = document.querySelector('[data-resizer="groups"]');
      const timestamps = [];

      const originalUpdate = layoutManager.updatePanelWidth.bind(layoutManager);
      jest
        .spyOn(layoutManager, 'updatePanelWidth')
        .mockImplementation((panel, width) => {
          timestamps.push(performance.now());
          return originalUpdate(panel, width);
        });

      resizer.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, clientX: 200, button: 0 })
      );

      // 模拟连续拖动（约 0.5s，使用 fake timers 保证稳定性）
      for (let i = 0; i < 30; i++) {
        document.dispatchEvent(
          new MouseEvent('mousemove', { bubbles: true, clientX: 200 + i })
        );
        jest.advanceTimersByTime(16);
      }

      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      jest.advanceTimersByTime(50);

      // 至少应发生多次更新
      expect(timestamps.length).toBeGreaterThanOrEqual(10);

      // 计算平均 fps（忽略第一帧）
      const deltas = [];
      for (let i = 1; i < timestamps.length; i++) {
        const delta = timestamps[i] - timestamps[i - 1];
        if (delta > 0) deltas.push(delta);
      }
      const avgDelta = deltas.reduce((a, b) => a + b, 0) / deltas.length;
      const avgFps = 1000 / avgDelta;

      // 允许一定误差（jsdom + 定时器会有波动）
      expect(avgFps).toBeGreaterThanOrEqual(55);
    } finally {
      jest.useRealTimers();
    }
  });
});
