"""Unit tests for NoteManager — CRUD, folders, tags, trash."""
import pytest


# ── Notes CRUD ─────────────────────────────────────────────────────────────────

def test_create_note_returns_id(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Test Title", "Test Content")
    assert isinstance(note_id, str) and len(note_id) > 0


def test_get_note_returns_correct_data(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Hello", "World")
    note = isolated_note_manager.get_note(note_id)
    assert note["title"] == "Hello"


def test_update_note_changes_title(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Old", "Content")
    isolated_note_manager.update_note(note_id, title="New")
    note = isolated_note_manager.get_note(note_id)
    assert note["title"] == "New"


def test_delete_note_moves_to_trash(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Trash Me", "bye")
    isolated_note_manager.delete_note(note_id)
    deleted = isolated_note_manager.get_deleted_notes()
    ids = [n["id"] for n in deleted]
    assert note_id in ids


def test_restore_note_removes_from_trash(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Restore", "me")
    isolated_note_manager.delete_note(note_id)
    isolated_note_manager.restore_note(note_id)
    deleted = isolated_note_manager.get_deleted_notes()
    ids = [n["id"] for n in deleted]
    assert note_id not in ids


def test_permanently_delete_note(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Gone", "forever")
    isolated_note_manager.delete_note(note_id)
    isolated_note_manager.permanently_delete_note(note_id)
    note = isolated_note_manager.get_note(note_id)
    assert note is None


# ── Folders ────────────────────────────────────────────────────────────────────

def test_create_folder(isolated_note_manager):
    folder_id = isolated_note_manager.create_folder("Work")
    folder = isolated_note_manager.get_folder(folder_id)
    assert folder["name"] == "Work"


def test_rename_folder(isolated_note_manager):
    folder_id = isolated_note_manager.create_folder("Old Name")
    isolated_note_manager.update_folder(folder_id, "New Name")
    folder = isolated_note_manager.get_folder(folder_id)
    assert folder["name"] == "New Name"


def test_delete_folder(isolated_note_manager):
    folder_id = isolated_note_manager.create_folder("To Delete")
    isolated_note_manager.delete_folder(folder_id)
    folder = isolated_note_manager.get_folder(folder_id)
    assert folder is None


def test_notes_by_folder(isolated_note_manager):
    folder_id = isolated_note_manager.create_folder("Work")
    note_id = isolated_note_manager.create_note("Work Note", "", folder_id=folder_id)
    notes = isolated_note_manager.get_notes_by_folder(folder_id)
    ids = [n["id"] for n in notes]
    assert note_id in ids


# ── Tags ───────────────────────────────────────────────────────────────────────

def test_create_tag(isolated_note_manager):
    tag_id = isolated_note_manager.create_tag("Python")
    tag = isolated_note_manager.get_tag(tag_id)
    assert tag["name"] == "Python"


def test_add_tag_to_note(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Tagged Note", "")
    tag_id = isolated_note_manager.create_tag("Python")
    isolated_note_manager.add_tag_to_note(note_id, tag_id)
    tags = isolated_note_manager.get_note_tags(note_id)
    tag_names = [t["name"] for t in tags]
    assert "Python" in tag_names


def test_filter_notes_by_tag(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Filtered", "")
    tag_id = isolated_note_manager.create_tag("FilterTag")
    isolated_note_manager.add_tag_to_note(note_id, tag_id)
    notes = isolated_note_manager.get_notes_by_tag(tag_id)
    ids = [n["id"] for n in notes]
    assert note_id in ids


def test_remove_tag_from_note(isolated_note_manager):
    note_id = isolated_note_manager.create_note("Note", "")
    tag_id = isolated_note_manager.create_tag("TempTag")
    isolated_note_manager.add_tag_to_note(note_id, tag_id)
    isolated_note_manager.remove_tag_from_note(note_id, tag_id)
    tags = isolated_note_manager.get_note_tags(note_id)
    assert tags == []
