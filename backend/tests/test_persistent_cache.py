"""Tests for persistent cache module."""
from __future__ import annotations

import os
import time
import unittest


class TestPersistentCacheMemoryMode(unittest.TestCase):
    """Test in-memory fallback mode (PERSISTENT_CACHE_ENABLED=false)."""

    def setUp(self) -> None:
        os.environ['PERSISTENT_CACHE_ENABLED'] = 'false'
        import importlib
        import backend.common.persistent_cache as pc
        importlib.reload(pc)
        self.pc = pc
        self.pc.clear_all()

    def test_set_and_get(self) -> None:
        self.pc.set_cached('key1', {'data': 42}, ttl_seconds=60)
        result = self.pc.get_cached('key1')
        self.assertIsNotNone(result)
        self.assertEqual(result['data'], 42)

    def test_missing_key_returns_none(self) -> None:
        self.assertIsNone(self.pc.get_cached('nonexistent'))

    def test_ttl_expiry(self) -> None:
        self.pc.set_cached('key2', {'data': 'temp'}, ttl_seconds=0.1)
        self.assertIsNotNone(self.pc.get_cached('key2'))
        time.sleep(0.15)
        self.assertIsNone(self.pc.get_cached('key2'))

    def test_cleanup_expired(self) -> None:
        self.pc.set_cached('exp1', {'a': 1}, ttl_seconds=0.05)
        self.pc.set_cached('keep1', {'b': 2}, ttl_seconds=60)
        time.sleep(0.1)
        removed = self.pc.cleanup_expired()
        self.assertEqual(removed, 1)
        self.assertIsNone(self.pc.get_cached('exp1'))
        self.assertIsNotNone(self.pc.get_cached('keep1'))

    def test_zero_ttl_never_expires(self) -> None:
        self.pc.set_cached('permanent', {'x': True}, ttl_seconds=0)
        time.sleep(0.05)
        self.assertIsNotNone(self.pc.get_cached('permanent'))

    def test_overwrite_existing_key(self) -> None:
        self.pc.set_cached('key3', {'v': 1}, ttl_seconds=60)
        self.pc.set_cached('key3', {'v': 2}, ttl_seconds=60)
        result = self.pc.get_cached('key3')
        self.assertEqual(result['v'], 2)


class TestPersistentCachePgMode(unittest.TestCase):
    """Test Postgres mode falls back to memory when Supabase unavailable."""

    def setUp(self) -> None:
        os.environ['PERSISTENT_CACHE_ENABLED'] = 'true'
        import importlib
        import backend.common.persistent_cache as pc
        importlib.reload(pc)
        self.pc = pc
        self.pc.clear_all()

    def test_pg_falls_back_to_mem_without_credentials(self) -> None:
        self.pc.set_cached('pg_key', {'data': 'test'}, ttl_seconds=60)
        result = self.pc.get_cached('pg_key')
        self.assertIsNotNone(result)
        self.assertEqual(result['data'], 'test')


if __name__ == '__main__':
    unittest.main()
