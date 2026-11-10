import unittest
from unittest.mock import patch

from tests._import_app import import_web_app_module


class BatchRequestSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = import_web_app_module().app

    def setUp(self):
        self.client = self.app.test_client()
        with self.client.session_transaction() as user_session:
            user_session["logged_in"] = True
        limits = patch.dict(
            self.app.config,
            {"MAX_BATCH_ACCOUNTS": 2, "MAX_BATCH_FOLDERS": 2, "MAX_MAIL_PAGE_SIZE": 10, "MAX_QUICK_CHECK_ACCOUNTS": 2},
        )
        limits.start()
        self.addCleanup(limits.stop)
        self.account = {
            "id": 1,
            "email": "security@example.test",
            "account_type": "outlook",
            "client_id": "mock-client",
            "refresh_token": "mock-refresh-token",
            "group_id": None,
        }
        self.lookup = self._mock(
            "accounts_repo.get_account_by_id", side_effect=lambda account_id: dict(self.account) if account_id == 1 else None
        )
        self.graph = self._mock("graph_service.get_emails_graph", return_value={"success": True, "emails": []})
        self.imap = self._mock("imap_service.get_emails_imap_with_server", return_value={"success": True, "emails": []})
        self._mock("compact_summary_service.update_summary_from_message_list", return_value={})
        self._mock("accounts_repo.touch_last_refresh_at", return_value=True)
        self.persist = self._mock("_persist_refresh_token")

    def _mock(self, target, **kwargs):
        patcher = patch("outlook_web.controllers.emails." + target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_batch_count_is_bounded_before_account_lookup(self):
        response = self.client.post("/api/emails/batch", json={"account_ids": [1, 2, 3]})
        self.assertEqual(response.status_code, 400)
        self.lookup.assert_not_called()
        self.graph.assert_not_called()

    def test_quick_check_count_is_bounded_before_account_lookup(self):
        response = self.client.post("/api/emails/quick-check", json={"account_ids": [1, 2, 3]})
        self.assertEqual(response.status_code, 400)
        self.lookup.assert_not_called()

    def test_json_arrays_are_rejected(self):
        for endpoint in ["/api/emails/batch", "/api/emails/quick-check"]:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.post(endpoint, json=[1]).status_code, 400)
        self.lookup.assert_not_called()

    def test_folder_count_and_folder_types_are_bounded(self):
        for folders in [["inbox", "junkemail", "sentitems"], ["inbox", {}], [""]]:
            with self.subTest(folders=folders):
                response = self.client.post("/api/emails/batch", json={"account_ids": [1], "folders": folders})
                self.assertEqual(response.status_code, 400)
        self.lookup.assert_not_called()

    def test_invalid_pagination_is_rejected_before_fetch(self):
        for pagination in [{"skip": -1}, {"top": 0}, {"top": 11}, {"top": None}, {"skip": "invalid"}]:
            with self.subTest(pagination=pagination):
                response = self.client.post("/api/emails/batch", json={"account_ids": [1], **pagination})
                self.assertEqual(response.status_code, 400)
        self.graph.assert_not_called()

    def test_testing_mode_uses_real_batch_controller_path(self):
        self.assertTrue(self.app.config["TESTING"])
        response = self.client.post("/api/emails/batch", json={"account_ids": [1], "top": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.graph.call_count, 2)
        self.assertEqual(response.json["summary"]["success_accounts"], 1)
        self.assertEqual(set(response.json["results"][0]["folders"]), {"inbox", "junkemail"})

    def test_duplicate_folders_are_only_fetched_once(self):
        response = self.client.post("/api/emails/batch", json={"account_ids": [1], "folders": ["inbox", "INBOX"]})
        self.assertEqual(response.status_code, 200)
        self.graph.assert_called_once()

    def test_graph_failure_can_fall_back_to_imap(self):
        self.graph.return_value = {"success": False, "error": {"code": "EMAIL_FETCH_FAILED"}}
        response = self.client.post("/api/emails/batch", json={"account_ids": [1], "folders": ["inbox"]})
        self.assertEqual(response.json["summary"]["success_accounts"], 1)
        self.imap.assert_called_once()

    def test_rotated_token_is_persisted(self):
        self.graph.return_value = {"success": True, "emails": [], "new_refresh_token": "new-mock-token"}
        self.client.post("/api/emails/batch", json={"account_ids": [1], "folders": ["inbox"]})
        self.persist.assert_called_once_with(self.account, "new-mock-token")

    def test_missing_account_does_not_abort_successful_account(self):
        response = self.client.post("/api/emails/batch", json={"account_ids": [1, 2], "folders": ["inbox"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["summary"]["success_accounts"], 1)
        self.assertEqual(response.json["summary"]["failed_accounts"], 1)

    def test_unauthenticated_batch_fetch_still_returns_401(self):
        self.assertEqual(self.app.test_client().post("/api/emails/batch", json={"account_ids": [1]}).status_code, 401)
        self.graph.assert_not_called()
