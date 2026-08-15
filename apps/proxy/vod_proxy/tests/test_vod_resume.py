"""
Tests for VOD resume offset calculations, range validation, manual skip,
and client disconnect handling.
"""

import errno
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
import requests.exceptions
import urllib3.exceptions

from apps.vod.models import Movie
from apps.proxy.vod_proxy.multi_worker_connection_manager import (
    parse_range_header,
    is_client_disconnect_error,
    MultiWorkerVODConnectionManager,
    RedisBackedVODConnection,
)


class TestParseRangeHeader(SimpleTestCase):
    """Test HTTP Range header parsing into (start_byte, end_byte)."""

    def test_missing_or_none_range_header(self):
        self.assertEqual(parse_range_header(None), (0, None))
        self.assertEqual(parse_range_header(""), (0, None))
        self.assertEqual(parse_range_header(123), (0, None))

    def test_open_ended_range_header(self):
        self.assertEqual(parse_range_header("bytes=1261347802-"), (1261347802, None))
        self.assertEqual(parse_range_header("bytes=0-"), (0, None))

    def test_closed_range_header(self):
        self.assertEqual(parse_range_header("bytes=100-200"), (100, 200))
        self.assertEqual(parse_range_header("bytes=0-499"), (0, 499))

    def test_suffix_range_header(self):
        # Suffix range: bytes=-500 on a 1000 byte file -> start=500, end=999
        self.assertEqual(parse_range_header("bytes=-500", content_length=1000), (500, 999))
        # Suffix range larger than content length -> start=0, end=999
        self.assertEqual(parse_range_header("bytes=-1500", content_length=1000), (0, 999))
        # Suffix range without content length -> (0, None) fallback
        self.assertEqual(parse_range_header("bytes=-500"), (0, None))
        self.assertEqual(parse_range_header("bytes=-0", content_length=1000), (0, None))

    def test_malformed_range_header(self):
        self.assertEqual(parse_range_header("invalid"), (0, None))
        self.assertEqual(parse_range_header("bytes=abc-def"), (0, None))
        self.assertEqual(parse_range_header("bytes=100"), (0, None))


class TestValidateRangeHeader(SimpleTestCase):
    """Test _validate_range_header on RedisBackedVODConnection."""

    def setUp(self):
        self.conn = RedisBackedVODConnection(
            session_id="test_session",
            redis_client=MagicMock(),
        )

    def test_valid_ranges(self):
        self.assertEqual(
            self.conn._validate_range_header("bytes=100-200", 1000),
            "bytes=100-200",
        )
        self.assertEqual(
            self.conn._validate_range_header("bytes=100-", 1000),
            "bytes=100-999",
        )
        self.assertEqual(
            self.conn._validate_range_header("bytes=0-", 1000),
            "bytes=0-999",
        )

    def test_suffix_range_validation(self):
        self.assertEqual(
            self.conn._validate_range_header("bytes=-300", 1000),
            "bytes=700-999",
        )
        self.assertEqual(
            self.conn._validate_range_header("bytes=-1500", 1000),
            "bytes=0-999",
        )

    def test_out_of_bounds_range(self):
        # Start byte >= content length -> 416 (None)
        self.assertIsNone(self.conn._validate_range_header("bytes=1000-", 1000))
        self.assertIsNone(self.conn._validate_range_header("bytes=1500-", 1000))
        # Start byte > end byte
        self.assertIsNone(self.conn._validate_range_header("bytes=500-400", 1000))

    def test_end_byte_clamping(self):
        # End byte exceeding content length is clamped to content_length - 1
        self.assertEqual(
            self.conn._validate_range_header("bytes=100-2000", 1000),
            "bytes=100-999",
        )


