from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.epg.models import EPGSource
from core.models import CoreSettings, DVR_SETTINGS_KEY, EPG_SETTINGS_KEY


class DispatcharrUserAgentTests(TestCase):
    @patch('version.__version__', '1.2.3')
    def test_dispatcharr_user_agent(self):
        from core.utils import dispatcharr_user_agent
        self.assertEqual(dispatcharr_user_agent(), 'Dispatcharr/1.2.3')

    def test_dispatcharr_dvr_user_agent(self):
        from core.utils import dispatcharr_dvr_user_agent
        self.assertEqual(dispatcharr_dvr_user_agent(42), 'Dispatcharr-DVR/recording-42')

    @patch('version.__version__', '1.2.3')
    def test_dispatcharr_http_headers_with_token(self):
        from core.utils import dispatcharr_http_headers
        headers = dispatcharr_http_headers(token='tok123')
        self.assertEqual(headers, {
            'User-Agent': 'Dispatcharr/1.2.3',
            'Content-Type': 'application/json',
            'token': 'tok123',
        })

    @patch('version.__version__', '1.2.3')
    def test_dispatcharr_http_headers_without_content_type(self):
        from core.utils import dispatcharr_http_headers
        self.assertEqual(
            dispatcharr_http_headers(content_type=None),
            {'User-Agent': 'Dispatcharr/1.2.3'},
        )


class ProgrammeIndexRebuildTests(TestCase):
    def test_startup_rebuild_does_not_lock_out_queued_build_task(self):
        EPGSource.objects.update(
            programme_index={"channels": {}, "interleaved_channels": []}
        )
        source = EPGSource.objects.create(
            name="Missing Index",
            source_type="xmltv",
            is_active=True,
            programme_index=None,
        )

        class FakeRedis:
            def __init__(self):
                self.keys = set()

            def set(self, key, value, nx=False, ex=None):
                if nx and key in self.keys:
                    return False
                self.keys.add(key)
                return True

            def delete(self, key):
                self.keys.discard(key)

        fake_redis = FakeRedis()

        from apps.epg.tasks import build_programme_index_task
        from core.tasks import _rebuild_programme_indices

        def run_task_immediately(source_id):
            build_programme_index_task(source_id)

        with patch(
            "core.tasks.RedisClient.get_client", return_value=fake_redis
        ), patch(
            "core.utils.RedisClient.get_client", return_value=fake_redis
        ), patch(
            "apps.epg.tasks.build_programme_index"
        ) as mock_build, patch(
            "apps.epg.tasks.build_programme_index_task.delay",
            side_effect=run_task_immediately,
        ):
            _rebuild_programme_indices()

        mock_build.assert_called_once_with(source.id)


class GetDvrSeriesRulesTest(TestCase):
    """Verify get_dvr_series_rules handles corrupted stored data."""

    def _set_series_rules_raw(self, raw_value):
        """Write a raw series_rules value into the DB, bypassing set_dvr_series_rules."""
        obj, _ = CoreSettings.objects.get_or_create(
            key=DVR_SETTINGS_KEY,
            defaults={"name": "DVR Settings", "value": {}},
        )
        current = obj.value if isinstance(obj.value, dict) else {}
        current["series_rules"] = raw_value
        obj.value = current
        obj.save()

    def test_valid_rules_returned_as_is(self):
        rules = [{"tvg_id": "abc", "mode": "all", "title": "Show"}]
        self._set_series_rules_raw(rules)
        result = CoreSettings.get_dvr_series_rules()
        self.assertEqual(result, rules)

    def test_non_dict_elements_filtered(self):
        """Strings in the list cause 'str' has no attribute 'get'."""
        self._set_series_rules_raw(["bad_string", {"tvg_id": "abc", "mode": "all", "title": ""}])
        result = CoreSettings.get_dvr_series_rules()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tvg_id"], "abc")

    def test_non_list_value_returns_empty(self):
        """If series_rules is a JSON string instead of a list, return empty."""
        self._set_series_rules_raw("[]")
        result = CoreSettings.get_dvr_series_rules()
        self.assertEqual(result, [])

    def test_none_value_returns_empty(self):
        self._set_series_rules_raw(None)
        result = CoreSettings.get_dvr_series_rules()
        self.assertEqual(result, [])

    def test_mixed_corrupt_elements(self):
        self._set_series_rules_raw([42, None, True, {"tvg_id": "x", "mode": "new", "title": "T"}])
        result = CoreSettings.get_dvr_series_rules()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tvg_id"], "x")


