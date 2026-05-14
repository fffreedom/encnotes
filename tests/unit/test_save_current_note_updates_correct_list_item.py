#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for save_current_note updating the correct note list item.

Bug: save_current_note(note_id=X) saves note X to the DB correctly, but then
calls _update_note_list_display(title, plain_text) which uses
_get_current_note_id() to find the list item.  If _get_current_note_id()
returns a different note Y at that moment (e.g. because a folder change
has already moved the view), note Y's list item gets updated with X's
title — visible as a wrong title in the sidebar.

This happens during drag-and-drop: after a drop, _delayed_refresh_note_ui
triggers load_folders() → on_folder_changed → load_notes, which changes
_get_current_note_id() to point at the newly-selected note (Y).  Around
the same time, _handle_previous_note_cleanup calls
save_current_note(note_id=X), which tries to update the display.
Because _get_current_note_id() now returns Y, the wrong list item is updated.

Fix: _update_note_list_display must accept a note_id parameter and use it
(rather than calling _get_current_note_id()) when provided.
save_current_note must pass note_id through to _update_note_list_display.
"""

import sys
import os
import inspect
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from main_window import MainWindow


# ---------------------------------------------------------------------------
# Helper: build a minimal MainWindow stub for save_current_note
# ---------------------------------------------------------------------------

def _make_save_stub(note_id_to_save, current_note_id_at_call_time):
    """
    Build a MainWindow-like stub for testing save_current_note.

    note_id_to_save:             the note_id passed explicitly to save_current_note
    current_note_id_at_call_time: what _get_current_note_id() returns while saving
                                  (simulates the view having already moved to another note)
    """
    # Use MagicMock without spec so we can attach arbitrary attributes like 'editor'
    stub = MagicMock()
    # Manually restrict the key methods to their real spec for accuracy
    stub._editor_initialized = True
    stub._get_current_note_id.return_value = current_note_id_at_call_time

    # Simulate editor content belonging to note_id_to_save
    stub.editor.toHtml.return_value = "<p>Content of note A</p>"
    stub.editor.toPlainText.return_value = "Title A\nContent of note A"
    stub.editor.text_edit.textCursor.return_value.position.return_value = 0

    stub._extract_title_from_content.return_value = "Title A"
    stub.note_manager.update_note = MagicMock()
    stub._update_note_list_display = MagicMock()

    return stub


# ---------------------------------------------------------------------------
# Test: save_current_note passes note_id to _update_note_list_display
# ---------------------------------------------------------------------------

class TestSaveCurrentNoteUpdatesCorrectListItem:
    """
    save_current_note(note_id=X) must pass note_id=X to _update_note_list_display
    even when _get_current_note_id() returns a different note Y.
    """

    def test_update_display_called_with_explicit_note_id(self):
        """
        Given:
          - save_current_note called with note_id='note-A'
          - _get_current_note_id() returns 'note-B' (view has moved)
        Expect: _update_note_list_display called with note_id='note-A', NOT 'note-B'.
        """
        stub = _make_save_stub(
            note_id_to_save='note-A',
            current_note_id_at_call_time='note-B',
        )

        MainWindow.save_current_note(stub, note_id='note-A')

        stub._update_note_list_display.assert_called_once()
        call_args = stub._update_note_list_display.call_args

        # note_id must be 'note-A', not 'note-B'
        passed_note_id = call_args.kwargs.get('note_id') or (
            call_args.args[2] if len(call_args.args) > 2 else None
        )
        assert passed_note_id == 'note-A', (
            f"_update_note_list_display must be called with note_id='note-A' "
            f"(the note being saved), but got note_id={passed_note_id!r}. "
            f"Full call: args={call_args.args!r} kwargs={call_args.kwargs!r}. "
            f"This bug causes note-B's title to be overwritten with note-A's title."
        )

    def test_update_display_not_called_with_current_note_id_when_different(self):
        """
        When note_id='note-A' but _get_current_note_id() returns 'note-B',
        _update_note_list_display must NOT receive 'note-B' as its note_id.
        """
        stub = _make_save_stub(
            note_id_to_save='note-A',
            current_note_id_at_call_time='note-B',
        )

        MainWindow.save_current_note(stub, note_id='note-A')

        stub._update_note_list_display.assert_called_once()
        call_args = stub._update_note_list_display.call_args
        passed_note_id = call_args.kwargs.get('note_id') or (
            call_args.args[2] if len(call_args.args) > 2 else None
        )
        assert passed_note_id != 'note-B', (
            f"_update_note_list_display received note_id='note-B' (the view's current note) "
            f"instead of 'note-A' (the note being saved). This corrupts note-B's display."
        )


# ---------------------------------------------------------------------------
# Test: _update_note_list_display uses provided note_id, not _get_current_note_id
# ---------------------------------------------------------------------------

class TestUpdateNoteListDisplayUsesNoteId:
    """
    _update_note_list_display(title, plain_text, note_id=X) must call
    _find_note_list_item_by_id(X), not _find_note_list_item_by_id(_get_current_note_id()).
    """

    def _make_display_stub(self, get_current_returns, note_id_arg):
        stub = MagicMock(spec=MainWindow)
        stub._get_current_note_id.return_value = get_current_returns
        stub._find_note_list_item_by_id.return_value = (None, None, None)
        return stub

    def test_find_item_called_with_provided_note_id(self):
        """
        When note_id='note-A' is passed, _find_note_list_item_by_id('note-A') is called.
        """
        stub = self._make_display_stub(
            get_current_returns='note-B',
            note_id_arg='note-A',
        )

        MainWindow._update_note_list_display(stub, "Title A", "Title A\nbody", note_id='note-A')

        stub._find_note_list_item_by_id.assert_called_once_with('note-A')

    def test_find_item_not_called_with_current_note_id_when_note_id_provided(self):
        """
        When note_id='note-A' is provided, _find_note_list_item_by_id must NOT
        be called with 'note-B' (the value from _get_current_note_id).
        """
        stub = self._make_display_stub(
            get_current_returns='note-B',
            note_id_arg='note-A',
        )

        MainWindow._update_note_list_display(stub, "Title A", "Title A\nbody", note_id='note-A')

        called_with = stub._find_note_list_item_by_id.call_args.args[0]
        assert called_with != 'note-B', (
            f"_find_note_list_item_by_id called with 'note-B' (current note) "
            f"instead of 'note-A' (provided note_id). "
            f"This means the wrong list item's title would be updated."
        )

    def test_falls_back_to_get_current_note_id_when_note_id_not_provided(self):
        """
        When note_id is not provided (legacy call site), fall back to _get_current_note_id().
        """
        stub = self._make_display_stub(
            get_current_returns='note-B',
            note_id_arg=None,
        )

        MainWindow._update_note_list_display(stub, "Title B", "Title B\nbody")

        stub._find_note_list_item_by_id.assert_called_once_with('note-B')


# ---------------------------------------------------------------------------
# Source inspection: verify the fix is in the implementation
# ---------------------------------------------------------------------------

class TestUpdateNoteListDisplaySourceAcceptsNoteId:
    """
    The signature of _update_note_list_display must accept a note_id parameter.
    """

    def test_signature_has_note_id_parameter(self):
        sig = inspect.signature(MainWindow._update_note_list_display)
        assert 'note_id' in sig.parameters, (
            "_update_note_list_display must accept a 'note_id' parameter. "
            "Without it, save_current_note cannot pass the correct note_id through."
        )

    def test_save_current_note_passes_note_id_to_display(self):
        """
        The source of save_current_note must contain a call to
        _update_note_list_display that passes note_id.
        """
        src = inspect.getsource(MainWindow.save_current_note)
        assert 'note_id' in src.split('_update_note_list_display')[1].split('\n')[0], (
            "save_current_note must pass note_id to _update_note_list_display. "
            "Current call `self._update_note_list_display(title, plain_text)` does not pass note_id, "
            "causing the wrong list item to be updated when _get_current_note_id() has changed."
        )
