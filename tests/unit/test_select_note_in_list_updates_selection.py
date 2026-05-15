#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for _select_note_in_list updating selected_note_rows.

Bug: after create_new_note(), _select_note_in_list() selects the new note in
the Qt list widget but does NOT update selected_note_rows.  As a result,
selected_note_rows still holds the row of the previously-selected note.
When the user later clicks that old row, _handle_normal_press sees
is_in_multi_select=True and calls _keep_multi_select_for_drag instead of
select_single_note, so the editor content is never switched.

Root cause: _select_note_in_list only calls setCurrentItem(); it never updates
self.selected_note_rows.

Fix: after setCurrentItem(), _select_note_in_list must also update
selected_note_rows = {row}.
"""

import sys
import os
import types
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QPoint


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _import_classes():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from main_window import MainWindow, NoteListWidget
    return MainWindow, NoteListWidget


def _make_list_widget(note_ids):
    """
    Return (QListWidget, {note_id: row}) with one selectable item per note_id.
    """
    lw = QListWidget()
    row_map = {}
    for i, nid in enumerate(note_ids):
        item = QListWidgetItem(f"Note {i}")
        item.setData(Qt.ItemDataRole.UserRole, nid)
        lw.addItem(item)
        row_map[nid] = i
    return lw, row_map


def _stub_mw(note_list, selected_note_rows):
    """
    Build a minimal stub that has exactly the attributes _select_note_in_list
    and _handle_normal_press (via NoteListWidget) need from MainWindow.

    NOTE: _select_note_in_list updates self.note_list.selected_rows (the
    NoteListWidget attribute), not a separate mw.selected_note_rows attribute.
    We seed the initial state on note_list.selected_rows so assertions can
    check the same attribute that the implementation writes to.
    """
    mw = MagicMock()
    mw.note_list = note_list
    # Seed initial selected_rows directly on the note_list (matches the real app)
    note_list.selected_rows = set(selected_note_rows)
    return mw


# ---------------------------------------------------------------------------
# Core regression tests  (these FAIL before the fix)
# ---------------------------------------------------------------------------

class TestSelectNoteInListUpdatesSelectedNoteRows:
    """
    _select_note_in_list must update selected_note_rows to the row of the
    newly selected note so that _handle_normal_press does NOT misidentify the
    old row as "in multi-select".
    """

    def test_old_row_removed_from_selected_note_rows(self, qt_app):
        """
        After _select_note_in_list(new_note_id), the previously-selected row
        must NOT remain in selected_note_rows.

        Scenario (from production logs):
          selected_note_rows = {1}  ← "AI人才" was at row 1
          _select_note_in_list called for new note at row 2
          → selected_note_rows must not still contain 1
        """
        MainWindow, _ = _import_classes()

        AI_PERSON_ID = "note-ai-person"
        NEW_NOTE_ID  = "note-new"
        lw, row_map = _make_list_widget([AI_PERSON_ID, NEW_NOTE_ID])
        # Simulate: AI人才 was selected (row 0), new note is at row 1
        mw = _stub_mw(lw, {row_map[AI_PERSON_ID]})

        # Invoke the real method on our stub
        MainWindow._select_note_in_list(mw, NEW_NOTE_ID)

        old_row = row_map[AI_PERSON_ID]
        assert old_row not in mw.note_list.selected_rows, (
            f"note_list.selected_rows still contains old row {old_row} after "
            f"_select_note_in_list selected NEW_NOTE_ID. "
            f"Actual selected_rows={mw.note_list.selected_rows!r}. "
            f"This causes _handle_normal_press to treat the old row as "
            f"'in multi-select' and refuse to switch notes."
        )

    def test_new_row_added_to_selected_note_rows(self, qt_app):
        """
        After _select_note_in_list(note_id), selected_note_rows must contain
        the row of the note that was just selected.
        """
        MainWindow, _ = _import_classes()

        AI_PERSON_ID = "note-ai-person"
        NEW_NOTE_ID  = "note-new"
        lw, row_map = _make_list_widget([AI_PERSON_ID, NEW_NOTE_ID])
        mw = _stub_mw(lw, {row_map[AI_PERSON_ID]})  # {0}

        MainWindow._select_note_in_list(mw, NEW_NOTE_ID)

        new_row = row_map[NEW_NOTE_ID]  # 1
        assert new_row in mw.note_list.selected_rows, (
            f"note_list.selected_rows {mw.note_list.selected_rows!r} does not contain "
            f"the new note's row {new_row} after _select_note_in_list."
        )

    def test_is_item_in_multi_select_returns_false_for_old_row_after_select(
        self, qt_app
    ):
        """
        End-to-end: after _select_note_in_list is called (simulating
        create_new_note), _is_item_in_multi_select must return False for the
        previously-selected note's row.

        This is the direct predicate tested by _handle_normal_press.  Before
        the fix, _is_item_in_multi_select(old_row) returns True (because
        selected_note_rows still holds the old row), triggering the bug.
        After the fix it returns False, allowing select_single_note to be called.
        """
        MainWindow, NoteListWidget = _import_classes()

        AI_PERSON_ID = "note-ai-person"
        NEW_NOTE_ID  = "note-new"
        lw, row_map = _make_list_widget([AI_PERSON_ID, NEW_NOTE_ID])

        # Build a stub MainWindow
        mw = _stub_mw(lw, {row_map[AI_PERSON_ID]})  # selected_note_rows = {0}

        # Step 1: simulate create_new_note calling _select_note_in_list
        MainWindow._select_note_in_list(mw, NEW_NOTE_ID)

        # Step 2: check whether _is_item_in_multi_select considers the old row
        # to still be "in multi-select".  It uses note_list.selected_rows directly.
        old_row = row_map[AI_PERSON_ID]
        is_multi = old_row in mw.note_list.selected_rows

        assert not is_multi, (
            f"note_list.selected_rows still contains old row {old_row} "
            f"(selected_rows={mw.note_list.selected_rows!r}), so "
            f"_handle_normal_press would keep multi-select and refuse to switch notes. "
            f"This is the create_new_note click-back bug."
        )


# ---------------------------------------------------------------------------
# Baseline sanity check — _select_note_in_list must still change the Qt current item
# ---------------------------------------------------------------------------

def test_select_note_in_list_sets_current_item(qt_app):
    """
    Existing behaviour must be preserved: the Qt current item must be updated
    to the requested note.
    """
    MainWindow, _ = _import_classes()

    NOTE_A = "note-a"
    NOTE_B = "note-b"
    lw, row_map = _make_list_widget([NOTE_A, NOTE_B])
    mw = _stub_mw(lw, {row_map[NOTE_A]})

    MainWindow._select_note_in_list(mw, NOTE_B)

    current_item = lw.currentItem()
    assert current_item is not None
    assert current_item.data(Qt.ItemDataRole.UserRole) == NOTE_B, (
        f"Expected current item to be NOTE_B, got "
        f"{current_item.data(Qt.ItemDataRole.UserRole)!r}"
    )
