###
# Copyright (c) 2004-2005,2009,2011, James Vega
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

import os
import string
import fnmatch
import re
import time
import pickle as pickle

import supybot.dbi as dbi
import supybot.utils as utils
import supybot.world as world
from supybot.commands import *
import supybot.ircmsgs as ircmsgs
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

from .storage import InfobotDB

RESERVED_MARKERS = re.compile(r"MAGIC_NICK|PLZREPLACEMENICKUNKNOWNWORDSHAHAH", re.IGNORECASE)

ends = [
    ".",
]
dunnos = [
    "Dunno",
    "No idea",
    "I don't know",
    "I have no idea",
    "I don't have a clue",
    "Bugger all, I dunno",
    "Wish I knew",
]
starts = [
    "",
]
confirms = ["10-4", "Okay", "Got it", "Gotcha", "I hear ya"]
NORESPONSE = "<reply>"
initialIs = {
    "who": NORESPONSE,
    "what": NORESPONSE,
    "when": NORESPONSE,
    "where": NORESPONSE,
    "why": NORESPONSE,
    "it": NORESPONSE,
    "that": NORESPONSE,
    "this": NORESPONSE,
}
initialAre = {
    "who": NORESPONSE,
    "what": NORESPONSE,
    "when": NORESPONSE,
    "where": NORESPONSE,
    "why": NORESPONSE,
    "it": NORESPONSE,
    "they": NORESPONSE,
    "these": NORESPONSE,
    "those": NORESPONSE,
    "roses": NORESPONSE,
    "violets": NORESPONSE,
}


class Dunno(Exception):
    pass