class SetDvrSeriesRulesTest(TestCase):
    """Verify set_dvr_series_rules sanitizes input before persisting."""

    def test_valid_rules_persisted(self):
        rules = [{"tvg_id": "abc", "mode": "all", "title": "Show"}]
        result = CoreSettings.set_dvr_series_rules(rules)
        self.assertEqual(result, rules)
        self.assertEqual(CoreSettings.get_dvr_series_rules(), rules)

    def test_non_dict_elements_stripped_on_write(self):
        dirty = ["bad", 42, {"tvg_id": "abc", "mode": "all", "title": ""}]
        result = CoreSettings.set_dvr_series_rules(dirty)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tvg_id"], "abc")
        self.assertEqual(CoreSettings.get_dvr_series_rules(), result)

    def test_non_list_input_stores_empty(self):
        result = CoreSettings.set_dvr_series_rules("not a list")
        self.assertEqual(result, [])
        self.assertEqual(CoreSettings.get_dvr_series_rules(), [])


class CoreSettingsSerializerDvrTest(TestCase):
    """Verify the generic settings API sanitizes series_rules on save."""

    def test_serializer_strips_corrupt_series_rules(self):
        """Settings page round-trip must not persist corrupt series_rules."""
        from core.serializers import CoreSettingsSerializer

        obj, _ = CoreSettings.objects.get_or_create(
            key=DVR_SETTINGS_KEY,
            defaults={"name": "DVR Settings", "value": {"series_rules": []}},
        )
        dirty_value = {
            **obj.value,
            "series_rules": ["bad", {"tvg_id": "ok", "mode": "all", "title": ""}],
        }
        serializer = CoreSettingsSerializer(obj, data={"value": dirty_value}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        obj.refresh_from_db()
        rules = obj.value.get("series_rules", [])
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["tvg_id"], "ok")

    def test_serializer_handles_non_list_series_rules(self):
        from core.serializers import CoreSettingsSerializer

        obj, _ = CoreSettings.objects.get_or_create(
            key=DVR_SETTINGS_KEY,
            defaults={"name": "DVR Settings", "value": {"series_rules": []}},
        )
        dirty_value = {**obj.value, "series_rules": "not a list"}
        serializer = CoreSettingsSerializer(obj, data={"value": dirty_value}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        obj.refresh_from_db()
        self.assertEqual(obj.value.get("series_rules"), [])


class EpgIgnoreListsTest(TestCase):
    """Verify EPG ignore list getters handle corrupted stored data."""

    def _set_epg_field_raw(self, field, raw_value):
        obj, _ = CoreSettings.objects.get_or_create(
            key=EPG_SETTINGS_KEY,
            defaults={"name": "EPG Settings", "value": {}},
        )
        current = obj.value if isinstance(obj.value, dict) else {}
        current[field] = raw_value
        obj.value = current
        obj.save()

    def test_valid_string_lists_returned(self):
        for field, getter in [
            ("epg_match_ignore_prefixes", CoreSettings.get_epg_match_ignore_prefixes),
            ("epg_match_ignore_suffixes", CoreSettings.get_epg_match_ignore_suffixes),
            ("epg_match_ignore_custom", CoreSettings.get_epg_match_ignore_custom),
        ]:
            self._set_epg_field_raw(field, ["HD", "SD"])
            self.assertEqual(getter(), ["HD", "SD"])

    def test_non_string_elements_filtered(self):
        for field, getter in [
            ("epg_match_ignore_prefixes", CoreSettings.get_epg_match_ignore_prefixes),
            ("epg_match_ignore_suffixes", CoreSettings.get_epg_match_ignore_suffixes),
            ("epg_match_ignore_custom", CoreSettings.get_epg_match_ignore_custom),
        ]:
            self._set_epg_field_raw(field, [42, None, "HD", True, "SD"])
            result = getter()
            self.assertEqual(result, ["HD", "SD"])

    def test_non_list_value_returns_empty(self):
        for field, getter in [
            ("epg_match_ignore_prefixes", CoreSettings.get_epg_match_ignore_prefixes),
            ("epg_match_ignore_suffixes", CoreSettings.get_epg_match_ignore_suffixes),
            ("epg_match_ignore_custom", CoreSettings.get_epg_match_ignore_custom),
        ]:
            self._set_epg_field_raw(field, "not a list")
            self.assertEqual(getter(), [])


class DropDBCommandTlsTest(TestCase):
    """Verify dropdb management command passes TLS parameters to psycopg."""
    databases = []

    _DB_WITH_TLS = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'testdb',
            'USER': 'testuser',
            'PASSWORD': 'testpass',
            'HOST': 'localhost',
            'PORT': 5432,
            'OPTIONS': {
                'sslmode': 'verify-full',
                'sslrootcert': '/certs/ca.crt',
                'sslcert': '/certs/client.crt',
                'sslkey': '/certs/client.key',
            },
        }
    }

    _DB_NO_TLS = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'testdb',
            'USER': 'testuser',
            'PASSWORD': 'testpass',
            'HOST': 'localhost',
            'PORT': 5432,
        }
    }

    @patch('core.management.commands.dropdb.psycopg.connect')
    @patch('core.management.commands.dropdb.connection')
    @patch('builtins.input', return_value='yes')
    def test_dropdb_passes_ssl_kwargs_when_tls_enabled(self, _inp, _conn, mock_connect):
        mock_pg = MagicMock()
        mock_connect.return_value = mock_pg
        mock_pg.cursor.return_value = MagicMock()

        with self.settings(DATABASES=self._DB_WITH_TLS):
            from django.core.management import call_command
            call_command('dropdb')

        mock_connect.assert_called_once_with(
            dbname='postgres', user='testuser', password='testpass',
            host='localhost', port=5432,
            autocommit=True,
            sslmode='verify-full',
            sslrootcert='/certs/ca.crt',
            sslcert='/certs/client.crt',
            sslkey='/certs/client.key',
        )

    @patch('core.management.commands.dropdb.psycopg.connect')
    @patch('core.management.commands.dropdb.connection')
    @patch('builtins.input', return_value='yes')
    def test_dropdb_no_ssl_kwargs_when_tls_disabled(self, _inp, _conn, mock_connect):
        mock_pg = MagicMock()
        mock_connect.return_value = mock_pg
        mock_pg.cursor.return_value = MagicMock()

        with self.settings(DATABASES=self._DB_NO_TLS):
            from django.core.management import call_command
            call_command('dropdb')

        mock_connect.assert_called_once_with(
            dbname='postgres', user='testuser', password='testpass',
            host='localhost', port=5432,
            autocommit=True,
        )