class TestIsClientDisconnectError(SimpleTestCase):
    """Test client disconnect exception detection."""

    def test_generator_exit(self):
        self.assertTrue(is_client_disconnect_error(GeneratorExit()))

    def test_broken_pipe(self):
        self.assertTrue(is_client_disconnect_error(BrokenPipeError()))

    def test_os_error_write_error(self):
        self.assertTrue(is_client_disconnect_error(OSError("write error")))
        self.assertTrue(is_client_disconnect_error(OSError("Write Error (Broken pipe)")))

    def test_os_error_errno(self):
        err_epipe = OSError()
        err_epipe.errno = errno.EPIPE
        self.assertTrue(is_client_disconnect_error(err_epipe))

        err_reset = OSError()
        err_reset.errno = errno.ECONNRESET
        self.assertTrue(is_client_disconnect_error(err_reset))

        err_shutdown = OSError()
        err_shutdown.errno = errno.ESHUTDOWN
        self.assertTrue(is_client_disconnect_error(err_shutdown))

    def test_upstream_errors_not_client_disconnect(self):
        self.assertFalse(is_client_disconnect_error(requests.exceptions.ChunkedEncodingError("Connection dropped")))
        self.assertFalse(is_client_disconnect_error(urllib3.exceptions.IncompleteRead(100, 50)))
        self.assertFalse(is_client_disconnect_error(requests.exceptions.ConnectionError("Connection aborted")))
        self.assertFalse(is_client_disconnect_error(ValueError("Invalid state")))


