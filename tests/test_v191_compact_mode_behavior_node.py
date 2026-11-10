from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class V191CompactModeBehaviorNodeTests(unittest.TestCase):
    def test_switch_mailbox_view_mode_toggles_layout_visibility(self):
        if shutil.which("node") is None:
            self.skipTest("node is not installed")

        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "static" / "js" / "features" / "mailbox_compact.js"
        self.assertTrue(module_path.exists(), f"missing {module_path}")

        node_script = r"""
const fs = require('fs');
const vm = require('vm');

const filePath = process.argv[2] || process.argv[1];
if (!filePath) {
  console.error('missing mailbox_compact.js path');
  process.exit(2);
}

const code = fs.readFileSync(filePath, 'utf8');

const elements = {
  mailboxStandardLayout: { style: { display: '' } },
  mailboxCompactLayout: { style: { display: 'none' } },
};

const localStorage = {
  store: {},
  setItem(key, value) { this.store[String(key)] = String(value); },
  getItem(key) { return Object.prototype.hasOwnProperty.call(this.store, String(key)) ? this.store[String(key)] : null; },
};

const context = {
  console,
  window: { addEventListener: function () {} },
  document: {
    getElementById(id) { return elements[id] || null; },
  },
  localStorage,
  mailboxViewMode: 'standard',
  currentPage: 'mailbox',
  currentGroupId: 1,
  accountsCache: { 1: [] },
  groups: [],
  selectedAccountIds: new Set(),
  updateTopbar: function () {},
  renderAccountList: function () {},
  renderCompactGroupStrip: function () {},
  renderCompactAccountList: function () {},
  updateBatchActionBar: function () {},
  updateSelectAllCheckbox: function () {},
};

vm.createContext(context);
vm.runInContext(code, context, { filename: filePath });

if (typeof context.switchMailboxViewMode !== 'function') {
  throw new Error('switchMailboxViewMode is not defined');
}

context.switchMailboxViewMode('compact');
if (context.mailboxViewMode !== 'compact') {
  throw new Error('mailboxViewMode did not update to compact');
}
if (elements.mailboxStandardLayout.style.display !== 'none') {
  throw new Error('standard layout should be hidden in compact mode');
}
if (elements.mailboxCompactLayout.style.display !== 'block') {
  throw new Error('compact layout should be visible in compact mode');
}
if (localStorage.getItem('ol_mailbox_view_mode') !== 'compact') {
  throw new Error('localStorage did not persist compact mode');
}

context.switchMailboxViewMode('standard');
if (context.mailboxViewMode !== 'standard') {
  throw new Error('mailboxViewMode did not update to standard');
}
if (elements.mailboxStandardLayout.style.display !== '') {
  throw new Error('standard layout should be visible in standard mode');
}
if (elements.mailboxCompactLayout.style.display !== 'none') {
  throw new Error('compact layout should be hidden in standard mode');
}
if (localStorage.getItem('ol_mailbox_view_mode') !== 'standard') {
  throw new Error('localStorage did not persist standard mode');
}

process.stdout.write('OK');
"""

        result = subprocess.run(
            ["node", "-e", node_script, "--", str(module_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"node stdout:\n{result.stdout}\nnode stderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
