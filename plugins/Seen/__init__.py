"""Bundled Seen commands with a newline-safe reader for legacy CSV state."""

from supybot.plugins.Seen import config

from .plugin import Seen

Class = Seen
configure = config.configure
