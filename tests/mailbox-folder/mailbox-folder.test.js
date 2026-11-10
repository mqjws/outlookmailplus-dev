const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const projectRoot = path.resolve(__dirname, '../..');

function createHarness() {
    const elements = new Map();
    const createElement = () => ({
        style: {},
        dataset: {},
        textContent: '',
        innerHTML: '',
        disabled: false,
        classList: { toggle() {}, remove() {} },
        addEventListener() {},
    });
    const tabs = ['inbox', 'junkemail'].map(folder => ({ ...createElement(), dataset: { folder } }));
    const refreshButton = createElement();
    const context = vm.createContext({
        console,
        window: { addEventListener() {} },
        document: {
            getElementById(id) {
                if (!elements.has(id)) elements.set(id, createElement());
                return elements.get(id);
            },
            querySelector: () => refreshButton,
            querySelectorAll: selector => selector === '.email-tab' ? tabs : [],
        },
        currentAccount: 'mailbox@example.com',
        currentFolder: 'inbox',
        currentMethod: 'graph',
        currentEmails: [],
        currentSkip: 0,
        hasMoreEmails: true,
        accountsCache: {},
        emailListCache: {},
        isTempEmailGroup: false,
        translateAppTextLocal: value => value,
        syncAccountSummaryToAccountCache() {},
    });
    for (const feature of ['accounts', 'groups', 'emails']) {
        vm.runInContext(fs.readFileSync(path.join(projectRoot, `static/js/features/${feature}.js`), 'utf8'), context);
    }
    const mainSource = fs.readFileSync(path.join(projectRoot, 'static/js/main.js'), 'utf8');
    const switchStart = mainSource.indexOf('        function switchFolder(folder) {');
    const switchEnd = mainSource.indexOf('        function selectCustomColor(', switchStart);
    assert.ok(switchStart >= 0 && switchEnd > switchStart);
    vm.runInContext(mainSource.slice(switchStart, switchEnd), context);
    context.updateEmailBatchActionBar = () => {};
    return { context, elements, tabs, refreshButton };
}

function responseFor(subject) {
    return { success: true, emails: [{ id: subject, subject }], method: 'Graph API', has_more: false };
}

test('accounts open the latest message folder without using protocol preference', () => {
    const { context } = createHarness();
    context.accountsCache = { 1: [{
        email: 'MAILBOX@example.com',
        latest_email_folder: 'junkemail',
        latest_verification_folder: 'inbox',
        preferred_verification_channel: 'graph_inbox',
    }] };
    assert.equal(context.resolveAccountMailboxFolder(' mailbox@example.com '), 'junkemail');
    context.accountsCache[1][0].latest_email_folder = 'inbox';
    assert.equal(context.resolveAccountMailboxFolder('mailbox@example.com'), 'inbox');
});

test('accounts without a message summary fall back safely', () => {
    const { context } = createHarness();
    context.accountsCache = { 1: [{ email: 'mailbox@example.com', latest_verification_folder: 'junkemail' }], invalid: null };
    assert.equal(context.resolveAccountMailboxFolder('mailbox@example.com'), 'junkemail');
    assert.equal(context.resolveAccountMailboxFolder('unknown@example.com'), 'inbox');
    context.accountsCache[1][0].latest_email_folder = 'unexpected';
    assert.equal(context.resolveAccountMailboxFolder('mailbox@example.com'), 'inbox');
});

test('selecting an account loads and activates its latest folder', () => {
    const { context, elements, tabs } = createHarness();
    context.accountsCache = { 1: [{ email: 'mailbox@example.com', latest_email_folder: 'junkemail' }] };
    const activated = [];
    tabs.forEach(tab => { tab.classList.toggle = (name, value) => { if (value) activated.push(tab.dataset.folder); }; });
    const calls = [];
    context.loadEmails = email => calls.push([email, context.currentFolder]);
    context.selectAccount('mailbox@example.com');
    assert.equal(context.currentFolder, 'junkemail');
    assert.deepEqual(activated, ['junkemail']);
    assert.deepEqual(calls, [['mailbox@example.com', 'junkemail']]);
    assert.equal(elements.get('currentAccountEmail').textContent, 'mailbox@example.com');
});

test('switching folders loads automatically and clears the previous detail', async () => {
    const { context, elements } = createHarness();
    const calls = [];
    context.loadEmails = email => calls.push([email, context.currentFolder]);
    await context.switchFolder('junkemail');
    assert.deepEqual(calls, [['mailbox@example.com', 'junkemail']]);
    assert.equal(elements.get('emailDetailToolbar').style.display, 'none');
    assert.ok(elements.get('emailDetail').innerHTML.includes('选择一封邮件查看详情'));
    await context.switchFolder('junkemail');
    assert.equal(calls.length, 1);
});

test('verification switches to its actual source and invalidates stale cache', () => {
    const { context } = createHarness();
    const cacheKey = 'mailbox@example.com_junkemail';
    context.emailListCache[cacheKey] = { emails: [] };
    const calls = [];
    context.loadEmails = email => calls.push([email, context.currentFolder]);
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'junkemail' });
    assert.equal(context.currentFolder, 'junkemail');
    assert.equal(context.emailListCache[cacheKey], undefined);
    assert.deepEqual(calls, [['mailbox@example.com', 'junkemail']]);
});

test('verification in the displayed folder forces a refresh', () => {
    const { context } = createHarness();
    const calls = [];
    context.loadEmails = (...args) => calls.push(args);
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'inbox' });
    assert.deepEqual(calls, [['mailbox@example.com', true]]);
});

