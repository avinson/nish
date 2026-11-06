###

"""Cobe integration with serialized SQLite access and shared text boundaries."""

import os
import random
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from cobe.brain import Brain
from supybot import callbacks, conf, ircmsgs, ircutils, schedule
from supybot.commands import additional, wrap

from .core import NICK_TOKEN, clean_input, clean_output, irc_fold


class Cobe(callbacks.Plugin):
    """Learn channel conversation and generate Markov replies."""

    callAfter = ["Infobot"]
    threaded = False

    def __init__(self, irc):
        super().__init__(irc)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cobe")
        self._brains = {}
        self._last = {}
        self._events = set()
        self._lock = threading.Lock()
        self._pending = 0
        self._active = True

    def _path(self, channel):
        if not channel.startswith(("#", "&")) or "/" in channel or ".." in channel:
            raise ValueError("Invalid channel")
        path = conf.supybot.directories.data.dirize(channel.lower() + "/cobe.brain")
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        return path

    def _brain(self, channel):
        path = self._path(channel)
        if path not in self._brains:
            brain = Brain(path)
            brain.graph.commit()
            brain.graph.cursor().execute("PRAGMA synchronous=FULL")
            brain.graph.cursor().execute("PRAGMA busy_timeout=5000")
            self._brains[path] = brain
        return self._brains[path]

    def _users(self, irc, channel):
        if not irc.isChannel(channel) or channel not in irc.state.channels:
            return None
        return tuple(irc.state.channels[channel].users)

    def _submit(self, irc, msg, channel, text, learn=False, reply=False, addressed=False):
        users = self._users(irc, channel)
        if users is None or not self._active:
            return
        text = clean_input(
            ircutils.stripFormatting(text),
            users,
            self.registryValue("stripUrls"),
            self.registryValue("stripNicks"),
        )
        if not text:
            return
        with self._lock:
            if self._pending >= 32:
                self.log.warning("Cobe queue is full; dropping an event")
                return
            self._pending += 1
        if reply:
            msg.tag("repliedTo")
        future = self._executor.submit(self._work, irc, msg, channel, text, learn, reply, addressed)
        future.add_done_callback(self._finished)
        return True

    def _finished(self, future):
        with self._lock:
            self._pending -= 1
        if not future.cancelled():
            try:
                future.result()
            except Exception:
                self.log.exception("Cobe event failed")

    def _work(self, irc, msg, channel, text, learn, reply, addressed):
        if not self._active:
            return
        brain = self._brain(channel)
        if learn:
            brain.learn(text)
        if not reply:
            return
        key = (irc.network, irc_fold(channel))
        now = time.monotonic()
        bypass = addressed and self.registryValue("ignoreWaitTimeIfAddressed", channel)
        if not bypass and now - self._last.get(key, float("-inf")) < self.registryValue(
            "waitTimeBetweenSpeaking", channel
        ):
            return
        response = brain.reply(text, loop_ms=500, max_len=300)
        users = self._users(irc, channel)
        if users is None:
            return
        response = clean_output(response, users)
        if not response:
            return
        self._last[key] = time.monotonic()

        def send():
            if self._active and self._users(irc, channel) is not None:
                current = clean_output(response, self._users(irc, channel))
                if current:
                    irc.queueMsg(ircmsgs.privmsg(channel, current))
            with self._lock:
                self._events.discard(event)

        event = "nish-cobe-" + uuid.uuid4().hex
        if self.registryValue("responseDelay", channel):
            with self._lock:
                if not self._active:
                    return
                self._events.add(event)
                schedule.addEvent(send, time.time() + random.randint(2, 5), name=event)
        else:
            send()

    def doPrivmsg(self, irc, msg):
        """Learn ordinary channel messages and optionally reply."""
        channel, text = msg.args
        if (
            self._users(irc, channel) is None
            or msg.repliedTo
            or ircutils.nickEqual(msg.nick, irc.nick)
        ):
            return
        if ircmsgs.isCtcp(msg) or callbacks.addressed(irc, msg):
            return
        if re.match(self.registryValue("ignoreRegex"), text):
            return
        mentioned = irc_fold(irc.nick) in {irc_fold(m[0]) for m in NICK_TOKEN.finditer(text)}
        setting = "probabilityWhenAddressed" if mentioned else "probability"
        probability = min(10000, self.registryValue(setting, channel))
        self._submit(
            irc,
            msg,
            channel,
            text,
            learn=True,
            reply=random.randrange(10000) < probability,
            addressed=mentioned,
        )

    def invalidCommand(self, irc, msg, tokens):
        """Respond after Infobot and recognized commands have had priority."""
        if not msg.repliedTo and self._users(irc, msg.args[0]) is not None:
            text = callbacks.addressed(irc, msg) or msg.args[1]
            if self._submit(irc, msg, msg.args[0], text, reply=True, addressed=True):
                # Limnoria's fallback chain checks its reply proxy, not the message tag.
                irc.repliedTo = True

    def brainsize(self, irc, msg, args, channel):
        """[<channel>]

        Report a channel brain's size on disk.
        """
        channel = channel or msg.args[0]
        if self._users(irc, channel) is None:
            irc.error("Use a channel the bot has joined.")
            return
        path = self._path(channel)
        irc.reply(
            "Brain size: %.2f MiB"
            % (os.path.getsize(path) / 1048576 if os.path.exists(path) else 0)
        )

    brainsize = wrap(brainsize, [additional("channel")])

    def teach(self, irc, msg, args, channel, text):
        """[<channel>] <text>

        Teach accepted text to a joined channel's brain.
        """
        channel = channel or msg.args[0]
        if self._users(irc, channel) is None:
            irc.error("Use a channel the bot has joined.")
            return
        self._submit(irc, msg, channel, text, learn=True)
        irc.replySuccess()

    teach = wrap(teach, [("checkCapability", "admin"), additional("channel"), "text"])

    def respond(self, irc, msg, args, channel, text):
        """[<channel>] <text>

        Generate a reply without learning the prompt.
        """
        self._submit(irc, msg, channel or msg.args[0], text, reply=True, addressed=True)

    respond = wrap(respond, [("checkCapability", "admin"), additional("channel"), "text"])

    def die(self):
        """Cancel delayed sends and close SQLite in its owning worker."""
        self._active = False
        with self._lock:
            for event in self._events:
                try:
                    schedule.removeEvent(event)
                except KeyError:
                    pass
            self._events.clear()

        def close():
            for brain in self._brains.values():
                brain.graph.close()
            self._brains.clear()

        self._executor.submit(close).result(timeout=30)
        self._executor.shutdown(wait=True)
        super().die()


Class = Cobe
# Copyright (c) 2015, waratte
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###
