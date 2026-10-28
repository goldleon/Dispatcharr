"""Regression tests for Bug 3: Redis SET NX Channel Ownership Lock."""

from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from apps.proxy.live_proxy.server import ProxyServer
from apps.proxy.live_proxy.redis_keys import RedisKeys


class RedisChannelOwnershipRegressionTests(SimpleTestCase):
    def setUp(self):
        # Create a fresh ProxyServer instance for testing
        self.server = ProxyServer.__new__(ProxyServer)
        self.server.worker_id = "test-worker-1"
        self.server.redis_client = MagicMock()
        self.server.stream_managers = {}
        self.server._live_stream_managers = {}
        self.channel_id = "channel-uuid-test"
        self.lock_key = RedisKeys.channel_owner(self.channel_id)

    def test_try_acquire_ownership_success_when_unlocked(self):
        """When key is not locked, SET NX EX returns True, worker acquires ownership."""
        self.server.redis_client.set.return_value = True

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)

        self.assertTrue(result)
        self.server.redis_client.set.assert_called_once_with(
            self.lock_key, "test-worker-1", nx=True, ex=30
        )
        self.server.redis_client.get.assert_not_called()

    def test_try_acquire_ownership_rejected_when_owned_by_another_worker(self):
        """CRITICAL REGRESSION: When another worker owns the lock, SET NX EX returns None (nil in Redis).

        Previously, `if acquired is None:` wrongly assumed ownership and returned True,
        causing multi-worker split-brain. It must return False.
        """
        # redis-py returns None when SET NX does not set because key already exists
        self.server.redis_client.set.return_value = None
        self.server.redis_client.get.return_value = "remote-worker-2"

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)

        self.assertFalse(result, "Must NOT assume ownership when another worker holds the lock!")
        self.server.redis_client.set.assert_called_once_with(
            self.lock_key, "test-worker-1", nx=True, ex=30
        )
        self.server.redis_client.get.assert_called_once_with(self.lock_key)
        self.server.redis_client.expire.assert_not_called()

    @patch("apps.proxy.live_proxy.server.logger.warning")
    def test_try_acquire_ownership_refreshes_when_already_owned_by_same_worker(self, mock_warn):
        """Case b: When Worker A re-checks ownership, SET NX returns None but GET matches worker_id;
        refreshes TTL without warning.
        """
        self.server.redis_client.set.return_value = None
        self.server.redis_client.get.return_value = "test-worker-1"

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)
        self.assertTrue(result)
        self.server.redis_client.expire.assert_called_once_with(self.lock_key, 30)

        # Ensure "Redis command failed during ownership acquisition - assuming ownership" is NOT logged
        for call in mock_warn.call_args_list:
            self.assertNotIn("Redis command failed during ownership acquisition", str(call))

    def test_try_acquire_ownership_decodes_bytes_owner(self):
        """When Redis returns bytes for channel owner, correctly decode and match."""
        self.server.redis_client.set.return_value = None
        self.server.redis_client.get.return_value = b"test-worker-1"

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)

        self.assertTrue(result)
        self.server.redis_client.expire.assert_called_once_with(self.lock_key, 30)

    @patch("apps.proxy.live_proxy.server.logger.warning")
    def test_try_acquire_ownership_redis_error_falls_back_to_ownership(self, mock_warn):
        """Case d: When Redis raises ConnectionError, log warning and fall back to assuming ownership (return True)."""
        from redis.exceptions import ConnectionError
        self.server.redis_client.set.side_effect = ConnectionError("Connection refused")
        self.server._setup_redis_connection = MagicMock()

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)

        self.assertTrue(result, "Must fall back to assuming ownership when Redis command fails")
        mock_warn.assert_any_call("Redis command failed during ownership acquisition - assuming ownership")

    def test_try_acquire_ownership_without_redis_client(self):
        """In standalone mode (no Redis), worker always acts as owner."""
        self.server.redis_client = None

        result = self.server.try_acquire_ownership(self.channel_id, ttl=30)

        self.assertTrue(result)

    def test_extend_ownership_with_bytes_owner(self):
        """extend_ownership correctly refreshes lease when owner in Redis is bytes."""
        self.server.redis_client.get.return_value = b"test-worker-1"

        result = self.server.extend_ownership(self.channel_id, ttl=30)

        self.assertTrue(result)
        self.server.redis_client.expire.assert_called_once_with(self.lock_key, 30)

    def test_extend_ownership_rejected_when_owned_by_another_worker(self):
        """extend_ownership returns False when channel is owned by someone else."""
        self.server.redis_client.get.return_value = "other-worker"

        result = self.server.extend_ownership(self.channel_id, ttl=30)

        self.assertFalse(result)
        self.server.redis_client.expire.assert_not_called()
