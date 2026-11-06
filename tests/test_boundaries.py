"""Regression checks for input and output contamination."""

import pytest

from Cobe.core import clean_input, clean_output, strip_nicks


@pytest.mark.parametrize(
    "text", ["MAGIC_NICKhello", "magic_nick", "PLZREPLACEMENICKUNKNOWNWORDSHAHAH text"]
)
def test_reject_reserved_training(text):
    assert clean_input(text) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('MAGIC_NICKaccording to trump, "everyone", duh', 'according to trump, "everyone", duh'),
        ("magic_nickHello PLZREPLACEMENICKUNKNOWNWORDSHAHAH there", "Hello there"),
        ("🙂 café -- it’s fine", "🙂 café -- it’s fine"),
    ],
)
def test_output_repairs_legacy_prefix(text, expected):
    assert clean_output(text) == expected


def test_nick_boundaries_and_irc_case():
    assert strip_nicks("nish: finish [nick] NICK|", ["nish", "{nick}", "nick\\"]) == ": finish  "
    assert (
        clean_input("Nish: according to this person, hello there", ["nish"])
        == "According to this person, hello there"
    )
    assert clean_input("A+B hi there", ["A+B"]) == "A+B hi there"


def test_url_and_whitespace_cleaning():
    assert clean_input("hi https://example.org/nish\t there") == "Hi there"
    assert clean_input("MAGIC_NICK https://example.org/") == ""


def test_utf8_payload_limit():
    result = clean_output("🙂" * 500)
    assert len(result.encode()) <= 400
    assert len(result) <= 300
    assert "\ufffd" not in result
