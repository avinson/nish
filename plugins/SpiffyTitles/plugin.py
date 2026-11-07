"""Nishbot's bounded, asynchronous integration of pinned SpiffyTitles."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import html
import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from supybot import callbacks, ircdb, ircmsgs, ircutils
from supybot.commands import wrap

from .upstream import SpiffyTitles as UpstreamSpiffyTitles

MAX_BYTES = 1024 * 1024
MAX_CACHE = 512
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def clean_title(text, limit=380):
    """Strip controls and truncate at a UTF-8 boundary, leaving IRC framing room."""
    text = " ".join(ircutils.stripFormatting(html.unescape(str(text))).split())
    text = "".join(c for c in text if ord(c) >= 32 and ord(c) != 127)
    if len(text.encode("utf-8")) > limit:
        text = text.encode("utf-8")[:limit - 3].decode("utf-8", "ignore") + "…"
    return text


def video_id(url):
    try:
        info = urlparse(url)
    except ValueError:
        return None
    if info.hostname not in YOUTUBE_HOSTS:
        return None
    parts = info.path.strip("/").split("/")
    if info.hostname == "youtu.be":
        candidate = parts[0]
    elif parts[0] in {"shorts", "live", "embed"} and len(parts) == 2:
        candidate = parts[1]
    else:
        candidate = parse_qs(info.query).get("v", [""])[0]
    return candidate if re.fullmatch(r"[\w-]{11}", candidate, re.ASCII) else None


def duration(value):
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match or not any(match.groups()):
        return ""
    hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def public_url(url):
    """Reject local destinations, including every redirect, before requesting."""
    info = urlparse(url)
    if info.scheme not in {"http", "https"} or not info.hostname or info.username:
        return False
    addresses = socket.getaddrinfo(info.hostname, info.port or 443, type=socket.SOCK_STREAM)
    return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)


class SpiffyTitles(UpstreamSpiffyTitles):
    """One compact preview per message; !t URL explicitly repeats a preview."""

    threaded = False
    callBefore = ["Infobot", "Cobe", "Web"]

    def __init__(self, irc):
        super().__init__(irc)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="titles")
        self._lock = threading.Lock()
        self._active = True
        self._pending = 0
        self._last_user = OrderedDict()
        self._cache = OrderedDict()

    def add_handlers(self):
        # Other upstream handlers stay inactive until reviewed and tested here.
        self.add_youtube_handlers()
        self.add_imdb_handlers()

    def die(self):
        with self._lock:
            self._active = False
        self._executor.shutdown(wait=True, cancel_futures=True)
        super().die()

    def _fetch(self, url, channel, network, params=None):
        """Bound response size and redirects; never log URLs or API credentials."""
        for _ in range(4):
            if not public_url(url):
                return None
            with requests.get(
                url, params=params, headers=self.get_headers(channel, network),
                timeout=self.registryValue("timeout"), stream=True, allow_redirects=False,
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("Location", ""))
                    params = None
                    continue
                response.raise_for_status()
                data = bytearray()
                deadline = time.monotonic() + self.registryValue("timeout")
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES or time.monotonic() > deadline:
                        return None
                return bytes(data), response.headers.get("Content-Type", "")
        return None

    def _json(self, url, channel, network, params):
        response = self._fetch(url, channel, network, params)
        return json.loads(response[0]) if response else {}

    def get_source_by_url(self, url, channel, network, retries=1):
        response = self._fetch(url, channel, network)
        if not response or response[1].split(";")[0].lower() not in {
            "text/html", "application/xhtml+xml",
        }:
            return None, False
        soup = BeautifulSoup(response[0], "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if not title:
            meta = soup.find("meta", property="og:title")
            title = meta.get("content", "") if meta else ""
        return title or None, False

    def handler_youtube(self, url, info, channel, network):
        vid = video_id(url)
        if not vid or not self.registryValue("youtube.enabled", channel, network):
            return self.handler_default(url, channel, network)
        canonical = "https://www.youtube.com/watch?v=" + vid
        key = self.registryValue("youtube.developerKey")
        values = {}
        if key:
            try:
                data = self._json("https://www.googleapis.com/youtube/v3/videos", channel, network, {
                    "part": "snippet,statistics,contentDetails", "id": vid, "key": key,
                })
                items = data.get("items", [])
                if items:
                    item = items[0]
                    snippet = item.get("snippet", {})
                    views = item.get("statistics", {}).get("viewCount")
                    values = {
                        "title": snippet.get("title", ""),
                        "channel_title": snippet.get("channelTitle", ""),
                        "published": snippet.get("publishedAt", "").split("T")[0],
                        "duration": duration(item.get("contentDetails", {}).get("duration")),
                        "view_count": f"{int(views):,}" if views is not None else "",
                    }
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                self.log.info("YouTube metadata unavailable; trying oEmbed")
        if not values.get("title"):
            data = self._json("https://www.youtube.com/oembed", channel, network, {
                "url": canonical, "format": "json",
            })
            values = {"title": data.get("title", ""), "channel_title": data.get("author_name", "")}
        if values.get("title"):
            values = {k: clean_title(v, 240) for k, v in values.items()}
            return self.get_template("youtube.template", channel, network).render(values)
        return None

    def handler_imdb(self, url, info, channel, network):
        key = self.registryValue("imdb.omdbAPI")
        match = re.search(r"/title/(tt\d+)", info.path)
        if not key or not match or not self.registryValue("imdb.enabled", channel, network):
            return self.handler_default(url, channel, network)
        data = self._json("https://www.omdbapi.com/", channel, network, {
            "apikey": key, "i": match[1], "plot": "short",
        })
        if data.get("Response") != "True":
            return None
        fields = [data.get(k) for k in ("Title", "Year", "Runtime", "Genre", "imdbRating")]
        return "IMDb | " + " | ".join(clean_title(v, 180) for v in fields if v and v != "N/A")

    def get_title_by_url(self, url, channel, network, origin_nick=None):
        """Keep on-demand lookups cached without bypassing channel settings."""
        key = (network, ircutils.toLower(channel or ""), self._canonical(url))
        now = time.monotonic()
        lifetime = max(0, self.registryValue("cacheLifetime"))
        cached = self._cache.get(key)
        if cached and now - cached[0] < lifetime:
            return cached[1]
        info = urlparse(url)
        try:
            host = info.hostname or ""
            if host in YOUTUBE_HOSTS:
                title = self.handler_youtube(url, info, channel, network)
            elif host in {"imdb.com", "www.imdb.com", "m.imdb.com"}:
                title = self.handler_imdb(url, info, channel, network)
            else:
                title = self.handler_default(url, channel, network)
            title = clean_title(title) if title else None
        except (requests.RequestException, ValueError, TypeError, AttributeError, OSError):
            self.log.info("Link preview unavailable")
            title = None
        self._cache[key] = (now, title)
        self._cache.move_to_end(key)
        while len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)
        return title

    @staticmethod
    def _canonical(url):
        vid = video_id(url)
        return "youtube:" + vid if vid else url

    def _allowed(self, irc, msg):
        return (
            irc.isChannel(msg.channel) and msg.channel in irc.state.channels
            and self.is_channel_allowed(msg.channel)
            and not ircutils.nickEqual(msg.nick, irc.nick)
            and not ircdb.checkIgnored(msg.prefix, msg.channel)
        )

    def doPrivmsg(self, irc, msg):
        if (
            not self._allowed(irc, msg) or msg.repliedTo or ircmsgs.isCtcp(msg)
            or callbacks.addressed(irc, msg)
            or self.message_matches_ignore_pattern(msg.args[1], msg.channel, irc.network)
        ):
            return
        urls = self.get_urls_from_message(msg.args[1], msg.channel, irc.network)
        if urls:
            self._submit(irc, msg, urls[0].rstrip(".,;!?"), explicit=False)

    def _submit(self, irc, msg, url, explicit=False):
        channel, network = msg.channel, irc.network
        try:
            info = urlparse(url)
        except ValueError:
            return
        if info.scheme not in {"http", "https"} or not info.hostname:
            return
        if self.is_ignored_domain(info.hostname, channel, network):
            return
        if self.registryValue("whitelistDomainPattern", channel, network) and not (
            self.is_whitelisted_domain(info.hostname, channel, network)
        ):
            return
        if self.registryValue("requireCapability", channel, network) and not (
            self.user_has_capability(msg, network)
        ):
            return
        now = time.monotonic()
        user = (network, ircutils.toLower(channel), ircutils.toLower(msg.nick))
        with self._lock:
            if not self._active or self._pending >= 8:
                return
            cooldown = self.registryValue("cooldownSeconds", channel, network)
            if now - self._last_user.get(user, float("-inf")) < cooldown:
                msg.tag("repliedTo")
                return
            self._last_user[user] = now
            self._last_user.move_to_end(user)
            if len(self._last_user) > MAX_CACHE:
                self._last_user.popitem(last=False)
            msg.tag("repliedTo")  # Claim synchronously before Cobe's passive callback.
            self._pending += 1
            future = self._executor.submit(self._preview, irc, msg, url, explicit)
        future.add_done_callback(self._finished)

    def _preview(self, irc, msg, url, explicit):
        channel, network = msg.channel, irc.network
        key = (network, ircutils.toLower(channel), self._canonical(url))
        cached = self._cache.get(key)
        if not explicit and cached and time.monotonic() - cached[0] < max(
            0, self.registryValue("cacheLifetime")
        ):
            return
        title = self.get_title_by_url(url, channel, network)
        with self._lock:
            if self._active and self._allowed(irc, msg) and title:
                if not self.title_matches_ignore_pattern(title, channel, network):
                    irc.queueMsg(ircmsgs.privmsg(channel, title))

    def _finished(self, future):
        with self._lock:
            self._pending -= 1
        if not future.cancelled() and future.exception():
            # An exception string may contain an API key; never print it.
            self.log.warning("Link preview worker failed")

    def t(self, irc, msg, args, url):
        """<url>

        Repeat a cached preview or fetch a title in an enabled channel.
        """
        if self._allowed(irc, msg):
            self._submit(irc, msg, url, explicit=True)

    t = wrap(t, ["httpUrl"])


Class = SpiffyTitles
