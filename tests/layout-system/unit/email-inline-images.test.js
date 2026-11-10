/**
 * 单元测试 - 邮件详情内联图片重写
 *
 * 覆盖：
 * - cid: 引用按归一化 key 映射到 inline_resources
 * - 非 cid 外链图片不受影响
 * - renderEmailDetail 经过重写后仍把 data:image 内容传给 iframe
 */

const fs = require('fs');
const path = require('path');

describe('邮件详情内联图片重写', () => {
  let emailApi;

  beforeAll(() => {
    const scriptPath = path.resolve(__dirname, '../../../static/js/features/emails.js');
    const script = fs.readFileSync(scriptPath, 'utf8');
    window.eval(`${script}
window.__emailInlineImageTestApi = {
  normalizeEmailInlineResourceKey,
  resolveEmailInlineResource,
  rewriteEmailInlineImages,
  renderEmailDetail
};`);
    emailApi = window.__emailInlineImageTestApi;
  });

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="emailDetail"></div>
      <div id="emailDetailToolbar"></div>
    `;

    global.escapeHtml = (value) => String(value ?? '');
    global.formatDate = (value) => String(value ?? '');
    global.adjustIframeHeight = jest.fn();
    global.isTrustedMode = false;
    global.isTempEmailGroup = false;
    global.currentPage = 'mailbox';
    global.DOMPurify = {
      sanitize: jest.fn((html) => html)
    };

    window.escapeHtml = global.escapeHtml;
    window.formatDate = global.formatDate;
    window.adjustIframeHeight = global.adjustIframeHeight;
    window.isTrustedMode = global.isTrustedMode;
    window.isTempEmailGroup = global.isTempEmailGroup;
    window.currentPage = global.currentPage;
    window.DOMPurify = global.DOMPurify;
  });

  test('rewriteEmailInlineImages rewrites cid sources with normalized keys', () => {
    const html = '<div><img src="cid:<captcha-1>" alt="captcha"></div>';
    const email = {
      inline_resources: {
        'captcha-1': 'data:image/png;base64,QUJDRA=='
      }
    };

    const result = emailApi.rewriteEmailInlineImages(html, email);

    expect(result).toContain('data:image/png;base64,QUJDRA==');
    expect(result).not.toContain('cid:<captcha-1>');
  });

  test('rewriteEmailInlineImages preserves non-cid images and unresolved cid references', () => {
    const html = [
      '<div>',
      '<img src="https://cdn.example.com/captcha.png" alt="remote">',
      '<img src="cid:missing-inline" alt="missing">',
      '</div>'
    ].join('');

    const result = emailApi.rewriteEmailInlineImages(html, {
      inline_resources: {
        'other-inline': 'data:image/png;base64,AAAA'
      }
    });

    expect(result).toContain('https://cdn.example.com/captcha.png');
    expect(result).toContain('cid:missing-inline');
  });

  test('renderEmailDetail passes rewritten inline image html into iframe srcdoc', () => {
    emailApi.renderEmailDetail({
      subject: 'Inline Image',
      from: 'sender@example.com',
      to: 'reader@example.com',
      cc: '',
      date: '2026-03-22T12:00:00',
      body_type: 'html',
      body: '<div><img src="cid:captcha-2" alt="captcha"></div>',
      inline_resources: {
        'captcha-2': 'data:image/png;base64,QUJDRA=='
      }
    });

    const iframe = document.getElementById('emailBodyFrame');

    expect(global.DOMPurify.sanitize).toHaveBeenCalled();
    expect(iframe).not.toBeNull();
    expect(iframe.srcdoc).toContain('data:image/png;base64,QUJDRA==');
    expect(iframe.srcdoc).not.toContain('cid:captcha-2');
  });
});
