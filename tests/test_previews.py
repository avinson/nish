"""Preview API failures, IRC routing, and persistence without live HTTP requests."""

from unittest import mock

import pytest
import requests
from supybot import conf, ircmsgs
from supybot import test as supytest

from SpiffyTitles.plugin import clean_title, duration, public_url, video_id


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=IR9NnGcB094&list=other",
    "https://youtu.be/IR9NnGcB094?t=42",
    "https://m.youtube.com/shorts/IR9NnGcB094",
    "https://www.youtube.com/live/IR9NnGcB094",
])
def test_video_urls(url):
    assert video_id(url) == "IR9NnGcB094"


def test_output_and_duration():
    text = clean_title("\x01ACTION\r\n" + "🙂" * 300 + "\x00")
    assert len(text.encode()) <= 380
    assert "\x01" not in text and "\n" not in text
    assert "\ufffd" not in text
    assert duration("PT2M44S") == "2:44"
    assert duration("PT1H2M3S") == "1:02:03"
    assert duration(None) == ""
    assert video_id("https://youtube.com.evil.test/watch?v=IR9NnGcB094") is None


@pytest.mark.parametrize("address", ["127.0.0.1", "192.168.1.2", "169.254.169.254", "::1"])
def test_private_destinations(address):
    with mock.patch("SpiffyTitles.plugin.socket.getaddrinfo", return_value=[
        (0, 0, 0, "", (address, 443)),
    ]):
        assert not public_url("https://example.org")


