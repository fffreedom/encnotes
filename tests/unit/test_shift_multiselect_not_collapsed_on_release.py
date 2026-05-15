#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Shift/Cmd multi-select not being collapsed by mouseReleaseEvent.

Bug: After Shift+click builds a range selection (selected_rows has N items),
mouseReleaseEvent checks:
  1. len(selected_rows) > 1  → True
  2. _is_within_click_threshold(pos) → True (it was a click not a drag)
  → calls _handle_click_in_multi_select() → collapses back to 1 note

The problem: mouseReleaseEvent cannot tell whether the multi-select was created
by THIS click (Shift/Cmd press — should KEEP multi-select) or by a PREVIOUS
operation (a plain click inside an existing multi-select — should COLLAPSE).

Fix: Record the modifiers at press time in _press_modifiers.
In mouseReleaseEvent, skip the collapse when _press_modifiers has Shift or
Command/Meta.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from note_list_widget import NoteListWidget
from PyQt6.QtWidgets import QApplication, QListWidget
from PyQt6.QtCore import Qt, QPoint

_app = QApplication.instance() or QApplication(sys.argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_widget():
    widget = NoteListWidget()
    widget.main_window = MagicMock()
    return widget


def _make_release_event(pos=None,
                        button=Qt.MouseButton.LeftButton):
    """Create a minimal mouse-release event mock (no real QMouseEvent needed
    because we patch super().mouseReleaseEvent to a no-op)."""
    event = MagicMock()
    event.button.return_value = button
    event.pos.return_value = pos or QPoint(10, 10)
    return event


# ---------------------------------------------------------------------------
# Tests: mouseReleaseEvent respects _press_modifiers
# ---------------------------------------------------------------------------

class TestShiftClickReleaseKeepsMultiSelect:
    """
    mouseReleaseEvent must NOT call _handle_click_in_multi_select when
    _press_modifiers contains Shift or Command/Meta.
    """

    def _run_release(self, widget, release_event):
        """Call mouseReleaseEvent with super() patched to avoid real Qt event."""
        with patch.object(QListWidget, 'mouseReleaseEvent'):
            widget.mouseReleaseEvent(release_event)

    def test_shift_press_release_does_not_collapse(self):
        """
        Given: _press_modifiers=Shift, selected_rows={0,1,2}, release within threshold
        Expect: _handle_click_in_multi_select NOT called.
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 2
        widget.selected_rows = {0, 1, 2}
        widget._press_modifiers = Qt.KeyboardModifier.ShiftModifier

        release_event = _make_release_event(pos=QPoint(12, 10))

        with patch.object(widget, '_handle_click_in_multi_select') as mock_collapse:
            self._run_release(widget, release_event)
            mock_collapse.assert_not_called(), (
                "_handle_click_in_multi_select must NOT be called when the press used "
                "Shift modifier. Calling it collapses the range selection just built."
            )

    def test_cmd_meta_press_release_does_not_collapse(self):
        """
        Given: _press_modifiers=Meta (Cmd on macOS), selected_rows={0,1}, release within threshold
        Expect: _handle_click_in_multi_select NOT called.
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 1
        widget.selected_rows = {0, 1}
        widget._press_modifiers = Qt.KeyboardModifier.MetaModifier

        release_event = _make_release_event(pos=QPoint(11, 10))

        with patch.object(widget, '_handle_click_in_multi_select') as mock_collapse:
            self._run_release(widget, release_event)
            mock_collapse.assert_not_called(), (
                "_handle_click_in_multi_select must NOT be called when the press used "
                "Command/Meta modifier."
            )

    def test_ctrl_press_release_does_not_collapse(self):
        """
        Ctrl key (Linux/Windows Cmd equivalent) must also be respected.
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 1
        widget.selected_rows = {0, 1}
        widget._press_modifiers = Qt.KeyboardModifier.ControlModifier

        release_event = _make_release_event(pos=QPoint(11, 10))

        with patch.object(widget, '_handle_click_in_multi_select') as mock_collapse:
            self._run_release(widget, release_event)
            mock_collapse.assert_not_called(), (
                "_handle_click_in_multi_select must NOT be called when the press used "
                "Ctrl modifier."
            )

    def test_plain_click_in_existing_multi_select_does_collapse(self):
        """
        Without Shift/Cmd: plain click inside existing multi-select SHOULD collapse.
        (This is the existing correct behavior for 'click to deselect multi-select'.)
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 1
        widget.selected_rows = {0, 1, 2}
        widget._press_modifiers = Qt.KeyboardModifier.NoModifier  # plain click

        release_event = _make_release_event(pos=QPoint(12, 10))  # within threshold

        with patch.object(widget, '_handle_click_in_multi_select') as mock_collapse:
            self._run_release(widget, release_event)
            mock_collapse.assert_called_once(), (
                "_handle_click_in_multi_select MUST be called on a plain click inside "
                "existing multi-select. This is the intended 'deselect' behavior."
            )

    def test_drag_does_not_collapse_regardless_of_modifiers(self):
        """
        Even with no modifier, a drag (release far from press) must NOT call collapse.
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 1
        widget.selected_rows = {0, 1, 2}
        widget._press_modifiers = Qt.KeyboardModifier.NoModifier

        release_event = _make_release_event(pos=QPoint(100, 10))  # far outside threshold

        with patch.object(widget, '_handle_click_in_multi_select') as mock_collapse:
            self._run_release(widget, release_event)
            mock_collapse.assert_not_called(), (
                "_handle_click_in_multi_select must NOT be called when release is outside "
                "the click threshold (drag occurred)."
            )


# ---------------------------------------------------------------------------
# Tests: _press_modifiers is initialized and set correctly
# ---------------------------------------------------------------------------

class TestPressModifiersAttribute:
    """
    The NoteListWidget must have a _press_modifiers attribute that is initialized
    to NoModifier and updated on mousePressEvent.
    """

    def test_initial_press_modifiers_is_no_modifier(self):
        """
        On construction, _press_modifiers must default to NoModifier (or None/falsy).
        """
        widget = _make_widget()
        # Either attribute doesn't exist yet (set only on first press) — acceptable
        # OR it exists with NoModifier. Both are valid.
        if hasattr(widget, '_press_modifiers'):
            is_falsy_or_no_modifier = (
                not widget._press_modifiers or
                widget._press_modifiers == Qt.KeyboardModifier.NoModifier
            )
            assert is_falsy_or_no_modifier, (
                "_press_modifiers initial value must be falsy or NoModifier."
            )

    def test_press_modifiers_cleared_after_release(self):
        """
        After mouseReleaseEvent completes, _press_modifiers must be reset to
        NoModifier (or falsy) so that a subsequent plain click is not confused
        with a prior Shift press.
        """
        widget = _make_widget()
        widget.press_pos = QPoint(10, 10)
        widget.press_row = 0
        widget.selected_rows = {0, 1}
        widget._press_modifiers = Qt.KeyboardModifier.ShiftModifier

        release_event = _make_release_event(pos=QPoint(12, 10))

        with patch.object(QListWidget, 'mouseReleaseEvent'):
            widget.mouseReleaseEvent(release_event)

        # After release, _press_modifiers should be reset
        if hasattr(widget, '_press_modifiers'):
            is_cleared = (
                not widget._press_modifiers or
                widget._press_modifiers == Qt.KeyboardModifier.NoModifier
            )
            assert is_cleared, (
                f"_press_modifiers must be cleared after mouseReleaseEvent, "
                f"got: {widget._press_modifiers!r}"
            )
