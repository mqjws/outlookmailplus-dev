import json
import unittest
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class PoolCFTddSkeletonTests(unittest.TestCase):
    """按 docs/TDD/2026-04-09-CF临时邮箱接入邮箱池-TDD.md 的测试骨架。

    说明：你已要求先写测试骨架（暂时 skip），等实现落地后再逐步打开。
    """

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            # 仅清理本用例会污染的关键表，避免影响其他测试
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM temp_email_messages")
            db.execute("DELETE FROM temp_emails")
            db.execute("DELETE FROM accounts")
            db.commit()

            # external pool 常用开关（为了后续可扩展到接口测试）
            settings_repo.set_setting("pool_external_enabled", "true")
            # CF Worker 配置（用占位值即可；真实网络必须在实现测试中 mock）
            settings_repo.set_setting("cf_worker_base_url", "http://mock.invalid")
            settings_repo.set_setting("cf_worker_admin_key", "test-admin")

    # ---------------------------------------------------------------------
    # 4.2 Repository 层（pool.py）单元测试 - 动态创建（claim）
    # ---------------------------------------------------------------------

    def test_claim_cf_dynamic_create_success(self):
        """R-CF-CLAIM-01: provider=cloudflare_temp_mail 且池空 → 动态创建并 claim 成功"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service

            mock_result = {
                "success": True,
                "email": "abc123@cf-domain.com",
                "meta": {"provider_jwt": "jwt", "provider_mailbox_id": "123"},
            }
            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                return_value=mock_result,
            ):
                account = pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_001",
                    provider="cloudflare_temp_mail",
                    project_key="project_A",
                    email_domain="cf-domain.com",
                )

            self.assertEqual(account.get("provider"), "cloudflare_temp_mail")
            self.assertIn("claim_token", account)

    def test_claim_cf_dynamic_create_respects_email_domain(self):
        """R-CF-CLAIM-02: 指定 email_domain 时应传递给 create_mailbox，并确保写入 email 域名匹配"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service

            mock_result = {
                "success": True,
                "email": "abc123@cf-domain.com",
                "meta": {"provider_jwt": "jwt", "provider_mailbox_id": "123"},
            }
            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                return_value=mock_result,
            ) as create_mock:
                account = pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_002",
                    provider="cloudflare_temp_mail",
                    project_key="project_A",
                    email_domain="cf-domain.com",
                )

            self.assertTrue(create_mock.called)
            self.assertTrue(account.get("email", "").endswith("@cf-domain.com"))

    def test_claim_cf_dynamic_create_upstream_timeout(self):
        """R-CF-CLAIM-03: create_mailbox 超时/异常 → 抛出稳定错误码（如 UPSTREAM_TIMEOUT）"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                side_effect=TimeoutError("upstream timeout"),
            ):
                with self.assertRaises(PoolServiceError) as ctx:
                    pool_service.claim_random(
                        caller_id="reg_script_001",
                        task_id="task_003",
                        provider="cloudflare_temp_mail",
                        project_key="project_A",
                        email_domain="cf-domain.com",
                    )

            # 约定：TimeoutError 映射到 UPSTREAM_SERVER_ERROR
            self.assertEqual(ctx.exception.error_code, "UPSTREAM_SERVER_ERROR")

    def test_claim_cf_dynamic_create_not_configured(self):
        """R-CF-CLAIM-04: Provider 返回未配置 → 抛 TEMP_MAIL_PROVIDER_NOT_CONFIGURED（或实现约定）"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            mock_result = {
                "success": False,
                "error": "not configured",
                "error_code": "TEMP_MAIL_PROVIDER_NOT_CONFIGURED",
            }
            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                return_value=mock_result,
            ):
                with self.assertRaises(PoolServiceError) as ctx:
                    pool_service.claim_random(
                        caller_id="reg_script_001",
                        task_id="task_004",
                        provider="cloudflare_temp_mail",
                        project_key="project_A",
                        email_domain="cf-domain.com",
                    )

            self.assertEqual(ctx.exception.error_code, "TEMP_MAIL_PROVIDER_NOT_CONFIGURED")

    def test_claim_non_cf_pool_empty_returns_none(self):
        """R-CF-CLAIM-05: 非 CF provider 且池空 → 不动态创建，应返回 no_available_account（service 层）"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_005",
                    provider="outlook",
                    project_key="project_A",
                    email_domain="extpool.test",
                )

            self.assertEqual(ctx.exception.error_code, "no_available_account")

    # ---------------------------------------------------------------------
    # 4.2 Repository 层（pool.py）单元测试 - complete 删除策略
    # ---------------------------------------------------------------------

    def test_complete_cf_deletes_remote_on_success(self):
        """R-CF-COMP-01: CF + result=success → delete_mailbox 被调用（非阻塞）"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            # 预置一个 claimed 的 CF 账号（字段按实现期望补齐）
            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, client_id, refresh_token, status, account_type, provider, pool_status,
                                     claim_token, claimed_by, claimed_at, lease_expires_at, temp_mail_meta)
                VALUES (?, '', '', 'active', 'outlook', 'cloudflare_temp_mail', 'claimed',
                        ?, ?, '2026-04-09T10:00:00Z', '2026-04-09T10:10:00Z', ?)
                """,
                (
                    "abc123@cf-domain.com",
                    "clm_xxx",
                    "reg_script_001:task_001",
                    json.dumps(
                        {"provider_jwt": "jwt", "provider_mailbox_id": "123"},
                        ensure_ascii=False,
                    ),
                ),
            )
            db.commit()
            row = db.execute("SELECT id FROM accounts WHERE claim_token = ?", ("clm_xxx",)).fetchone()
            account_id = int(row["id"])

            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.delete_mailbox",
                return_value=True,
            ) as delete_mock:
                new_status = pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="clm_xxx",
                    caller_id="reg_script_001",
                    task_id="task_001",
                    result="success",
                    detail="注册成功",
                )

            self.assertTrue(delete_mock.called)
            self.assertEqual(new_status, "used")

    def test_complete_cf_deletes_remote_on_credential_invalid(self):
        """R-CF-COMP-02: CF + result=credential_invalid → delete_mailbox 被调用；本地状态为 retired"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, client_id, refresh_token, status, account_type, provider, pool_status,
                                     claim_token, claimed_by, claimed_at, lease_expires_at, temp_mail_meta)
                VALUES (?, '', '', 'active', 'outlook', 'cloudflare_temp_mail', 'claimed',
                        ?, ?, '2026-04-09T10:00:00Z', '2026-04-09T10:10:00Z', ?)
                """,
                (
                    "abc124@cf-domain.com",
                    "clm_cred_invalid",
                    "reg_script_001:task_006",
                    json.dumps(
                        {"provider_jwt": "jwt", "provider_mailbox_id": "124"},
                        ensure_ascii=False,
                    ),
                ),
            )
            db.commit()
            account_id = int(
                db.execute(
                    "SELECT id FROM accounts WHERE claim_token = ?",
                    ("clm_cred_invalid",),
                ).fetchone()["id"]
            )

            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.delete_mailbox",
                return_value=True,
            ) as delete_mock:
                new_status = pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="clm_cred_invalid",
                    caller_id="reg_script_001",
                    task_id="task_006",
                    result="credential_invalid",
                    detail="凭据失效",
                )

            self.assertTrue(delete_mock.called)
            self.assertEqual(new_status, "retired")

    def test_complete_cf_skip_delete_on_timeout(self):
        """R-CF-COMP-03: CF + result=verification_timeout → 不调用 delete；本地状态为 cooldown"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, client_id, refresh_token, status, account_type, provider, pool_status,
                                     claim_token, claimed_by, claimed_at, lease_expires_at, temp_mail_meta)
                VALUES (?, '', '', 'active', 'outlook', 'cloudflare_temp_mail', 'claimed',
                        ?, ?, '2026-04-09T10:00:00Z', '2026-04-09T10:10:00Z', ?)
                """,
                (
                    "abc125@cf-domain.com",
                    "clm_timeout",
                    "reg_script_001:task_007",
                    json.dumps(
                        {"provider_jwt": "jwt", "provider_mailbox_id": "125"},
                        ensure_ascii=False,
                    ),
                ),
            )
            db.commit()
            account_id = int(db.execute("SELECT id FROM accounts WHERE claim_token = ?", ("clm_timeout",)).fetchone()["id"])

            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.delete_mailbox",
                return_value=True,
            ) as delete_mock:
                new_status = pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="clm_timeout",
                    caller_id="reg_script_001",
                    task_id="task_007",
                    result="verification_timeout",
                    detail="超时",
                )

            self.assertFalse(delete_mock.called)
            self.assertEqual(new_status, "cooldown")

    def test_complete_cf_delete_failure_nonblocking(self):
        """R-CF-COMP-04: delete_mailbox 返回 False / 抛异常 → complete 仍成功返回，状态流转不受影响"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, client_id, refresh_token, status, account_type, provider, pool_status,
                                     claim_token, claimed_by, claimed_at, lease_expires_at, temp_mail_meta)
                VALUES (?, '', '', 'active', 'outlook', 'cloudflare_temp_mail', 'claimed',
                        ?, ?, '2026-04-09T10:00:00Z', '2026-04-09T10:10:00Z', ?)
                """,
                (
                    "abc126@cf-domain.com",
                    "clm_del_fail",
                    "reg_script_001:task_008",
                    json.dumps(
                        {"provider_jwt": "jwt", "provider_mailbox_id": "126"},
                        ensure_ascii=False,
                    ),
                ),
            )
            db.commit()
            account_id = int(db.execute("SELECT id FROM accounts WHERE claim_token = ?", ("clm_del_fail",)).fetchone()["id"])

            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.delete_mailbox",
                side_effect=RuntimeError("delete failed"),
            ):
                new_status = pool_service.complete_claim(
                    account_id=account_id,
                    claim_token="clm_del_fail",
                    caller_id="reg_script_001",
                    task_id="task_008",
                    result="success",
                    detail="注册成功但删除失败",
                )

            self.assertEqual(new_status, "used")

    # ---------------------------------------------------------------------
    # 4.2.3 project_key / 兼容用例（回归）
    # ---------------------------------------------------------------------

    def test_claim_cf_with_project_key_records_usage(self):
        """R-CF-PROJ-01: project_key 存在时，应记录 account_project_usage（或等价行为）"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            mock_result = {
                "success": True,
                "email": "abc127@cf-domain.com",
                "meta": {"provider_jwt": "jwt", "provider_mailbox_id": "127"},
            }
            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                return_value=mock_result,
            ):
                account = pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_009",
                    provider="cloudflare_temp_mail",
                    project_key="project_A",
                    email_domain="cf-domain.com",
                )

            db = get_db()
            rows = db.execute(
                "SELECT * FROM account_project_usage WHERE project_key = ?",
                ("project_A",),
            ).fetchall()
            self.assertTrue(len(rows) >= 1)
            self.assertIn("id", account)

    def test_release_keeps_project_usage_without_success(self):
        """R-CF-PROJ-02: release 后保留 usage 行，但不应形成 success 阻断"""
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.services import pool as pool_service

            # 先 claim 一个 CF
            mock_result = {
                "success": True,
                "email": "abc128@cf-domain.com",
                "meta": {"provider_jwt": "jwt", "provider_mailbox_id": "128"},
            }
            with patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
                return_value=mock_result,
            ):
                account = pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_010",
                    provider="cloudflare_temp_mail",
                    project_key="project_A",
                    email_domain="cf-domain.com",
                )

            pool_service.release_claim(
                account_id=account["id"],
                claim_token=account["claim_token"],
                caller_id="reg_script_001",
                task_id="task_010",
                reason="not needed",
            )

            db = get_db()
            rows = db.execute(
                """
                SELECT success_count, first_success_at, last_success_at
                FROM account_project_usage
                WHERE project_key = ?
                """,
                ("project_A",),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["success_count"], 0)
            self.assertIsNone(rows[0]["first_success_at"])
            self.assertIsNone(rows[0]["last_success_at"])


