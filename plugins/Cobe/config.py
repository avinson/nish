###
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

"""Cobe learning and reply settings."""

from supybot import conf, registry


def configure(advanced):
    """Enable the Cobe plugin through the configuration wizard."""
    conf.registerPlugin("Cobe", True)


Cobe = conf.registerPlugin("Cobe")
conf.registerGlobalValue(
    Cobe, "ignoreRegex", registry.String("^[.@!$%]", "Ignore matching input, including commands.")
)
conf.registerGlobalValue(
    Cobe, "stripUrls", registry.Boolean(True, "Remove HTTP and HTTPS URLs before learning.")
)
conf.registerGlobalValue(
    Cobe,
    "stripNicks",
    registry.Boolean(True, "Remove whole nicknames before learning. Do not insert a placeholder."),
)
conf.registerChannelValue(
    Cobe,
    "probability",
    registry.NonNegativeInteger(200, "Automatic reply chance out of 10000; 200 means 2 percent."),
)
conf.registerChannelValue(
    Cobe,
    "probabilityWhenAddressed",
    registry.NonNegativeInteger(10000, "Reply chance out of 10000 when the bot is mentioned."),
)
conf.registerChannelValue(
    Cobe,
    "waitTimeBetweenSpeaking",
    registry.NonNegativeInteger(10, "Minimum seconds between automatic replies."),
)
conf.registerChannelValue(
    Cobe,
    "ignoreWaitTimeIfAddressed",
    registry.Boolean(True, "Bypass the automatic reply cooldown when addressed."),
)
conf.registerChannelValue(
    Cobe, "responseDelay", registry.Boolean(False, "Delay replies by 2 to 5 seconds.")
)
