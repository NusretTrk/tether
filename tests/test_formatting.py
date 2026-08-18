from tether.transport.formatting import chunk_text, truncate_with_notice


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
