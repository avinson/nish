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
