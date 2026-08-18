"""
UI Automation elements go stale while a live tree is being walked - reading
a property on one raises _ctypes.COMError. Verified live: this crashed
dialog_job with "An event was unable to invoke any of the subscribers"
while a reply was streaming into the chat mid-walk. One bad element must
not blow up the whole walk.

Uses fake control objects rather than real UIA, so this runs without a
live window and without accessibility support on this platform.
"""
import pytest

pytest.importorskip("_ctypes")
from _ctypes import COMError  # noqa: E402

from tether.platform.capabilities import CAPABILITIES  # noqa: E402

pytestmark = pytest.mark.skipif(
    not CAPABILITIES.accessibility, reason="uia module only imports on Windows"
)


def _make_com_error():
    # Real shape observed live: (-2147220991, 'An event was unable to
    # invoke any of the subscribers', (None, None, None, 0, None))
    return COMError(-2147220991, "An event was unable to invoke any of the subscribers",
                     (None, None, None, 0, None))


class StaleElement:
    """Raises COMError on any property access, like a UIA element that went
    stale mid-walk."""
    @property
    def Name(self):
        raise _make_com_error()

    @property
    def ControlTypeName(self):
        raise _make_com_error()

    def GetChildren(self):
        raise _make_com_error()


class GoodElement:
    def __init__(self, name, ctype, children=None):
        self.Name = name
        self.ControlTypeName = ctype
        self._children = children or []

    def GetChildren(self):
        return self._children


def test_stale_sibling_does_not_abort_the_walk():
    from tether.platform import uia
    root = GoodElement("root", "PaneControl", children=[
        GoodElement("Alpha", "ButtonControl"),
        StaleElement(),  # goes stale between GetChildren() and property read
        GoodElement("Beta", "ButtonControl"),
    ])
    result = uia.collect_named_controls(root)
    names = [n for _, n in result]
    assert "Alpha" in names
    assert "Beta" in names
    assert len(names) == 2  # the stale one contributed nothing, did not crash


def test_stale_get_children_treated_as_leaf():
    from tether.platform import uia
    root = GoodElement("root", "PaneControl", children=[StaleElement()])
    # StaleElement.GetChildren raises when we recurse into it — must not propagate
    result = uia.collect_named_controls(root)
    assert result == []


def test_walk_count_survives_stale_elements():
    from tether.platform import uia
    root = GoodElement("root", "PaneControl", children=[
        GoodElement("a", "x"), StaleElement(), GoodElement("b", "x"),
    ])
    count = uia._walk_count(root)
    assert count == 3  # counted before recursing, stale one still counted as a node


def test_find_control_by_name_skips_stale_and_keeps_looking():
    from tether.platform import uia
    target = GoodElement("target", "ButtonControl")
    root = GoodElement("root", "PaneControl", children=[StaleElement(), target])
    found = uia.find_control_by_name(root, "target")
    assert found is target