class Infobot(callbacks.PluginRegexp):
    addressedRegexps = ["doForce", "doForget", "doChange", "doFactoid", "doUnknown"]
    unaddressedRegexps = ["doFactoid", "doUnknown"]
    callBefore = ["Youtube", "Cobe"]

    def __init__(self, irc):
        self.__parent = super(Infobot, self)
        self.__parent.__init__(irc)
        self.db = InfobotDB()
        self.irc = None
        self.msg = None
        self.changed = False
        self.added = False

    def die(self):
        self.__parent.die()
        self.db.close()

    def reset(self):
        self.db.close()

    def error(self, s, irc=None, msg=None):
        if irc is None:
            assert self.irc is not None
            irc = self.irc
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        if msg.repliedTo:
            self.log.debug("Already replied, not replying again.")
            return
        if msg.addressed:
            self.irc.error(s)
        else:
            self.log.warning(s)

    def reply(self, s, irc=None, msg=None, action=False, substitute=True):
        if irc is None:
            assert self.irc is not None
            irc = self.irc
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        if msg.repliedTo:
            self.log.debug("Already replied, not replying again.")
            return
        if substitute:
            s = ircutils.standardSubstitute(irc, msg, s)
        s = RESERVED_MARKERS.sub("", s).strip()
        if not s:
            return
        irc.reply(s, prefixNick=False, action=action, msg=msg)

    def confirm(self, irc=None, msg=None):
        if self.registryValue("personality"):
            s = self.db.getConfirm()
        else:
            s = conf.supybot.replies.success()
        self.reply(s, irc=irc, msg=msg)

    def missing(self, fact, irc=None, msg=None):
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        self.reply(
            format("I didn't have anything matching %q, %s.", fact, msg.nick), irc=irc, msg=msg
        )

    def dunno(self, irc=None, msg=None):
        if self.registryValue("personality"):
            s = self.db.getDunno()
        else:
            s = self.registryValue("boringDunno")
        self.reply(s, irc=irc, msg=msg)

    _alternation = re.compile(r"(?<!\\)\|")

    def factoid(self, key, irc=None, msg=None, dunno=False, prepend="", isAre=None):
        if irc is None:
            assert self.irc is not None
            irc = self.irc
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        if isAre is not None:
            isAre = isAre.lower()
        channel = dynamic.channel
        try:
            if isAre is None:
                if self.db.hasIs(channel, key):
                    isAre = "is"
                    value = self.db.getIs(channel, key)
                elif self.db.hasAre(channel, key):
                    isAre = "are"
                    value = self.db.getAre(channel, key)
            elif isAre == "is":
                if not self.db.hasIs(channel, key):
                    isAre = None
                else:
                    value = self.db.getIs(channel, key)
            elif isAre == "are":
                if not self.db.hasAre(channel, key):
                    isAre = None
                else:
                    value = self.db.getAre(channel, key)
            else:
                self.log.debug("Returning early: Got a bad isAre value.")
                return
        except dbi.InvalidDBError as e:
            self.error("Unable to access db: %s" % e)
            return
        if isAre is None:
            if msg.addressed:
                if dunno:
                    self.dunno(irc=irc, msg=msg)
                # else:
                #    raise Dunno
        else:
            value = utils.iter.choice(self._alternation.split(value))
            value = value.replace("\|", "|")
            lvalue = value.lower()
            if lvalue.startswith("<reply>"):
                value = value[7:].strip()
                if value:
                    self.reply(value, irc=irc, msg=msg)
                else:
                    self.log.debug("Not sending empty factoid.")
            elif lvalue.startswith("<action>"):
                self.reply(value[8:].strip(), irc=irc, msg=msg, action=True)
            else:
                # s = format('%s %s %s, $who', key, isAre, value)
                s = format("%s %s %s.", key, isAre, value)
                s = prepend + s
                self.reply(s, irc=irc, msg=msg)

    _iAm = (re.compile(r"^i am ", re.I), "%s is ")
    _my = (re.compile(r"^my ", re.I), "%s's ")
    _your = (re.compile(r"^your ", re.I), "%s's ")

    def normalize(self, s, bot, nick):
        s = ircutils.stripFormatting(s)
        s = s.strip()  # After stripFormatting for formatted spaces.
        s = utils.str.normalizeWhitespace(s)
        s = self._iAm[0].sub(self._iAm[1] % nick, s)
        # s = self._my[0].sub(self._my[1] % nick, s)
        # s = self._your[0].sub(self._your[1] % bot, s)
        contractions = [
            ("what's", "what is"),
            ("where's", "where is"),
            ("who's", "who is"),
            ("wtf's", "wtf is"),
        ]
        for contraction, replacement in contractions:
            if s.startswith(contraction):
                s = replacement + s[len(contraction) :]
        return s

    _forceRe = re.compile(r"^no[,: -]+", re.I)

    def doPrivmsg(self, irc, msg):
        try:
            if RESERVED_MARKERS.search(msg.args[1]):
                return
            if ircmsgs.isCtcp(msg):
                self.log.debug("Returning early from doPrivmsg: isCtcp(msg).")
                return
            s = callbacks.addressed(irc, msg)
            payload = self.normalize(s or msg.args[1], irc.nick, msg.nick)
            if s:
                msg.tag("addressed", payload)
            msg = ircmsgs.IrcMsg(args=(msg.args[0], payload), msg=msg)
            self.__parent.doPrivmsg(irc, msg)
        finally:
            self.changed = False
            self.added = False

    def callCommand(self, name, irc, msg, *L, **kwargs):
        try:
            self.irc = irc
            self.msg = msg
            # For later dynamic scoping
            channel = plugins.getChannel(msg.args[0])
            self.__parent.callCommand(name, irc, msg, *L, **kwargs)
        finally:
            self.irc = None
            self.msg = None

    def _callRegexp(self, name, irc, msg, *L, **kwargs):
        try:
            self.irc = irc
            self.msg = msg
            # For later dynamic scoping
            channel = plugins.getChannel(msg.args[0])
            self.__parent._callRegexp(name, irc, msg, *L, **kwargs)
        finally:
            self.irc = None
            self.msg = None

    def doForget(self, irc, msg, match):
        r"^forget\s+(.+?[?!. ]*)$"
        fact = match.group(1)
        fact = fact.rstrip("?")
        deleted = False
        for method in [self.db.delIs, self.db.delAre]:
            try:
                method(dynamic.channel, fact)
                deleted = True
            except dbi.NoRecordError:
                pass
        if deleted:
            self.confirm()
        elif msg.addressed:
            self.missing(fact, irc=irc, msg=msg)

    def doForce(self, irc, msg, match):
        r"^no,\s+(\w+,\s+)?(.+?)\s+(?<!\\)(was|is|am|were|are)\s+(.+?[?!. ]*)$"
        (nick, key, isAre, value) = match.groups()
        value = value.rstrip()
        key.rstrip("?")
        if not msg.addressed:
            if nick is None:
                self.log.debug(
                    "Not forcing because we weren't addressed and "
                    "payload wasn't of the form: no, irc.nick, .."
                )
                return
            nick = nick.rstrip(" \t,")
            if not ircutils.nickEqual(nick, irc.nick):
                self.log.debug("Not forcing because the regexp nick didn't match our nick.")
                return
        else:
            if nick is not None:
                stripped = nick.rstrip(" \t,")
                if not ircutils.nickEqual(stripped, irc.nick):
                    key = nick + key
        isAre = isAre.lower()
        if self.added:
            return
        channel = dynamic.channel
        if isAre in ("was", "is", "am"):
            if self.db.hasIs(channel, key):
                oldValue = self.db.getIs(channel, key)
                if oldValue.lower() == value.lower():
                    self.reply(format("I already had it that way, %s.", msg.nick))
                    return
                self.log.debug("Forcing %q to %q.", key, value)
                self.added = True
                self.db.setIs(channel, key, value)
        else:
            if self.db.hasAre(channel, key):
                oldValue = self.db.getAre(channel, key)
                if oldValue.lower() == value.lower():
                    self.reply(format("I already had it that way, %s.", msg.nick))
                    return
                self.log.debug("Forcing %q to %q.", key, value)
                self.added = True
                self.db.setAre(channel, key, value)
        self.confirm()

    def doChange(self, irc, msg, match):
        r"^(.+)\s+=~\s+(.+)$"
        (fact, regexp) = match.groups()
        changed = False
        try:
            r = utils.str.perlReToReplacer(regexp)
        except ValueError as e:
            if msg.addressed:
                irc.errorInvalid("regexp", regexp)
            else:
                self.log.debug("Invalid regexp: %s" % regexp)
                return
        if self.changed:
            return
        for method in [self.db.changeIs, self.db.changeAre]:
            try:
                method(dynamic.channel, fact, r)
                self.changed = True
            except dbi.NoRecordError:
                pass
        if self.changed:
            self.confirm()
        else:
            self.missing(fact, irc=irc, msg=msg)

    def doUnknown(self, irc, msg, match):
        r"^(.+?)\s*(\?[?!. ]*)?$"
        (key, question) = match.groups()
        question = True  # assume everything is a question
        if not msg.addressed:
            if question is None:
                self.log.debug(
                    "Not answering question since we weren't "
                    "addressed and there was no question mark."
                )
                return
            if self.registryValue("unaddressed.answerQuestions"):
                self.factoid(key, prepend=utils.iter.choice(starts))
        else:
            self.factoid(key, prepend=utils.iter.choice(starts))

    def doFactoid(self, irc, msg, match):
        r"^(.+?)\s+(?<!\\)(was|is|am|were|are)\s+(also\s+)?(.+?[?!. ]*)$"
        (key, isAre, also, value) = match.groups()
        key = key.replace("\\", "")
        isAre = isAre.lower()
        value = value.rstrip().rstrip("?")
        if isAre in ("was", "is", "am"):
            isAre = "is"
        else:
            isAre = "are"
        if key.lower() in ("where", "what", "who", "wtf"):
            # It's a question.
            if msg.addressed or self.registryValue("unaddressed.answerQuestions"):
                self.factoid(value, isAre=isAre, prepend=utils.iter.choice(starts))
            return
        if not msg.addressed and not self.registryValue("unaddressed.snarfDefinitions"):
            return
        if self.added:
            return
        if isAre == "is":
            if self.db.hasIs(dynamic.channel, key):
                oldValue = self.db.getIs(dynamic.channel, key)
                if oldValue.lower() == value.lower() and self.registryValue(
                    "unaddressed.replyExistingFactoid", dynamic.channel
                ):
                    self.reply(format("I already had it that way, %s.", msg.nick))
                    return
                if also:
                    self.log.debug("Adding %q to %q.", key, value)
                    value = format("%s and %s", oldValue, value)
                elif msg.addressed:
                    if initialIs.get(key) != value:
                        self.reply(format("... but %s is %s ...", key, oldValue), substitute=False)
                        return
                else:
                    self.log.debug("Already have a %q key.", key)
                    return
            self.added = True
            self.db.setIs(dynamic.channel, key, value)
        else:
            if self.db.hasAre(dynamic.channel, key):
                oldValue = self.db.getAre(dynamic.channel, key)
                if oldValue.lower() == value.lower() and self.registryValue(
                    "unaddressed.replyExistingFactoid", dynamic.channel
                ):
                    self.reply(format("I already had it that way, %s.", msg.nick))
                    return
                if also:
                    self.log.debug("Adding %q to %q.", key, value)
                    value = format("%s and %s", oldValue, value)
                elif msg.addressed:
                    if initialAre.get(key) != value:
                        self.reply(format("... but %s are %s ...", key, oldValue), substitute=False)
                        return
                else:
                    self.log.debug("Already have a %q key.", key)
                    return
            self.added = True
            self.db.setAre(dynamic.channel, key, value)
        if msg.addressed:
            self.confirm()

    def listfacts(self, irc, msg, args, channel, glob):
        """[<channel>] [<glob>]

        Returns the facts in the Infobot database matching <glob>.
        """
        facts = self.db.getFacts(channel, glob)
        if not facts:
            self.dunno(irc=irc, msg=msg)
        else:
            irc.reply(utils.str.format("%L", list(facts)))

    listfacts = wrap(listfacts, ["channeldb", additional("glob", "*")])

    def stats(self, irc, msg, args, channel):
        """[<channel>]

        Returns the number of changes and requests made to the Infobot database
        since the plugin was loaded.  <channel> is only necessary if the
        message isn't in the channel itself.
        """
        changes = self.db.getChangeCount(channel)
        responses = self.db.getResponseCount(channel)
        now = time.time()
        diff = int(now - world.startedAt)
        mode = {True: "optional", False: "require"}
        answer = self.registryValue("unaddressed.answerQuestions")
        irc.reply(
            format(
                "Since %s, there %h been %n and %n. I have been awake"
                " for %s this session, and currently reference %n. "
                "Addressing is in %s mode.",
                time.ctime(world.startedAt),
                changes,
                (changes, "modification"),
                (responses, "question"),
                utils.timeElapsed(int(now - world.startedAt)),
                (self.db.getNumFacts(channel), "factoid"),
                mode[answer],
            )
        )

    stats = wrap(stats, ["channeldb"])
    status = stats

    def tell(self, irc, msg, args, channel, nick, _, factoid):
        """[<channel>] <nick> [about] <factoid>

        Tells <nick> about <factoid>.  <channel> is only necessary if the
        message isn't sent in the channel itself.
        """
        try:
            hostmask = irc.state.nickToHostmask(nick)
        except KeyError:
            irc.error(format("I haven't seen %s, I'll let you do the telling.", nick), Raise=True)
        newmsg = ircmsgs.privmsg(irc.nick, factoid, prefix=hostmask)
        try:
            prepend = format("%s wants you to know that ", msg.nick)
            self.factoid(factoid, msg=newmsg, prepend=prepend)
            msg.tag("repliedTo")
        except Dunno:
            self.dunno()

    tell = wrap(tell, ["channeldb", "something", optional(("literal", "about")), "text"])

    def update(self, irc, msg, args, channel, isAre, url):
        """[<channel>] {is,are} <url|file>

        Updates the Infobot database using the dumped database at remote <url>
        or local <file>.  The first argument should be "is" or "are", and
        determines whether the is or are database is updated.
        """
        isAre = isAre.lower()
        if isAre == "is":
            add = self.db.setIs
        elif isAre == "are":
            add = self.db.setAre
        count = 0
        try:
            fd = utils.web.getUrlFd(url)
        except utils.web.Error:
            try:
                fd = open(url, encoding="utf-8")
            except EnvironmentError:
                irc.errorInvalid("url or file")
        for line in fd:
            line = line.rstrip("\r\n")
            try:
                (key, value) = line.split(" => ", 1)
            except ValueError:  # unpack list of wrong size
                self.log.debug("Invalid line: %r", line)
                continue
            else:
                key = key.rstrip()
                value = value.lstrip()
                self.log.debug("Adding factoid %r with value %r.", key, value)
                add(channel, key, value)
                count += 1
        fd.close()
        irc.replySuccess(format("%n added.", (count, "factoid")))

    update = wrap(update, ["owner", "channeldb", ("literal", ("is", "are")), first("url", "text")])


Class = Infobot

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
