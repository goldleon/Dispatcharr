"""Regression tests for Bug 2: Xtream Codes Live TV Streams Buffering & X-Accel-Buffering."""

import re
from unittest.mock import MagicMock, patch
from django.http import StreamingHttpResponse
from django.test import RequestFactory, SimpleTestCase
from apps.proxy.live_proxy.views import stream_ts
from apps.proxy.vod_proxy.views import stream_vod


class NginxConfigRegressionTests(SimpleTestCase):
    def setUp(self):
        with open("docker/nginx.conf", "r", encoding="utf-8") as f:
            self.nginx_conf = f.read()

    def test_root_location_has_unbuffered_uwsgi_and_long_timeout(self):
        """location / must have uwsgi_buffering off and 3600s timeouts."""
        pattern = r"location\s+/\s*\{([^}]+)\}"
        match = re.search(pattern, self.nginx_conf)
        self.assertIsNotNone(match, "location / block not found in docker/nginx.conf")
        block = match.group(1)
        self.assertIn("uwsgi_buffering off;", block)
        self.assertIn("uwsgi_read_timeout 3600s;", block)
        self.assertIn("uwsgi_send_timeout 3600s;", block)
        self.assertIn("client_max_body_size 0;", block)

    def test_xtream_codes_live_movie_series_location_configured(self):
        """location ~ ^/(live|movie|series)/ must have uwsgi_buffering off and 3600s timeouts."""
        pattern = r"location\s+~\s+\^/\(live\|movie\|series\)/\s*\{([^}]+)\}"
        match = re.search(pattern, self.nginx_conf)
        self.assertIsNotNone(match, "location ~ ^/(live|movie|series)/ block not found in docker/nginx.conf")
        block = match.group(1)
        self.assertIn("uwsgi_buffering off;", block)
        self.assertIn("uwsgi_read_timeout 3600s;", block)
        self.assertIn("uwsgi_send_timeout 3600s;", block)
        self.assertIn("client_max_body_size 0;", block)

    def test_xtream_codes_direct_stream_urls_location_configured(self):
        r"""location ~ ^/[^/]+/[^/]+/\d+(?:\.(?:ts|m3u8|mkv|mp4))?$ must be configured."""
        pattern = r"location\s+~\s+\^/\[\^/\]\+/\[\^/\]\+/\\d\+\(\?:\\\.\(\?:ts\|m3u8\|mkv\|mp4\)\)\?\$\s*\{([^}]+)\}"
        match = re.search(pattern, self.nginx_conf)
        self.assertIsNotNone(match, "Direct XC stream location block not found in docker/nginx.conf")
        block = match.group(1)
        self.assertIn("uwsgi_buffering off;", block)
        self.assertIn("uwsgi_read_timeout 3600s;", block)
        self.assertIn("uwsgi_send_timeout 3600s;", block)
        self.assertIn("client_max_body_size 0;", block)

    def test_xtream_codes_url_regex_matching(self):
        """Verify URL matching patterns for all Xtream Codes Live TV and VOD routes."""
        xc_prefix_regex = re.compile(r"^/(live|movie|series)/")
        xc_direct_regex = re.compile(r"^/[^/]+/[^/]+/\d+(?:\.(?:ts|m3u8|mkv|mp4))?$")
        admin_redirect_regex = re.compile(r"^/admin(?!/[^/]+/[^/]+/?$)(?:/|$)")

        # Prefix routes
        self.assertTrue(xc_prefix_regex.match("/live/hometv001/pass123/681313"))
        self.assertTrue(xc_prefix_regex.match("/live/hometv001/pass123/681313.ts"))
        self.assertTrue(xc_prefix_regex.match("/movie/hometv001/pass123/681313.mp4"))
        self.assertTrue(xc_prefix_regex.match("/series/hometv001/pass123/681313.mkv"))

        # Direct 3-part routes
        self.assertTrue(xc_direct_regex.match("/hometv001/5zcjr66u5ck/681313"))
        self.assertTrue(xc_direct_regex.match("/hometv001/5zcjr66u5ck/681313.ts"))
        self.assertTrue(xc_direct_regex.match("/hometv001/5zcjr66u5ck/681313.m3u8"))
        self.assertTrue(xc_direct_regex.match("/admin/5zcjr66u5ck/681313"))

        # Admin route conflict checks: admin streams must NOT match the admin redirect
        self.assertIsNone(admin_redirect_regex.match("/admin/5zcjr66u5ck/681313"))
        # Regular admin paths MUST match the redirect
        self.assertIsNotNone(admin_redirect_regex.match("/admin"))
        self.assertIsNotNone(admin_redirect_regex.match("/admin/"))
        self.assertIsNotNone(admin_redirect_regex.match("/admin/login/"))


class AccelBufferingHeaderRegressionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.proxy.live_proxy.views.close_old_connections")
    @patch("apps.proxy.live_proxy.views.create_stream_generator")
    @patch("apps.proxy.live_proxy.views._resolve_output_format", return_value="mpegts")
    @patch("apps.proxy.live_proxy.views._resolve_output_profile")
    @patch(
        "apps.proxy.live_proxy.views.ChannelService.is_channel_unavailable_for_new_clients",
        return_value=False,
    )
    @patch("apps.proxy.live_proxy.views.get_stream_object")
    @patch("apps.proxy.live_proxy.views.network_access_allowed", return_value=True)
    @patch("apps.proxy.live_proxy.views.ProxyServer")
    def test_live_stream_ts_sets_x_accel_buffering_no(
        self,
        mock_proxy_cls,
        _network_ok,
        mock_get_stream_object,
        _unavailable,
        _resolve_profile,
        _resolve_format,
        mock_create_generator,
        _close_db,
    ):
        """stream_ts response must include X-Accel-Buffering: no header."""
        channel_id = "test-channel-uuid"
        channel = MagicMock()
        channel.id = 1
        channel.uuid = channel_id
        channel.name = "Test Channel"
        channel.get_stream_profile.return_value = MagicMock(is_redirect=lambda: False)
        mock_get_stream_object.return_value = channel

        proxy_server = MagicMock()
        proxy_server.redis_client = MagicMock()
        proxy_server.redis_client.exists.return_value = True
        proxy_server.redis_client.hgetall.return_value = {"state": "active"}
        proxy_server.stream_buffers = {channel_id: MagicMock()}
        proxy_server.client_managers = {channel_id: MagicMock()}
        proxy_server.check_if_channel_exists.return_value = True
        proxy_server.get_buffer.return_value = MagicMock()
        proxy_server.am_i_owner.return_value = False
        proxy_server.ensure_output_profile.return_value = True
        proxy_server._channels_setting_up = set()
        mock_proxy_cls.get_instance.return_value = proxy_server

        mock_create_generator.return_value = lambda: iter([b"ts_data"])

        request = self.factory.get(f"/proxy/ts/stream/{channel_id}/")
        request.user = MagicMock(is_authenticated=False)

        response = stream_ts(request, channel_id)

        self.assertIsInstance(response, StreamingHttpResponse)
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
        self.assertEqual(response.headers.get("Cache-Control"), "no-cache")

    @patch("apps.proxy.vod_proxy.views._select_vod_stream")
    @patch("apps.proxy.vod_proxy.views.check_user_stream_limits", return_value=True)
    @patch("core.models.CoreSettings.is_default_stream_profile_redirect", return_value=False)
    @patch("apps.proxy.vod_proxy.views.network_access_allowed", return_value=True)
    @patch("apps.proxy.vod_proxy.views._vod_playback_allowed", return_value=True)
    @patch("apps.proxy.vod_proxy.views._user_from_vod_request")
    @patch("apps.proxy.vod_proxy.views.MultiWorkerVODConnectionManager")
    @patch("apps.proxy.vod_proxy.views.close_old_connections")
    def test_vod_stream_sets_x_accel_buffering_no(
        self,
        _close_db,
        mock_cm_cls,
        mock_user_from_req,
        _playback_allowed,
        _network_ok,
        _is_redirect,
        _check_limits,
        mock_select_stream,
    ):
        """stream_vod response must include X-Accel-Buffering: no header."""
        user = MagicMock(is_authenticated=True, user_level=10, stream_limit=0)
        mock_user_from_req.return_value = user

        content_obj = MagicMock()
        content_obj.uuid = "movie-uuid-123"
        m3u_profile = MagicMock(id=1, is_active=True, max_streams=5)
        mock_select_stream.return_value = {
            "content_obj": content_obj,
            "m3u_account": MagicMock(name="account", is_active=True),
            "m3u_profile": m3u_profile,
            "current_connections": 0,
            "final_stream_url": "http://upstream.example.com/movie.mp4",
        }

        mock_cm = MagicMock()
        streaming_resp = StreamingHttpResponse(iter([b"vod_data"]), content_type="video/mp4")
        mock_cm.stream_content_with_session.return_value = streaming_resp
        mock_cm.get_connection_count_for_profile.return_value = 0
        mock_cm_cls.get_instance.return_value = mock_cm

        session_id = "vod_test_session_123"
        request = self.factory.get(f"/proxy/vod/movie/movie-uuid-123/{session_id}")
        request.user = user

        response = stream_vod(request, "movie", "movie-uuid-123", session_id=session_id, profile_id=1, user=user)

        self.assertIsInstance(response, StreamingHttpResponse)
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
