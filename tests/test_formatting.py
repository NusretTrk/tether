from tether.transport.formatting import chunk_text, normalize_for_comparison, truncate_with_notice


def test_short_text_single_chunk():
    assert chunk_text("hello") == ["hello"]


def test_empty_text_no_chunks():
    assert chunk_text("") == []


def test_long_text_splits_on_line_boundary():
    line = "x" * 100
    text = "\n".join([line] * 60)  # well over 4000 chars
    chunks = chunk_text(text, max_len=500)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 500
    # reassembled (with the newlines chunk_text strips at boundaries) still
    # contains all the original lines
    assert "".join(chunks).count("x") == text.count("x")


def test_no_line_boundary_hard_splits():
    text = "x" * 5000  # one giant line, no newlines at all
    chunks = chunk_text(text, max_len=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) == 5000


def test_truncate_with_notice_short_text_unchanged():
    assert truncate_with_notice("short", 100, "…") == "short"


def test_truncate_with_notice_cuts_and_appends():
    result = truncate_with_notice("x" * 100, 20, "[cut]")
    assert len(result) == 20
    assert result.endswith("[cut]")


# ---- normalize_for_comparison: closes the false "wasn't confirmed as
# sent" report - the target app's own transcript doesn't always record
# text byte-identical to what was pasted, even when delivery genuinely
# succeeded. ----

def test_identical_text_matches():
    assert normalize_for_comparison("hello world") == normalize_for_comparison("hello world")


def test_smart_quotes_normalize_to_straight_quotes():
    assert normalize_for_comparison("it’s a “test”") == normalize_for_comparison('it\'s a "test"')


def test_smart_dashes_normalize_to_hyphen():
    assert normalize_for_comparison("a — b – c") == normalize_for_comparison("a - b - c")


def test_ellipsis_character_normalizes_to_three_dots():
    assert normalize_for_comparison("wait…") == normalize_for_comparison("wait...")


def test_collapsed_whitespace_runs_match():
    assert normalize_for_comparison("hello   world\n\nfoo") == normalize_for_comparison("hello world foo")


def test_leading_trailing_whitespace_ignored():
    assert normalize_for_comparison("  hello  ") == normalize_for_comparison("hello")


def test_genuinely_different_text_does_not_match():
    assert normalize_for_comparison("hello world") != normalize_for_comparison("goodbye world")


def test_unicode_composed_and_decomposed_forms_match():
    composed = "café"        # é as a single code point
    decomposed = "café"     # e + combining acute accent
    assert normalize_for_comparison(composed) == normalize_for_comparison(decomposed)
