import pytest

from cmux_handoff_relay.errors import HandoffParseError
from cmux_handoff_relay.parser import parse_latest_handoff


def test_valid_block() -> None:
    text = """before
<<<HANDOFF target=review submit=false>>>
Prompt text
<<<END_HANDOFF>>>
after"""

    block = parse_latest_handoff(text)

    assert block.target == "review"
    assert block.submit is False
    assert block.body == "Prompt text"


def test_multiple_blocks_choose_latest() -> None:
    text = """<<<HANDOFF target=review submit=false>>>
Old prompt
<<<END_HANDOFF>>>
noise
<<<HANDOFF target=qa submit=false>>>
Latest prompt
<<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.target == "qa"
    assert block.body == "Latest prompt"


def test_malformed_latest_block_is_rejected_even_if_earlier_block_is_valid() -> None:
    text = """<<<HANDOFF target=review submit=false>>>
Old valid prompt
<<<END_HANDOFF>>>
noise
<<<HANDOFF target=qa>>>
Latest malformed prompt
<<<END_HANDOFF>>>"""

    with pytest.raises(HandoffParseError, match="Malformed HANDOFF header"):
        parse_latest_handoff(text)


def test_missing_end_rejected() -> None:
    text = """<<<HANDOFF target=review submit=false>>>
Prompt text"""

    with pytest.raises(HandoffParseError, match="missing"):
        parse_latest_handoff(text)


def test_invalid_header_rejected() -> None:
    text = """<<<HANDOFF target=review>>>
Prompt text
<<<END_HANDOFF>>>"""

    with pytest.raises(HandoffParseError, match="Malformed HANDOFF header"):
        parse_latest_handoff(text)


def test_empty_body_rejected() -> None:
    text = """<<<HANDOFF target=review submit=false>>>

<<<END_HANDOFF>>>"""

    with pytest.raises(HandoffParseError, match="empty"):
        parse_latest_handoff(text)


def test_metadata_submit_true_is_only_parsed_metadata() -> None:
    text = """<<<HANDOFF target=review submit=true>>>
Prompt text
<<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.submit is True
    assert block.body == "Prompt text"


def test_nonce_metadata_is_parsed_when_present() -> None:
    text = """<<<HANDOFF target=review submit=false nonce=abc-123>>>
Prompt text
<<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.nonce == "abc-123"


def test_trailing_terminal_padding_is_ignored() -> None:
    text = (
        "<<<HANDOFF target=review submit=false>>>" + "   \n"
        "Prompt text\n"
        "<<<END_HANDOFF>>>" + "   "
    )

    block = parse_latest_handoff(text)

    assert block.target == "review"
    assert block.body == "Prompt text"


def test_known_terminal_gutter_is_ignored_for_marker_lines() -> None:
    text = """• <<<HANDOFF target=review submit=false nonce=n1>>>
  Prompt text
    Preserve intended indentation after gutter
  <<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.target == "review"
    assert block.nonce == "n1"
    assert block.body == "Prompt text\n  Preserve intended indentation after gutter"


def test_guttered_end_marker_controls_body_gutter_stripping() -> None:
    text = """• <<<HANDOFF target=review submit=false>>>
  Prompt text
    Preserve intended indentation after gutter
  <<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.body == "Prompt text\n  Preserve intended indentation after gutter"


def test_header_gutter_does_not_strip_indented_body_when_end_is_not_guttered() -> None:
    text = """• <<<HANDOFF target=review submit=false>>>
  Preserve this two-space indentation
<<<END_HANDOFF>>>"""

    block = parse_latest_handoff(text)

    assert block.body == "  Preserve this two-space indentation"


def test_nested_handoff_headers_are_rejected() -> None:
    text = """<<<HANDOFF target=review submit=false>>>
Do not route this sample:
<<<HANDOFF target=qa submit=false>>>
Sample body
<<<END_HANDOFF>>>
<<<END_HANDOFF>>>"""

    with pytest.raises(HandoffParseError, match="nested"):
        parse_latest_handoff(text)
