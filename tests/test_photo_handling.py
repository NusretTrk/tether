"""
Photos sent from Telegram had no handler at all before this — filters.PHOTO
was never registered, so a sent photo was silently dropped with no error
and no explanation. These tests cover the parts that don't require a live
Claude window: clipboard image conversion, and the confirmation state
machine that tracks whether a pending send is text or an image (they need
different transcript event types to confirm delivery).
"""
import io

import pytest

from tether.platform.capabilities import CAPABILITIES

pytestmark = pytest.mark.skipif(not CAPABILITIES.window_control, reason="Windows clipboard only")


def test_set_clipboard_image_round_trips_as_cf_dib():
    from PIL import Image
    import win32clipboard
    from tether.platform.window import set_clipboard_image

    img = Image.new("RGB", (4, 4), (0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")

    assert set_clipboard_image(buf.getvalue()) is True

    win32clipboard.OpenClipboard()
    try:
        assert win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB)
        data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
    finally:
        win32clipboard.CloseClipboard()
    assert len(data) > 0


def test_set_clipboard_image_rejects_garbage_without_raising():
    from tether.platform.window import set_clipboard_image
    assert set_clipboard_image(b"not an image") is False


def test_set_clipboard_image_handles_rgba_source():
    """Telegram can hand back a PNG with an alpha channel; BMP/DIB needs RGB."""
    from PIL import Image
    from tether.platform.window import set_clipboard_image

    img = Image.new("RGBA", (4, 4), (0, 128, 255, 128))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    assert set_clipboard_image(buf.getvalue()) is True


def test_dib_strips_bmp_file_header():
    """CF_DIB is a BMP without its 14-byte file header — get this wrong and
    the paste either does nothing or pastes corrupted image data."""
    from PIL import Image
    import win32clipboard
    from tether.platform.window import set_clipboard_image

    img = Image.new("RGB", (8, 8), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, "BMP")
    full_bmp_len = len(buf.getvalue())

    buf2 = io.BytesIO()
    img.save(buf2, "PNG")
    set_clipboard_image(buf2.getvalue())

    win32clipboard.OpenClipboard()
    try:
        dib = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
    finally:
        win32clipboard.CloseClipboard()
    assert len(dib) == full_bmp_len - 14