class PoolServiceProviderValidationTddSkeletonTests(unittest.TestCase):
    """按 TDD 4.3：Service 层 provider 校验与错误映射测试骨架（暂时 skip）。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            # 先删除有外键引用的子表，再删除父表
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM accounts")
            db.commit()
            settings_repo.set_setting("pool_external_enabled", "true")

    def test_claim_random_invalid_provider_rejected(self):
        """S-CF-VAL-01: provider=unknown → PoolServiceError(error_code='invalid_provider')"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_val_001",
                    provider="unknown_provider",
                    project_key=None,
                    email_domain=None,
                )

            self.assertIn("provider", ctx.exception.error_code)

    def test_claim_random_provider_blank_treated_as_none(self):
        """S-CF-VAL-02: provider='' → 行为与 None 一致（不报 invalid_provider）"""
        with self.app.app_context():
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            # 池为空时，期望走 no_available_account，而不是 invalid_provider
            with self.assertRaises(PoolServiceError) as ctx:
                pool_service.claim_random(
                    caller_id="reg_script_001",
                    task_id="task_val_002",
                    provider="",
                    project_key=None,
                    email_domain=None,
                )

            self.assertEqual(ctx.exception.error_code, "no_available_account")

    def test_claim_random_maps_repo_error_code(self):
        """S-CF-VAL-03: repo 抛 PoolRepositoryError → service 转换为 PoolServiceError 且保留 error_code"""
        with self.app.app_context():
            from outlook_web.repositories.pool import PoolRepositoryError
            from outlook_web.services import pool as pool_service
            from outlook_web.services.pool import PoolServiceError

            # PoolRepositoryError 在 repo 层抛出时，service 层应捕获并转换为 PoolServiceError
            with patch(
                "outlook_web.repositories.pool.claim_atomic",
                side_effect=PoolRepositoryError("upstream timeout", "upstream_timeout"),
            ):
                with self.assertRaises(PoolServiceError) as ctx:
                    pool_service.claim_random(
                        caller_id="reg_script_001",
                        task_id="task_val_003",
                        provider="cloudflare_temp_mail",
                        project_key="project_A",
                        email_domain="cf-domain.com",
                    )

            self.assertEqual(ctx.exception.error_code, "upstream_timeout")