test('successful verification copy refreshes its source folder and shows the source', async () => {
    const { context } = createHarness();
    const copied = [];
    const toasts = [];
    const loads = [];
    context.copyToClipboard = async value => copied.push(value);
    context.syncExtractedVerificationToAccountCache = () => {};
    context.getUiLanguage = () => 'zh';
    context.showToast = message => toasts.push(message);
    context.setTimeout = () => {};
    context.loadEmails = email => loads.push([email, context.currentFolder]);
    context.fetch = async () => ({ json: async () => ({
        success: true,
        data: { formatted: '654321', verification_code: '654321', folder: 'junkemail' },
    }) });
    const button = { innerHTML: 'key', disabled: false, style: {} };
    assert.equal(await context.copyVerificationInfo('mailbox@example.com', button), true);
    assert.deepEqual(copied, ['654321']);
    assert.deepEqual(loads, [['mailbox@example.com', 'junkemail']]);
    assert.ok(toasts[0].includes('来自垃圾邮件'));
});

test('verification for another account invalidates only its cache', () => {
    const { context } = createHarness();
    context.emailListCache['other@example.com_junkemail'] = { emails: [] };
    context.loadEmails = () => assert.fail('must not change the displayed account');
    context.syncVerificationMailbox('other@example.com', { folder: 'junkemail' });
    assert.equal(context.currentFolder, 'inbox');
    assert.equal(context.emailListCache['other@example.com_junkemail'], undefined);
});

test('verification from detail, temporary mail, or unknown folders leaves the list alone', () => {
    const { context } = createHarness();
    context.loadEmails = () => assert.fail('must not navigate');
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'junkemail' }, { source: 'mailbox' });
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'junkemail' }, { source: 'temp' });
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'unexpected' });
    context.isTempEmailGroup = true;
    context.syncVerificationMailbox('mailbox@example.com', { folder: 'junkemail' });
    assert.equal(context.currentFolder, 'inbox');
});

test('folder cache is reused without another network call', async () => {
    const { context, refreshButton } = createHarness();
    context.currentFolder = 'junkemail';
    context.emailListCache['mailbox@example.com_junkemail'] = { emails: [{ subject: 'cached' }], has_more: false, skip: 0, method: 'graph' };
    context.renderEmailList = () => {};
    context.fetch = () => assert.fail('cache should be reused');
    refreshButton.disabled = true;
    await context.loadEmails('mailbox@example.com');
    assert.equal(context.currentEmails[0].subject, 'cached');
    assert.equal(refreshButton.disabled, false);
});

test('late inbox response cannot replace a newer junk folder response', async () => {
    const { context, refreshButton, tabs } = createHarness();
    const pending = [];
    context.renderEmailList = () => {};
    context.fetch = url => new Promise(resolve => pending.push({ url, resolve }));
    const inboxRequest = context.loadEmails('mailbox@example.com');
    context.currentFolder = 'junkemail';
    const junkRequest = context.loadEmails('mailbox@example.com');
    assert.ok(pending[0].url.includes('folder=inbox'));
    assert.ok(pending[1].url.includes('folder=junkemail'));
    pending[1].resolve({ json: async () => responseFor('junk verification') });
    await junkRequest;
    pending[0].resolve({ json: async () => responseFor('old inbox') });
    await inboxRequest;
    assert.equal(context.currentEmails[0].subject, 'junk verification');
    assert.equal(context.emailListCache['mailbox@example.com_inbox'], undefined);
    assert.equal(refreshButton.disabled, false);
    assert.ok(tabs.every(tab => !tab.disabled));
});

test('late response for a previous account cannot replace a cached new account', async () => {
    const { context, refreshButton } = createHarness();
    context.renderEmailList = () => {};
    let resolvePrevious;
    context.fetch = () => new Promise(resolve => { resolvePrevious = resolve; });
    const previousRequest = context.loadEmails('mailbox@example.com');
    context.currentAccount = 'other@example.com';
    context.emailListCache['other@example.com_inbox'] = { emails: [{ subject: 'new account' }], has_more: false, skip: 0 };
    await context.loadEmails('other@example.com');
    resolvePrevious({ json: async () => responseFor('previous account') });
    await previousRequest;
    assert.equal(context.currentEmails[0].subject, 'new account');
    assert.equal(refreshButton.disabled, false);
});

test('stale request failure leaves the active folder loading state intact', async () => {
    const { context, refreshButton } = createHarness();
    const pending = [];
    context.renderEmailList = () => {};
    context.fetch = () => new Promise((resolve, reject) => pending.push({ resolve, reject }));
    const inboxRequest = context.loadEmails('mailbox@example.com');
    context.currentFolder = 'junkemail';
    const junkRequest = context.loadEmails('mailbox@example.com');
    pending[0].reject(new Error('stale inbox request failed'));
    await inboxRequest;
    assert.equal(refreshButton.disabled, true);
    pending[1].resolve({ json: async () => responseFor('junk verification') });
    await junkRequest;
    assert.equal(context.currentEmails[0].subject, 'junk verification');
    assert.equal(refreshButton.disabled, false);
});

test('empty folder messaging distinguishes junk from inbox', () => {
    const { context, elements } = createHarness();
    context.currentFolder = 'junkemail';
    context.renderEmailList([]);
    assert.ok(elements.get('emailList').innerHTML.includes('垃圾邮件为空'));
    context.currentFolder = 'inbox';
    context.renderEmailList([]);
    assert.ok(elements.get('emailList').innerHTML.includes('收件箱为空'));
});
