"""Regression tests for Bug 1: Daphne WebSocket Server Gevent Deadlock."""

from unittest.mock import AsyncMock, MagicMock, patch
from django.test import SimpleTestCase
from asgiref.sync import async_to_sync
from dispatcharr.consumers import MyWebSocketConsumer


class DaphneWebSocketRegressionTests(SimpleTestCase):
    def test_asgi_file_does_not_call_monkey_patch(self):
        """dispatcharr/asgi.py must NOT contain gevent.monkey or monkey.patch_all()."""
        with open("dispatcharr/asgi.py", "r", encoding="utf-8") as f:
            asgi_content = f.read()

        self.assertNotIn("monkey.patch_all", asgi_content)
        self.assertNotIn("gevent", asgi_content)

    def test_ws_modules_do_not_import_or_call_gevent_monkey_patch(self):
        """Audit routing, consumers, and jwt_ws_auth to ensure none import gevent monkey patching."""
        modules_to_check = [
            "dispatcharr/routing.py",
            "dispatcharr/consumers.py",
            "dispatcharr/jwt_ws_auth.py",
        ]
        for path in modules_to_check:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("monkey.patch_all", content, f"{path} must not call monkey.patch_all()")
            self.assertNotIn("from gevent import monkey", content, f"{path} must not import gevent.monkey")

    def test_consumers_imports_sync_to_async(self):
        """dispatcharr/consumers.py must import sync_to_async for cached IP lookups."""
        import dispatcharr.consumers as consumers_module
        self.assertTrue(hasattr(consumers_module, "sync_to_async"))

    @patch("dispatcharr.consumers.sync_to_async")
    def test_consumer_connect_with_cached_ip(self, mock_sync_to_async):
        """MyWebSocketConsumer.connect can push cached IP lookup via sync_to_async."""
        mock_sync_to_async.return_value = AsyncMock(
            return_value={"ip": "192.0.2.1", "country": "US", "verified_at": "12345"}
        )

        consumer = MyWebSocketConsumer()
        mock_layer = MagicMock()
        mock_layer.group_add = AsyncMock()
        consumer.channel_layer = mock_layer
        consumer.scope = {
            "user": MagicMock(is_authenticated=True),
        }
        consumer.channel_name = "test_channel_name"
        consumer.accept = AsyncMock()
        consumer.send = AsyncMock()
        consumer.close = AsyncMock()

        async_to_sync(consumer.connect)()

        consumer.accept.assert_awaited_once()
        mock_layer.group_add.assert_awaited_once_with("updates", "test_channel_name")
        self.assertEqual(consumer.send.await_count, 2)
        # First send is connection_established
        first_call = consumer.send.await_args_list[0]
        self.assertIn("connection_established", first_call.kwargs.get("text_data", ""))
        # Second send is ip_lookup_complete
        second_call = consumer.send.await_args_list[1]
        self.assertIn("ip_lookup_complete", second_call.kwargs.get("text_data", ""))
        self.assertIn("192.0.2.1", second_call.kwargs.get("text_data", ""))
