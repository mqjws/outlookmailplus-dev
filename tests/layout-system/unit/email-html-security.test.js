const fs = require('fs');
const path = require('path');

describe('邮件 HTML 安全边界', () => {
  let emailApi;
  const sanitizerSource = fs.readFileSync(
    path.resolve(__dirname, '../../../static/vendor/dompurify/purify.min.js'), 'utf8'
  );

  beforeAll(() => {
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../../static/js/features/emails.js'), 'utf8'
    );
    window.eval(`${source}\nwindow.__emailSecurityApi = { renderEmailDetail, openFullscreenEmail };`);
    emailApi = window.__emailSecurityApi;
  });

  beforeEach(() => {
    jest.useFakeTimers();
    document.body.innerHTML = `
      <div id="emailDetail"></div><div id="emailDetailToolbar"></div>
      <div id="fullscreenEmailModal"></div><div id="fullscreenEmailContent"></div>
      <span id="fullscreenEmailTitle"></span>
    `;
    window.escapeHtml = (value) => {
      const container = document.createElement('div');
      container.textContent = String(value ?? '');
      return container.innerHTML;
    };
    window.formatDate = (value) => String(value ?? '');
    window.isTrustedMode = false;
    window.isTempEmailGroup = false;
    window.currentPage = 'mailbox';
    window.eval(sanitizerSource);
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  function render(body) {
    emailApi.renderEmailDetail({
      subject: 'Security audit', from: 'sender@example.test', to: 'reader@example.test',
      date: '2026-11-03T00:00:00Z', body_type: 'html', body
    });
    return document.getElementById('emailBodyFrame');
  }

  test('本地净化库移除脚本和事件属性', () => {
    expect(window.DOMPurify.version).toBe('3.4.17');
    const iframe = render('<script>parent.auditMarker=1</script><img src="invalid" onerror="parent.auditMarker=1"><b>safe</b>');
    expect(iframe.srcdoc).not.toContain('<script>');
    expect(iframe.srcdoc).not.toContain('onerror');
    expect(iframe.srcdoc).toContain('<b>safe</b>');
    expect(iframe.getAttribute('sandbox')).toBe('allow-same-origin');
  });

  test('净化库缺失时转义原始 HTML 而不是正则过滤', () => {
    window.DOMPurify = undefined;
    const iframe = render('<script>parent.auditMarker=1</script><img src=x onerror=parent.auditMarker=1>');
    expect(iframe.srcdoc).toContain('&lt;script&gt;');
    expect(iframe.srcdoc).toContain('&lt;img');
    expect(iframe.srcdoc).not.toContain('<script>');
    expect(iframe.srcdoc).not.toContain('<img');
    expect(iframe.srcdoc).toContain('<pre ');
  });

  test('净化库接口不完整时同样降级为纯文本', () => {
    window.DOMPurify = {};
    expect(render('<img src=x onerror=parent.auditMarker=1>').srcdoc).toContain('&lt;img');
  });

  test.each([false, true])('全屏视图保持沙盒隔离，信任模式=%s', (trustedMode) => {
    window.isTrustedMode = trustedMode;
    const original = render('<p>safe content</p>');
    original.contentDocument.body.innerHTML = '<p>safe content</p>';
    emailApi.openFullscreenEmail();
    const fullscreen = document.getElementById('fullscreenEmailBodyFrame');
    expect(fullscreen.getAttribute('sandbox')).toBe('allow-same-origin');
    expect(fullscreen.srcdoc).toContain('safe content');
    expect(fullscreen.getAttribute('sandbox')).not.toContain('allow-scripts');
  });
});
