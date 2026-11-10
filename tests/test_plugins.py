"""Exercise plugin routing through Limnoria's IRC harness."""

from supybot import conf
from supybot import test as supytest
from supybot import ircmsgs
from unittest import mock


class CobePluginTest(supytest.ChannelPluginTestCase):
    plugins = ("Cobe", "Infobot", "Karma", "Seen")
    timeout = 5

    def runTest(self):
        """Provide the legacy harness's default method on Python 3.12."""

    def setUp(self):
        super().setUp()
        conf.supybot.plugins.Cobe.responseDelay.setValue(False)
        conf.supybot.plugins.Cobe.probability.setValue(0)

    def test_infobot_precedence(self):
        self.assertNotError("coffee is delicious")
        self.assertResponse("what is coffee?", "coffee is delicious.")

    def test_unicode_fact(self):
        self.assertNotError("café is très bien 🙂")
        self.assertResponse("what is café?", "café is très bien 🙂.")

    def test_karma(self):
        self.assertNotError("karma testthing")

    def test_seen_uses_safe_reader(self):
        self.assertEqual(self.irc.getCallback("Seen").db.__class__.__name__, "SafeSeenDB")

    def test_unknown_addressed_prompt_uses_real_brain(self):
        plugin = self.irc.getCallback("Cobe")
        plugin._executor.submit(
            lambda: plugin._brain(self.channel).learn("A zebra tells a bread story")
        ).result(timeout=5)
        fallback = self.irc.getCallback("Misc")
        with mock.patch.object(fallback, "invalidCommand", wraps=fallback.invalidCommand) as called:
            self.assertResponse("zebra story", "A zebra tells a bread story")
            called.assert_not_called()

    def test_ordinary_message_does_not_reply(self):
        self.assertNoResponse("an ordinary sentence with words", usePrefixChar=False, timeout=0.5)

    def test_delayed_callback_and_no_self_learning(self):
        plugin = self.irc.getCallback("Cobe")
        conf.supybot.plugins.Cobe.responseDelay.setValue(True)
        msg = ircmsgs.privmsg(self.channel, "hello there", prefix="alice!a@host")
        brain = mock.Mock()
        brain.reply.return_value = "MAGIC_NICKaccording to someone, hello"
        with (
            mock.patch.object(plugin, "_brain", return_value=brain),
            mock.patch("Cobe.plugin.schedule.addEvent") as scheduled,
        ):
            plugin._submit(self.irc, msg, self.channel, "hello there", reply=True, addressed=True)
            plugin._executor.submit(lambda: None).result(timeout=5)
            callback = scheduled.call_args.args[0]
            self.assertTrue(callable(callback))
            self.assertIsNone(self.irc.takeMsg())
            callback()
            self.assertEqual(self.irc.takeMsg().args[1], "according to someone, hello")
            brain.learn.assert_not_called()

    def test_cooldown_and_private_message_guard(self):
        plugin = self.irc.getCallback("Cobe")
        conf.supybot.plugins.Cobe.responseDelay.setValue(False)
        brain = mock.Mock()
        brain.reply.return_value = "A normal generated sentence"
        msg = ircmsgs.privmsg(self.channel, "hello there", prefix="alice!a@host")
        with mock.patch.object(plugin, "_brain", return_value=brain):
            for _ in range(2):
                plugin._submit(self.irc, msg, self.channel, "hello there", reply=True)
            plugin._executor.submit(lambda: None).result(timeout=5)
            self.assertEqual(brain.reply.call_count, 1)
            plugin._submit(self.irc, msg, "alice", "private text", learn=True, reply=True)
            brain.learn.assert_not_called()

    def test_raw_unicode_learning_and_marker_rejection(self):
        plugin = self.irc.getCallback("Cobe")
        brain = mock.Mock()
        with mock.patch.object(plugin, "_brain", return_value=brain):
            self.assertNoResponse(
                "the café has good bread 🙂", usePrefixChar=False, frm="alice!a@host", timeout=0.1
            )
            plugin._executor.submit(lambda: None).result(timeout=5)
            brain.learn.assert_called_once_with("The café has good bread 🙂")
            self.assertNoResponse(
                "MAGIC_NICKevil poisoned text", usePrefixChar=False, frm="alice!a@host", timeout=0.1
            )
            plugin._executor.submit(lambda: None).result(timeout=5)
            self.assertEqual(brain.learn.call_count, 1)

    def test_two_percent_random_reply_boundaries(self):
        plugin = self.irc.getCallback("Cobe")
        conf.supybot.plugins.Cobe.probability.setValue(200)
        for roll, expected in ((0, True), (199, True), (200, False), (9999, False)):
            msg = ircmsgs.privmsg(self.channel, "an ordinary sentence", prefix="alice!a@host")
            with (
                mock.patch("Cobe.plugin.random.randrange", return_value=roll),
                mock.patch.object(plugin, "_submit") as submit,
            ):
                plugin.doPrivmsg(self.irc, msg)
                self.assertEqual(submit.call_args.kwargs["reply"], expected)

    def test_automatic_reply_metrics_track_outcomes_without_text(self):
        plugin = self.irc.getCallback("Cobe")
        conf.supybot.plugins.Cobe.probability.setValue(200)
        brain = mock.Mock()
        brain.reply.return_value = "A normal generated sentence"
        msg = ircmsgs.privmsg(self.channel, "private conversation", prefix="alice!a@host")
        with (
            mock.patch("Cobe.plugin.random.randrange", return_value=0),
            mock.patch.object(plugin, "_brain", return_value=brain),
            mock.patch.object(plugin.log, "info") as logged,
        ):
            plugin.doPrivmsg(self.irc, msg)
            plugin._executor.submit(lambda: None).result(timeout=5)
            second = ircmsgs.privmsg(self.channel, "another private message", prefix="alice!a@host")
            plugin.doPrivmsg(self.irc, second)
            plugin._executor.submit(lambda: None).result(timeout=5)
            plugin._log_auto_stats()
            args = logged.call_args.args
            self.assertEqual(args[1:], (2, 0.04, 2, 0, 1, 0, 1, 0))
            self.assertNotIn("private conversation", str(args))
