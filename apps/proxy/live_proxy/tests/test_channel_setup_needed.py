from unittest.mock import MagicMock
from django.test import SimpleTestCase
from apps.proxy.live_proxy.constants import ChannelState, ChannelMetadataField
from apps.proxy.live_proxy.views import _channel_setup_needed


class ChannelSetupNeededZombieTests(SimpleTestCase):
    def setUp(self):
        self.channel_id = "test-channel-uuid-1234"
        self.proxy_server = MagicMock()
        self.proxy_server.worker_id = "worker-1"
        self.proxy_server.stream_managers = {}
        self.proxy_server.stream_buffers = {}
        self.redis_client = MagicMock()
        self.proxy_server.redis_client = self.redis_client

    def test_zombie_channel_active_state_no_owner_lock(self):
        """When metadata says active but no owner lock exists, treat as zombie, clean up, and return needs_setup=True."""
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.ACTIVE,
            ChannelMetadataField.OWNER: "dead-worker",
        }
        self.proxy_server.get_channel_owner.return_value = None

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertTrue(needs_setup)
        self.assertIsNone(state)
        self.assertFalse(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_called_once()

    def test_zombie_channel_owner_heartbeat_dead(self):
        """When owner lock exists for remote worker but remote worker heartbeat is gone, treat as zombie."""
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.ACTIVE,
            ChannelMetadataField.OWNER: "crashed-worker",
        }
        self.proxy_server.get_channel_owner.return_value = "crashed-worker"
        # Heartbeat does not exist in Redis
        self.redis_client.exists.return_value = False

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertTrue(needs_setup)
        self.assertIsNone(state)
        self.assertFalse(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_called_once()

    def test_remote_worker_active_and_healthy(self):
        """When remote worker holds owner lock and heartbeat is active, do not re-setup."""
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.ACTIVE,
            ChannelMetadataField.OWNER: "worker-remote",
        }
        self.proxy_server.get_channel_owner.return_value = "worker-remote"
        self.redis_client.exists.return_value = True

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertFalse(needs_setup)
        self.assertEqual(state, ChannelState.ACTIVE)
        self.assertFalse(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_not_called()

    def test_remote_worker_initializing(self):
        """When remote worker is initializing and alive, wait_for_init should be True."""
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.INITIALIZING,
            ChannelMetadataField.OWNER: "worker-remote",
        }
        self.proxy_server.get_channel_owner.return_value = "worker-remote"
        self.redis_client.exists.return_value = True

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertFalse(needs_setup)
        self.assertEqual(state, ChannelState.INITIALIZING)
        self.assertTrue(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_not_called()

    def test_local_channel_active(self):
        """When local worker already buffers the channel, no setup needed."""
        self.proxy_server.stream_buffers = {self.channel_id: MagicMock()}
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.ACTIVE,
            ChannelMetadataField.OWNER: "worker-1",
        }

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertFalse(needs_setup)
        self.assertEqual(state, ChannelState.ACTIVE)
        self.assertFalse(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_not_called()

    def test_stopping_channel_not_reinitialized_as_zombie(self):
        """Stopping state should be respected so stopping gate can reject with 503."""
        self.redis_client.hgetall.return_value = {
            ChannelMetadataField.STATE: ChannelState.STOPPING,
        }

        needs_setup, state, wait_for_init = _channel_setup_needed(self.proxy_server, self.channel_id)

        self.assertFalse(needs_setup)
        self.assertEqual(state, ChannelState.STOPPING)
        self.assertFalse(wait_for_init)
        self.proxy_server._clean_zombie_channel.assert_not_called()