class EpgParserSecurityTests(TestCase):
    def test_parse_html_entities_resolved(self):
        from apps.epg.tasks import _parse_programme_element
        # A simple programme element containing &eacute;
        xml_bytes = b'<programme start="20260620120000" stop="20260620130000" channel="test"><title>Caf&amp;eacute; Caf&amp;eacute;</title></programme>'
        # Wait, since our regex replaces "&eacute;" we should write it as "&eacute;" or escaped &amp;eacute; depending on test.
        # Let's test with raw "&eacute;" directly:
        xml_bytes_raw = b'<programme start="20260620120000" stop="20260620130000" channel="test"><title>Caf&eacute; Caf&eacute;</title></programme>'
        element = _parse_programme_element(xml_bytes_raw)
        title_element = element.find('title')
        self.assertEqual(title_element.text, 'Caf\u00e9 Caf\u00e9')

    def test_billion_laughs_protection(self):
        from apps.epg.tasks import _parse_programme_element
        from lxml import etree
        # XML containing a Billion Laughs recursive entity definition within the bytes.
        # Note: If resolve_entities is False, it will either raise XMLSyntaxError because of 
        # the entity references, or parse it as plain unexpanded text.
        xml_bytes = (
            b'<!DOCTYPE programme [\n'
            b'<!ENTITY lol "lol">\n'
            b'<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
            b']>\n'
            b'<programme start="20260620120000" stop="20260620130000" channel="test">\n'
            b'  <title>&lol1;</title>\n'
            b'</programme>'
        )
        try:
            element = _parse_programme_element(xml_bytes)
            title_element = element.find('title')
            self.assertNotEqual(title_element.text, 'lol' * 10)
        except etree.XMLSyntaxError:
            # Raising syntax error due to unresolved entity reference is a safe outcome
            pass


class StreamProfileSecurityTests(TestCase):
    def setUp(self):
        from core.models import StreamProfile
        self.profile = StreamProfile.objects.create(
            name="Test Custom Profile",
            command="ffmpeg",
            parameters="-i {streamUrl} -c copy -f mpegts pipe:1"
        )

    def test_build_command_success(self):
        cmd = self.profile.build_command("http://provider.com/live.ts", "Mozilla/5.0")
        self.assertEqual(cmd, ["ffmpeg", "-i", "http://provider.com/live.ts", "-c", "copy", "-f", "mpegts", "pipe:1"])

    def test_build_command_rejects_hyphen_url(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.profile.build_command("-option_injection", "Mozilla/5.0")

    def test_build_command_rejects_unapproved_protocol(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.profile.build_command("file:///etc/passwd", "Mozilla/5.0")

    def test_build_command_rejects_control_characters(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.profile.build_command("http://provider.com/live.ts\n;rm -rf /", "Mozilla/5.0")