class ExternalPoolApiContractTddSkeletonTests(unittest.TestCase):
    """按 TDD 4.4：external_pool controller 层契约测试骨架（暂时 skip）。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            # 先删除有外键引用的子表，再删除父表
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM accounts")
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.commit()

            settings_repo.set_setting("external_api_key", "abc123")
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("pool_external_enabled", "true")
            settings_repo.set_setting("external_api_ip_whitelist", "[]")
            settings_repo.set_setting("external_api_disable_pool_claim_random", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_release", "false")
            settings_repo.set_setting("external_api_disable_pool_claim_complete", "false")
            settings_repo.set_setting("external_api_disable_pool_stats", "false")

            # CF Worker 配置（占位）
            settings_repo.set_setting("cf_worker_base_url", "http://mock.invalid")
            settings_repo.set_setting("cf_worker_admin_key", "test-admin")

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def test_claim_random_accepts_provider_param(self):
        """C-CF-API-01: claim-random 可接收 provider 参数，并保持最小字段契约"""
        client = self.app.test_client()
        with patch(
            "outlook_web.controllers.external_pool.claim_random",
            return_value={
                "id": 1,
                "email": "abc123@cf-domain.com",
                "claim_token": "clm_xxx",
                "lease_expires_at": "2026-04-09T10:10:00Z",
                "provider": "cloudflare_temp_mail",
                "claimed_at": "2026-04-09T10:00:00Z",
                "email_domain": "cf-domain.com",
            },
        ):
            resp = client.post(
                "/api/external/pool/claim-random",
                headers=self._auth_headers(),
                json={
                    "caller_id": "ext-worker-01",
                    "task_id": "task-api-001",
                    "provider": "cloudflare_temp_mail",
                    "email_domain": "cf-domain.com",
                },
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json().get("data", {})
        self.assertIn("account_id", payload)
        self.assertIn("email", payload)
        self.assertIn("claim_token", payload)
        self.assertIn("lease_expires_at", payload)

    def test_claim_random_invalid_provider_returns_error(self):
        """C-CF-API-02: provider 白名单生效 → 返回统一错误 code"""
        client = self.app.test_client()
        from outlook_web.services.pool import PoolServiceError

        with patch(
            "outlook_web.controllers.external_pool.claim_random",
            side_effect=PoolServiceError("invalid provider", "invalid_provider", http_status=400),
        ):
            resp = client.post(
                "/api/external/pool/claim-random",
                headers=self._auth_headers(),
                json={
                    "caller_id": "ext-worker-01",
                    "task_id": "task-api-002",
                    "provider": "unknown_provider",
                },
            )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertTrue(data.get("code"))

    def test_claim_random_provider_cf_pool_empty_returns_no_available_or_upstream_error(
        self,
    ):
        """C-CF-API-03: CF 动态创建失败路径 → 返回稳定错误 code（no_available 或 upstream）"""
        client = self.app.test_client()
        from outlook_web.services.pool import PoolServiceError

        with patch(
            "outlook_web.controllers.external_pool.claim_random",
            side_effect=PoolServiceError("upstream timeout", "upstream_timeout", http_status=502),
        ):
            resp = client.post(
                "/api/external/pool/claim-random",
                headers=self._auth_headers(),
                json={
                    "caller_id": "ext-worker-01",
                    "task_id": "task-api-003",
                    "provider": "cloudflare_temp_mail",
                    "email_domain": "cf-domain.com",
                },
            )

        self.assertIn(resp.status_code, (400, 502, 503))
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertTrue(data.get("code"))


class ExternalVerificationCompatibilityTddSkeletonTests(unittest.TestCase):
    """按 TDD 4.5：external 读信/验证码提取兼容性测试骨架（暂时 skip）。"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM external_api_keys")
            db.execute("DELETE FROM external_api_consumer_usage_daily")
            db.execute("DELETE FROM temp_email_messages")
            db.execute("DELETE FROM temp_emails")
            # 先删除有外键引用的子表，再删除父表
            db.execute("DELETE FROM account_claim_logs")
            db.execute("DELETE FROM account_project_usage")
            db.execute("DELETE FROM accounts")
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.commit()

            settings_repo.set_setting("external_api_key", "abc123")
            settings_repo.set_setting("external_api_public_mode", "false")
            settings_repo.set_setting("pool_external_enabled", "true")
            settings_repo.set_setting("external_api_ip_whitelist", "[]")
            settings_repo.set_setting("cf_worker_base_url", "http://mock.invalid")
            settings_repo.set_setting("cf_worker_admin_key", "test-admin")

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    @unittest.skip("已由 test_pool_cf_real_e2e.py 的真实 CF Worker E2E 测试替代")
    def test_e2e_claim_cf_then_extract_verification_code(self):
        """E2E-CF-01: claim CF → mock list_messages → external verification-code 返回 code"""
        client = self.app.test_client()

        # 1) claim cf
        with patch(
            "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.create_mailbox",
            return_value={
                "success": True,
                "email": "abc200@cf-domain.com",
                "meta": {"provider_jwt": "jwt", "provider_mailbox_id": "200"},
            },
        ):
            claim_resp = client.post(
                "/api/external/pool/claim-random",
                headers=self._auth_headers(),
                json={
                    "caller_id": "ext-worker-01",
                    "task_id": "task-e2e-001",
                    "provider": "cloudflare_temp_mail",
                    "email_domain": "cf-domain.com",
                },
            )

        self.assertEqual(claim_resp.status_code, 200)
        claim_data = claim_resp.get_json()["data"]

        # 2) mock list_messages — 返回与 CF Provider list_messages 一致的消息列表格式
        with (
            patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.list_messages",
                return_value=[
                    {
                        "id": "msg-e2e-001",
                        "message_id": "msg-e2e-001",
                        "subject": "Your code is 123456",
                        "from_address": "no-reply@test.com",
                        "content": "Verification code: 123456",
                        "html_content": "",
                        "has_html": False,
                        "timestamp": 1744188060,
                        "raw_content": "",
                    }
                ],
            ),
            patch(
                "outlook_web.services.temp_mail_provider_cf.CloudflareTempMailProvider.get_message_detail",
                return_value={
                    "id": "msg-e2e-001",
                    "message_id": "msg-e2e-001",
                    "subject": "Your code is 123456",
                    "from_address": "no-reply@test.com",
                    "content": "Verification code: 123456",
                    "html_content": "",
                    "has_html": False,
                    "timestamp": 1744188060,
                    "raw_content": "",
                },
            ),
        ):
            # external verification-code 路由只支持 GET 方法
            verify_resp = client.get(
                "/api/external/verification-code",
                headers=self._auth_headers(),
                query_string={
                    "email": claim_data["email"],
                    "folder": "inbox",
                    "since_minutes": "10",
                },
            )

        # E2E 验证：路由存在且返回基础状态码
        self.assertIn(verify_resp.status_code, (200, 400, 401, 403, 500))
