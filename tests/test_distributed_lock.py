import time
import unittest
import uuid

from tests._import_app import import_web_app_module


class DistributedLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()

    def test_acquire_and_release_distributed_lock(self):
        conn = self.module.create_sqlite_connection()
        try:
            lock_name = "test_lock_" + uuid.uuid4().hex
            owner_a = "a_" + uuid.uuid4().hex
            owner_b = "b_" + uuid.uuid4().hex

            ok, info = self.module.acquire_distributed_lock(conn, lock_name, owner_a, ttl_seconds=60)
            self.assertTrue(ok)
            self.assertIsNone(info)

            ok2, info2 = self.module.acquire_distributed_lock(conn, lock_name, owner_b, ttl_seconds=60)
            self.assertFalse(ok2)
            self.assertIsInstance(info2, dict)
            self.assertEqual(info2.get("owner_id"), owner_a)

            released = self.module.release_distributed_lock(conn, lock_name, owner_a)
            self.assertTrue(released)

            ok3, info3 = self.module.acquire_distributed_lock(conn, lock_name, owner_b, ttl_seconds=60)
            self.assertTrue(ok3)
            self.assertIsNone(info3)
        finally:
            conn.close()

    def test_expired_lock_can_be_taken_over(self):
        conn = self.module.create_sqlite_connection()
        try:
            lock_name = "test_lock_expired_" + uuid.uuid4().hex
            owner_a = "a_" + uuid.uuid4().hex
            owner_b = "b_" + uuid.uuid4().hex

            ok, _ = self.module.acquire_distributed_lock(conn, lock_name, owner_a, ttl_seconds=1)
            self.assertTrue(ok)
            time.sleep(1.2)

            ok2, info2 = self.module.acquire_distributed_lock(conn, lock_name, owner_b, ttl_seconds=60)
            self.assertTrue(ok2)
            self.assertIsInstance(info2, dict)
            self.assertEqual(info2.get("previous_owner_id"), owner_a)
        finally:
            conn.close()