class TestStreamResumeOffsetLogic(SimpleTestCase):
    """Test stream_content_with_session resume offset calculations and manual skip."""

    def setUp(self):
        with patch("core.utils.RedisClient.get_client"):
            self.cm = MultiWorkerVODConnectionManager()
        self.cm.redis_client = MagicMock()
        self.cm.redis_client.exists.return_value = False
        self.movie_mock = MagicMock(spec=Movie)
        self.movie_mock.uuid = "uuid_1"
        self.movie_mock.name = "Test Movie"
        self.profile_mock = MagicMock(id=1)

    @patch("apps.proxy.vod_proxy.multi_worker_connection_manager.RedisBackedVODConnection")
    def test_stream_resume_offset_with_seek(self, mock_redis_conn_cls):
        """When client requests seek Range: bytes=1261347802- and drops after 1000 bytes,
        resume range must be bytes=1261348802- (initial_start_byte + bytes_sent)."""
        mock_redis_conn = MagicMock()
        mock_redis_conn_cls.return_value = mock_redis_conn
        mock_redis_conn.get_headers.return_value = {
            "content_type": "video/mp4",
            "content_length": "5000000000",
        }
        mock_redis_conn._acquire_lock.return_value = True
        mock_redis_conn._get_connection_state.return_value = MagicMock(
            is_valid=True,
            worker_id="test_worker",
            m3u_profile_id=1,
            final_url=None,
        )
        mock_redis_conn.has_active_streams.return_value = True
        mock_redis_conn.decrement_active_streams_and_check.return_value = (True, False)

        # Initial upstream stream returns 1 chunk of 1000 bytes then raises ChunkedEncodingError
        mock_initial_response = MagicMock()
        mock_initial_response.status_code = 206

        def initial_iter_content(chunk_size):
            yield b"X" * 1000
            raise requests.exceptions.ChunkedEncodingError("Upstream connection dropped")

        mock_initial_response.iter_content = initial_iter_content

        # Resume stream returns 1 chunk of 2000 bytes and completes
        mock_resumed_response = MagicMock()
        mock_resumed_response.status_code = 206

        def resumed_iter_content(chunk_size):
            yield b"Y" * 2000

        mock_resumed_response.iter_content = resumed_iter_content

        # Configure get_stream mock to return initial response then resumed response
        def get_stream_side_effect(range_hdr):
            if range_hdr == "bytes=1261347802-":
                return mock_initial_response
            elif range_hdr == "bytes=1261348802-":
                return mock_resumed_response
            return None

        mock_redis_conn.get_stream.side_effect = get_stream_side_effect

        response = self.cm.stream_content_with_session(
            session_id="client_1",
            content_obj=self.movie_mock,
            stream_url="http://example.com/movie.mp4",
            m3u_profile=self.profile_mock,
            client_ip="127.0.0.1",
            client_user_agent="TestAgent",
            request=MagicMock(),
            range_header="bytes=1261347802-",
        )

        self.assertTrue(hasattr(response, "streaming_content"))
        chunks = list(response.streaming_content)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], b"X" * 1000)
        self.assertEqual(chunks[1], b"Y" * 2000)

        # Verify get_stream was called with correct offset
        mock_redis_conn.get_stream.assert_any_call("bytes=1261347802-")
        mock_redis_conn.get_stream.assert_any_call("bytes=1261348802-")

    @patch("apps.proxy.vod_proxy.multi_worker_connection_manager.RedisBackedVODConnection")
    def test_client_disconnect_terminates_without_upstream_resume(self, mock_redis_conn_cls):
        """When client write error (BrokenPipe / OSError) occurs, generator terminates
        immediately and does NOT attempt upstream resume retries."""
        mock_redis_conn = MagicMock()
        mock_redis_conn_cls.return_value = mock_redis_conn
        mock_redis_conn.get_headers.return_value = {
            "content_type": "video/mp4",
            "content_length": "5000000000",
        }
        mock_redis_conn._acquire_lock.return_value = True
        mock_redis_conn._get_connection_state.return_value = MagicMock(
            is_valid=True,
            worker_id="test_worker",
            m3u_profile_id=1,
            final_url=None,
        )
        mock_redis_conn.has_active_streams.return_value = True
        mock_redis_conn.decrement_active_streams_and_check.return_value = (True, False)

        mock_initial_response = MagicMock()
        mock_initial_response.status_code = 206

        def initial_iter_content(chunk_size):
            yield b"X" * 1000
            # Client socket broke
            raise OSError("write error")

        mock_initial_response.iter_content = initial_iter_content
        mock_redis_conn.get_stream.return_value = mock_initial_response

        response = self.cm.stream_content_with_session(
            session_id="client_1",
            content_obj=self.movie_mock,
            stream_url="http://example.com/movie.mp4",
            m3u_profile=self.profile_mock,
            client_ip="127.0.0.1",
            client_user_agent="TestAgent",
            request=MagicMock(),
            range_header="bytes=100-",
        )

        chunks = list(response.streaming_content)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], b"X" * 1000)

        # get_stream was called only once initially, no resume calls
        self.assertEqual(mock_redis_conn.get_stream.call_count, 1)

    @patch("apps.proxy.vod_proxy.multi_worker_connection_manager.RedisBackedVODConnection")
    def test_manual_skip_when_provider_returns_200_on_resume(self, mock_redis_conn_cls):
        """When provider ignores Range header on resume (returns HTTP 200),
        the proxy skips current_offset bytes manually and yields the rest."""
        mock_redis_conn = MagicMock()
        mock_redis_conn_cls.return_value = mock_redis_conn
        mock_redis_conn.get_headers.return_value = {
            "content_type": "video/mp4",
            "content_length": "5000000000",
        }
        mock_redis_conn._acquire_lock.return_value = True
        mock_redis_conn._get_connection_state.return_value = MagicMock(
            is_valid=True,
            worker_id="test_worker",
            m3u_profile_id=1,
            final_url=None,
        )
        mock_redis_conn.has_active_streams.return_value = True
        mock_redis_conn.decrement_active_streams_and_check.return_value = (True, False)

        # Initial stream: sends 1000 bytes starting at byte 500
        mock_initial_response = MagicMock()
        mock_initial_response.status_code = 206

        def initial_iter_content(chunk_size):
            yield b"A" * 1000
            raise requests.exceptions.ChunkedEncodingError("Upstream connection dropped")

        mock_initial_response.iter_content = initial_iter_content

        # Resume stream: offset is 500 + 1000 = 1500.
        # Provider returns 200 (sending from byte 0): 1500 bytes of dummy prefix + 500 bytes of data
        mock_resumed_response = MagicMock()
        mock_resumed_response.status_code = 200

        def resumed_iter_content(chunk_size):
            # First chunk contains the first 1500 bytes to skip + 200 bytes real data
            yield b"DUMMY_PREFIX" * 125 + b"B" * 200  # 1500 + 200 = 1700
            # Second chunk contains remaining 300 bytes
            yield b"B" * 300

        mock_resumed_response.iter_content = resumed_iter_content

        def get_stream_side_effect(range_hdr):
            if range_hdr == "bytes=500-":
                return mock_initial_response
            elif range_hdr == "bytes=1500-":
                return mock_resumed_response
            return None

        mock_redis_conn.get_stream.side_effect = get_stream_side_effect

        response = self.cm.stream_content_with_session(
            session_id="client_1",
            content_obj=self.movie_mock,
            stream_url="http://example.com/movie.mp4",
            m3u_profile=self.profile_mock,
            client_ip="127.0.0.1",
            client_user_agent="TestAgent",
            request=MagicMock(),
            range_header="bytes=500-",
        )

        chunks = list(response.streaming_content)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0], b"A" * 1000)
        self.assertEqual(chunks[1], b"B" * 200)
        self.assertEqual(chunks[2], b"B" * 300)
