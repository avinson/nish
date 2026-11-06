"""Text boundaries shared by all Cobe learning and response paths."""

import re
from functools import lru_cache

MARKERS = re.compile(r"MAGIC_NICK|PLZREPLACEMENICKUNKNOWNWORDSHAHAH", re.IGNORECASE)
NICK_TOKEN = re.compile(r"[\w\[\]\\`^{}|~\-]+", re.UNICODE)
CASEMAP = str.maketrans("[]\\^", "{}|~")


def irc_fold(text):
    """Return an RFC1459 comparison key."""
    return text.lower().translate(CASEMAP)


@lru_cache(maxsize=128)
def _nicknames(users):
    return frozenset(irc_fold(str(user)) for user in users)


def strip_nicks(text, users):
    """Remove whole nickname tokens without changing adjacent words."""
    names = _nicknames(tuple(users))
    return NICK_TOKEN.sub(lambda m: "" if irc_fold(m[0]) in names else m[0], text)


def clean_input(text, users=(), strip_urls=True, strip_names=True):
    """Normalize human input and reject reserved-marker contamination."""
    if MARKERS.search(text):
        return ""
    if strip_urls:
        text = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    if strip_names:
        text = strip_nicks(text, users)
    text = " ".join(text.split()).strip(" ,:;")
    return text[:1].upper() + text[1:] if len(text) > 1 else ""


def clean_output(text, users=()):
    """Remove old markers and nicknames, then bound a single IRC reply."""
    text = MARKERS.sub("", text)
    text = strip_nicks(text, users)
    text = " ".join(text.replace("\x00", "").split()).strip(" ,:;")
    text = text[:300].encode("utf-8")[:400].decode("utf-8", "ignore")
    if MARKERS.search(text):
        return ""
    return text.strip()