class PreviewPluginTest(supytest.ChannelPluginTestCase):
    plugins = ("SpiffyTitles", "Cobe", "Infobot", "QuoteGrabs", "Later")
    timeout = 5
    config = {
        "plugins.SpiffyTitles.channelWhitelist": ["#test"],
        "plugins.SpiffyTitles.cooldownSeconds": 0,
        "plugins.Cobe.probability": 0,
        "plugins.Cobe.responseDelay": False,
    }

    def runTest(self):
        """Legacy Limnoria harness entry point."""

    def setUp(self):
        super().setUp()
        self.prefix = "tester!user@host.domain.tld"
        self.plugin = self.irc.getCallback("SpiffyTitles")

    def wait_preview(self):
        self.plugin._executor.submit(lambda: None).result(timeout=5)

    def test_rich_youtube_and_missing_fields(self):
        conf.supybot.plugins.SpiffyTitles.youtube.developerKey.setValue("synthetic-key")
        with mock.patch.object(self.plugin, "_json", return_value={"items": [{
            "snippet": {"title": "Black & White Sailor Song", "channelTitle": "ProfessorMudkip",
                        "publishedAt": "2009-10-19T00:00:00Z"},
            "statistics": {"viewCount": "106322"},
            "contentDetails": {"duration": "PT2M44S"},
        }]}) as fetch:
            self.assertResponse(
                "t https://youtu.be/IR9NnGcB094",
                "▶ Black & White Sailor Song | 2:44 | 106,322 views | ProfessorMudkip | 2009-10-19",
            )
            self.assertEqual(fetch.call_count, 1)
        self.plugin._cache.clear()
        with mock.patch.object(self.plugin, "_json", return_value={"items": [{
            "snippet": {"title": "Minimal video"},
        }]}):
            self.assertResponse("t https://youtu.be/IR9NnGcB094", "▶ Minimal video")

    def test_no_key_and_api_failure_fallback(self):
        for key in ("", "synthetic-key"):
            conf.supybot.plugins.SpiffyTitles.youtube.developerKey.setValue(key)
            self.plugin._cache.clear()
            results = ([requests.HTTPError("secret must not be logged")] if key else []) + [
                {"title": "Some video", "author_name": "Some uploader"},
            ]
            with mock.patch.object(self.plugin, "_json", side_effect=results):
                self.assertResponse(
                    "t https://youtu.be/IR9NnGcB094", "▶ Some video | Some uploader",
                )

    def test_preview_claims_message_and_suppresses_duplicates(self):
        cobe = self.irc.getCallback("Cobe")
        conf.supybot.plugins.Cobe.probability.setValue(10000)
        with (
            mock.patch.object(self.plugin, "_json", return_value={
                "title": "Some video", "author_name": "Uploader",
            }) as fetch,
            mock.patch.object(cobe, "_submit") as cobe_submit,
        ):
            conf.supybot.plugins.SpiffyTitles.youtube.developerKey.setValue("")
            self.assertResponse(
                "https://youtu.be/IR9NnGcB094 https://example.org/second",
                "▶ Some video | Uploader", usePrefixChar=False,
            )
            self.wait_preview()
            cobe_submit.assert_not_called()
            self.assertNoResponse(
                "https://youtube.com/watch?v=IR9NnGcB094&t=12",
                usePrefixChar=False, timeout=0.2,
            )
            self.wait_preview()
            self.assertEqual(fetch.call_count, 1)
            self.assertResponse("t https://youtu.be/IR9NnGcB094", "▶ Some video | Uploader")
            self.assertEqual(fetch.call_count, 1)

    def test_timeouts_and_bad_payloads_are_silent(self):
        for failure in (requests.Timeout("private-url"), ValueError("malformed JSON")):
            self.plugin._cache.clear()
            with mock.patch.object(self.plugin, "_fetch", side_effect=failure):
                self.assertNoResponse(
                    "https://example.org/page", usePrefixChar=False, timeout=0.2,
                )
                self.wait_preview()

    def test_channel_guard_cooldown_and_command_precedence(self):
        conf.supybot.plugins.SpiffyTitles.cooldownSeconds.setValue(5)
        with mock.patch.object(self.plugin, "_fetch", return_value=(
            b"<html><title>Article title</title></html>", "text/html",
        )) as fetch:
            self.assertResponse("https://example.org/a", "^ Article title", usePrefixChar=False)
            self.assertNoResponse("https://example.org/b", usePrefixChar=False, timeout=0.2)
            self.wait_preview()
            self.assertEqual(fetch.call_count, 1)
            self.assertNotError("later tell absent https://example.org/later")
            self.assertEqual(fetch.call_count, 1)
            conf.supybot.plugins.SpiffyTitles.channelWhitelist.setValue(["#elsewhere"])
            self.assertNoResponse("https://example.org/c", usePrefixChar=False, timeout=0.2)
            self.assertEqual(fetch.call_count, 1)

    def test_fetch_limits_and_redirect_validation(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = True
        response.headers = {"Location": "http://127.0.0.1/secret"}
        with (
            mock.patch("SpiffyTitles.plugin.public_url", side_effect=[True, False]),
            mock.patch("SpiffyTitles.plugin.requests.get", return_value=response) as get,
        ):
            self.assertIsNone(self.plugin._fetch("https://example.org/", self.channel, "test"))
            self.assertEqual(get.call_count, 1)
        response.is_redirect = False
        response.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
        with (
            mock.patch("SpiffyTitles.plugin.public_url", return_value=True),
            mock.patch("SpiffyTitles.plugin.requests.get", return_value=response),
        ):
            self.assertIsNone(self.plugin._fetch("https://example.org/", self.channel, "test"))

    def test_quotes_and_later_survive_reinstantiation(self):
        self.irc.feedMsg(ircmsgs.privmsg(
            self.channel, "a memorable café quote 🙂", prefix="alice!a@host",
        ))
        self.assertNotError("grab alice")
        self.assertResponse("quote alice", "<alice> a memorable café quote 🙂")
        quotes = self.irc.getCallback("QuoteGrabs")
        quotes.db.close()
        quotes.db = type(quotes.db)(quotes.db.filename)
        self.assertResponse("quote alice", "<alice> a memorable café quote 🙂")
        self.assertNotError("later tell absent remember the café 🙂")
        later = self.irc.getCallback("Later")
        later.die()
        replacement = type(later)(self.irc)
        self.irc.removeCallback("Later")
        self.irc.addCallback(replacement)
        self.assertRegexp("later notes absent", "remember the café 🙂")
        self.irc.feedMsg(ircmsgs.privmsg(self.channel, "hello", prefix="absent!a@host"))
        reply = self.getMsg(" ")
        self.assertIn("absent: Sent just now:", str(reply))
        self.assertIn("remember the café 🙂", str(reply))
        self.assertError("later notes absent")
