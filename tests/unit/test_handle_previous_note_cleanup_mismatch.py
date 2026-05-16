#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for _handle_previous_note_cleanup when current_note_id != prev_note_id.

Bug: during a multi-select drag, mousePressEvent loads the drag-source note into
the editor, changing current_note_id.  After the drag completes, the folder view
is refreshed and _clear_note_list_widgets fires
on_note_selected(current=None, previous=item_for_prev_note).
_handle_previous_note_cleanup then calls save_current_note(note_id=prev_note_id)
even though the editor now holds a DIFFERENT note's content, corrupting prev_note_id.

Fix: when current_note_id != prev_note_id, skip the save entirely (return early).
The editor's content belongs to current_note_id, which was already saved by
on_folder_changed before the list was cleared.
"""

import sys
import os
import inspect
import pytest
from unittest.mock import MagicMock, patch, call
from PyQt6.QtCore import Qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from main_window import MainWindow


# ---------------------------------------------------------------------------
# Helper: build a minimal MainWindow stub for _handle_previous_note_cleanup
# ---------------------------------------------------------------------------

def _make_stub(current_note_id, prev_note_id):
    """
    Build a MainWindow-like stub.
    current_note_id: what _get_last_note_for_current_view() returns (editor's live note)
    prev_note_id:    what previous_item.data(UserRole) returns (item being deselected)
    """
    stub = MagicMock(spec=MainWindow)

    # previous_item mock
    prev_item = MagicMock()
    prev_item.data.return_value = prev_note_id

    stub._get_last_note_for_current_view.return_value = current_note_id
    stub._update_item_widget_selection = MagicMock()
    stub.save_current_note = MagicMock()
    stub._cleanup_note_attachment_trash = MagicMock()

    return stub, prev_item


# ---------------------------------------------------------------------------
# Test: mismatch → save must be SKIPPED
# ---------------------------------------------------------------------------

class TestHandlePreviousNoteCleanupMismatch:
    """
    When current_note_id != prev_note_id, _handle_previous_note_cleanup must
    NOT call save_current_note at all.  The editor's content belongs to
    current_note_id (already saved by on_folder_changed), not to prev_note_id.
    Saving anyway would overwrite prev_note_id with the wrong content.
    """

    def test_save_skipped_when_note_ids_mismatch(self):
        """
        Given:
          current_note_id = '1b690a10'  (drag-source note loaded into editor)
          prev_note_id    = '368c251d'  (note that was displayed before drag)
        Expect: save_current_note is NOT called (skip to avoid corruption).
        """
        stub, prev_item = _make_stub(
            current_note_id='1b690a10',
            prev_note_id='368c251d',
        )

        MainWindow._handle_previous_note_cleanup(stub, prev_item)

        stub.save_current_note.assert_not_called(), (
            "save_current_note must NOT be called when current_note_id != prev_note_id. "
            "The editor holds content for '1b690a10'; saving it under '368c251d' corrupts "
            "the note that was previously displayed."
        )

    def test_attachment_cleanup_skipped_when_note_ids_mismatch(self):
        """
        When IDs mismatch the function returns early, so attachment cleanup must
        also be skipped (it could trigger side effects on the wrong note).
        """
        stub, prev_item = _make_stub(
            current_note_id='1b690a10',
            prev_note_id='368c251d',
        )

        MainWindow._handle_previous_note_cleanup(stub, prev_item)

        stub._cleanup_note_attachment_trash.assert_not_called(), (
            "_cleanup_note_attachment_trash must NOT be called when IDs mismatch — "
            "the early return should prevent it."
        )


# ---------------------------------------------------------------------------
# Test: match → save must still happen (no regression)
# ---------------------------------------------------------------------------

class TestHandlePreviousNoteCleanupMatch:
    """
    When current_note_id == prev_note_id (the normal case), save_current_note
    must still be called with prev_note_id.
    """

    def test_save_called_when_note_ids_match(self):
        """Normal case: IDs match → save proceeds."""
        stub, prev_item = _make_stub(
            current_note_id='abc123',
            prev_note_id='abc123',
        )

        MainWindow._handle_previous_note_cleanup(stub, prev_item)

        stub.save_current_note.assert_called_once()
        call_kwargs = stub.save_current_note.call_args
        # note_id must be prev_note_id (passed explicitly)
        assert call_kwargs.kwargs.get('note_id') == 'abc123' or \
               (call_kwargs.args and call_kwargs.args[0] == 'abc123'), (
            f"save_current_note must be called with note_id='abc123', "
            f"got args={call_kwargs.args!r} kwargs={call_kwargs.kwargs!r}"
        )

    def test_attachment_cleanup_called_when_ids_match(self):
        """Normal case: attachment cleanup runs after save."""
        stub, prev_item = _make_stub(
            current_note_id='abc123',
            prev_note_id='abc123',
        )

        MainWindow._handle_previous_note_cleanup(stub, prev_item)

        stub._cleanup_note_attachment_trash.assert_called_once_with('abc123')

    def test_no_previous_item_skips_everything(self):
        """previous_item=None → nothing should happen (existing guard)."""
        stub, _ = _make_stub(current_note_id='abc123', prev_note_id='abc123')

        MainWindow._handle_previous_note_cleanup(stub, None)

        stub.save_current_note.assert_not_called()
        stub._cleanup_note_attachment_trash.assert_not_called()


# ---------------------------------------------------------------------------
# Source inspection: verify early-return is present in the implementation
# ---------------------------------------------------------------------------

class TestHandlePreviousNoteCleanupSourceGuard:
    """
    The source of _handle_previous_note_cleanup must contain an early return
    when current_note_id != prev_note_id so the guard is unconditional.
    """

    def test_source_contains_early_return_on_mismatch(self):
        """
        Before the fix: the mismatch branch logs a warning but still calls
        save_current_note.  After the fix: the branch returns early.
        Verified by checking that 'return' appears after the mismatch condition.
        """
        src = inspect.getsource(MainWindow._handle_previous_note_cleanup)

        # Both the condition and an early return must be present
        assert 'current_note_id != prev_note_id' in src, (
            "_handle_previous_note_cleanup must still check "
            "`current_note_id != prev_note_id`."
        )
        # The simplest proxy: 'return' appears after the mismatch check.
        # We verify by finding the mismatch block and checking 'return' follows it.
        mismatch_pos = src.index('current_note_id != prev_note_id')
        rest = src[mismatch_pos:]
        assert 'return' in rest, (
            "_handle_previous_note_cleanup does not return early when "
            "current_note_id != prev_note_id.  Add `return` after the warning log "
            "to prevent saving the wrong note's content into prev_note_id."
        )
