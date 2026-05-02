#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for multi-select note drag order preservation.

Bug: when dragging N multi-selected notes, the notes appear in wrong order
in the target folder. Root cause: move_note_to_folder() is called once per
note with datetime.now() as enc_modified_at; consecutive calls occur within
milliseconds and the OS clock can be non-monotonic, so timestamps may not
respect visual order. After ORDER BY enc_modified_at DESC the notes appear
scrambled.

Fix: in _handle_note_drop(), iterate src_note_ids in REVERSE so the visually
first note is moved last (gets the highest timestamp) and therefore sorts
first in ORDER BY enc_modified_at DESC.

Complementary fix: _get_drag_source_data() must iterate selected_note_rows in
sorted ascending order so src_note_ids always reflects visual top-to-bottom
order, regardless of Python set iteration order.
"""

import sys
import os
import inspect
import types
import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from main_window import FolderListWidget


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_stub(note_ids):
    """
    Build a FolderListWidget-like stub for testing _handle_note_drop.
    note_ids: list of note IDs to be moved (in the order they should appear
              visually, i.e., index 0 = top of list).
    """
    stub = MagicMock()
    stub._drop_indicator_position = 'on'
    stub._drop_indicator_rect = MagicMock()
    stub._drop_target_item = MagicMock()
    stub._clear_drop_indicator = lambda: FolderListWidget._clear_drop_indicator(stub)
    stub._expand_folder_ancestors = MagicMock()
    stub.main_window.note_manager.move_note_to_folder = MagicMock()
    return stub


# ---------------------------------------------------------------------------
# Test: _get_drag_source_data iterates selected_note_rows sorted
# ---------------------------------------------------------------------------

class TestGetDragSourceDataSortsRows:
    """
    _get_drag_source_data must iterate selected_note_rows in sorted order so
    that src_note_ids reflects the visual top-to-bottom note order regardless
    of Python set iteration order.
    """

    def test_source_iterates_sorted_rows(self):
        """
        The source of _get_drag_source_data must sort selected_note_rows.
        Before the fix: `for row in self.main_window.selected_note_rows`
        iterates a set with undefined order.
        After the fix: `for row in sorted(self.main_window.selected_note_rows)`
        """
        src = inspect.getsource(FolderListWidget._get_drag_source_data)
        assert 'sorted(self.main_window.selected_note_rows)' in src or \
               'sorted(' in src, (
            "_get_drag_source_data does not sort selected_note_rows. "
            "Set iteration order is undefined — the note IDs passed to "
            "_handle_note_drop must be in visual (row-ascending) order. "
            "Fix: use `for row in sorted(self.main_window.selected_note_rows)`."
        )


# ---------------------------------------------------------------------------
# Test: _handle_note_drop iterates in reverse to preserve visual order
# ---------------------------------------------------------------------------

class TestHandleNoteDropReverseOrder:
    """
    _handle_note_drop must call move_note_to_folder in REVERSE order so that
    the visually-first note receives the highest enc_modified_at timestamp and
    appears first under ORDER BY enc_modified_at DESC.
    """

    def test_move_calls_are_in_reverse_visual_order(self):
        """
        Given src_note_ids = ['id_top', 'id_mid', 'id_bot'] (visual order),
        move_note_to_folder must be called as: id_bot first, id_top last.
        This ensures id_top gets the latest timestamp and sorts first.
        """
        note_ids = ['id_top', 'id_mid', 'id_bot']
        stub = _make_stub(note_ids)

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, note_ids, 'folder-x', 0)

        mock_move = stub.main_window.note_manager.move_note_to_folder
        actual_order = [c.args[0] for c in mock_move.call_args_list]
        expected_order = ['id_bot', 'id_mid', 'id_top']  # reversed

        assert actual_order == expected_order, (
            f"move_note_to_folder call order was {actual_order!r}, "
            f"expected reversed order {expected_order!r}. "
            "The visually-first note must be moved last so it receives the "
            "highest enc_modified_at timestamp and appears first in the list."
        )

    def test_all_notes_are_moved(self):
        """All notes in src_note_ids must be moved regardless of order."""
        note_ids = ['id_a', 'id_b', 'id_c']
        stub = _make_stub(note_ids)

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, note_ids, 'folder-x', 0)

        mock_move = stub.main_window.note_manager.move_note_to_folder
        moved_ids = {c.args[0] for c in mock_move.call_args_list}
        assert moved_ids == set(note_ids), (
            f"Expected all notes {set(note_ids)!r} to be moved, "
            f"but got {moved_ids!r}."
        )

    def test_single_note_drag_unaffected(self):
        """Single-note drag still works correctly."""
        note_ids = ['id_only']
        stub = _make_stub(note_ids)

        with patch('main_window.QTimer'):
            FolderListWidget._handle_note_drop(stub, note_ids, 'folder-x', 0)

        mock_move = stub.main_window.note_manager.move_note_to_folder
        assert mock_move.call_count == 1
        assert mock_move.call_args.args[0] == 'id_only'

    def test_source_uses_reversed(self):
        """
        The source of _handle_note_drop must reference reversed() or iterate
        in reverse to guarantee timestamp ordering.
        Before the fix: `for note_id in src_note_ids` (forward order).
        After the fix:  `for note_id in reversed(src_note_ids)`.
        """
        src = inspect.getsource(FolderListWidget._handle_note_drop)
        assert 'reversed(' in src, (
            "_handle_note_drop does not use reversed(src_note_ids). "
            "Forward iteration means the visually-last note gets the highest "
            "timestamp and incorrectly appears first in ORDER BY enc_modified_at DESC. "
            "Fix: `for note_id in reversed(src_note_ids):`"
        )
