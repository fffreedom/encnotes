#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for drop indicator being cleared after a note drag-and-drop.

Bug: after dragging (multi-selected) notes onto a folder, the target folder
retains the pale-yellow highlight background. The highlight is drawn in
FolderListWidget.paintEvent() whenever _drop_indicator_position is not None.

Root cause: _handle_note_drop() does not call _clear_drop_indicator() before
scheduling the delayed UI refresh via QTimer.singleShot(). The folder-drop
path (_handle_folder_drop) correctly calls _clear_drop_indicator() at line 672,
but the note-drop path has no such call.

Fix: call self._clear_drop_indicator() in _handle_note_drop() before the
QTimer.singleShot() call.
"""

import sys
import os
import types
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QRect


def _import_folder_list_widget():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from main_window import FolderListWidget
    return FolderListWidget


def _make_self_stub(FolderListWidget):
    """
    Build a plain object that quacks like a FolderListWidget for the purpose
    of invoking _handle_note_drop as an unbound method.

    We bind the *real* _clear_drop_indicator() so its attribute-clearing logic
    runs on our stub — no Qt widget construction needed.
    """
    stub = MagicMock()

    # Simulate: drop indicator is set (mid-drag state)
    stub._drop_indicator_position = 'on'
    stub._drop_indicator_rect = QRect(0, 0, 100, 30)
    stub._drop_target_item = MagicMock()

    # Bind the real _clear_drop_indicator so it actually mutates stub attributes
    stub._clear_drop_indicator = lambda: FolderListWidget._clear_drop_indicator(stub)

    # _expand_folder_ancestors is called but not under test here — keep as mock
    stub._expand_folder_ancestors = MagicMock()

    # note_manager dependency
    stub.main_window.note_manager.move_note_to_folder = MagicMock()

    return stub


# ---------------------------------------------------------------------------
# Core regression tests — these FAIL before the fix
# ---------------------------------------------------------------------------

class TestDropIndicatorClearedAfterNoteDrop:
    """
    _handle_note_drop must call _clear_drop_indicator() so that the pale-yellow
    background does not persist after a note drag-and-drop completes.
    """

    def test_drop_indicator_position_is_none_after_note_drop(self):
        """
        After _handle_note_drop() runs, _drop_indicator_position must be None.

        Before the fix: _handle_note_drop() never calls _clear_drop_indicator(),
        so _drop_indicator_position stays 'on' and paintEvent keeps drawing the
        yellow highlight on the target folder.
        """
        FolderListWidget = _import_folder_list_widget()
        stub = _make_self_stub(FolderListWidget)

        assert stub._drop_indicator_position == 'on', "Pre-condition: indicator must be set"

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, ['note-id-1', 'note-id-2'], 'folder-id-1', 0)

        assert stub._drop_indicator_position is None, (
            f"_drop_indicator_position should be None after _handle_note_drop(), "
            f"but got {stub._drop_indicator_position!r}. "
            f"The pale-yellow folder background persists because _clear_drop_indicator() "
            f"was never called."
        )

    def test_drop_indicator_rect_is_none_after_note_drop(self):
        """
        After _handle_note_drop(), _drop_indicator_rect must also be cleared.
        """
        FolderListWidget = _import_folder_list_widget()
        stub = _make_self_stub(FolderListWidget)

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, ['note-id-1'], 'folder-id-1', 0)

        assert stub._drop_indicator_rect is None, (
            f"_drop_indicator_rect should be None after _handle_note_drop(), "
            f"but got {stub._drop_indicator_rect!r}."
        )

    def test_drop_indicator_target_item_is_none_after_note_drop(self):
        """
        After _handle_note_drop(), _drop_target_item must also be cleared.
        """
        FolderListWidget = _import_folder_list_widget()
        stub = _make_self_stub(FolderListWidget)

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, ['note-id-1'], 'folder-id-1', 0)

        assert stub._drop_target_item is None, (
            f"_drop_target_item should be None after _handle_note_drop(), "
            f"but got {stub._drop_target_item!r}."
        )

    def test_symmetry_folder_drop_also_clears_indicator(self):
        """
        Symmetry sanity check: the folder-drop path (_handle_folder_drop) already
        clears the indicator. This test confirms that baseline still holds so we
        can compare the two code paths.
        """
        FolderListWidget = _import_folder_list_widget()
        stub = _make_self_stub(FolderListWidget)
        stub._drop_indicator_position = 'on'
        stub.main_window.note_manager.update_folder_parent = MagicMock()

        with patch('main_window.QTimer'):
            FolderListWidget._handle_folder_drop(stub, 'src-folder', 'target-folder', 0)

        assert stub._drop_indicator_position is None, (
            "folder-drop path reference: _drop_indicator_position must be None"
        )
