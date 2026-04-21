"""Integration tests for tag creation and filtering."""
import pytest
from unittest.mock import patch


@pytest.fixture
def note_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))
    fake_keyring: dict = {}
    with patch("keyring.set_password", side_effect=lambda s, u, p: fake_keyring.__setitem__((s, u), p)), \
         patch("keyring.get_password", side_effect=lambda s, u: fake_keyring.get((s, u))), \
         patch("keyring.delete_password", side_effect=lambda s, u: fake_keyring.pop((s, u), None)):
        from note_manager import NoteManager
        mgr = NoteManager()
        yield mgr
        mgr.close()


def test_create_tag_and_assign(note_manager):
    tag_id = note_manager.create_tag("pytest")
    note_id = note_manager.create_note("Tagged", "")
    note_manager.add_tag_to_note(note_id, tag_id)
    tags = note_manager.get_note_tags(note_id)
    assert any(t["name"] == "pytest" for t in tags)


def test_filter_by_tag_shows_only_tagged_notes(note_manager):
    tag_id = note_manager.create_tag("visible")
    note_id = note_manager.create_note("Visible Note", "")
    _ = note_manager.create_note("Invisible Note", "")  # not tagged
    note_manager.add_tag_to_note(note_id, tag_id)

    results = note_manager.get_notes_by_tag(tag_id)
    ids = [n["id"] for n in results]
    assert note_id in ids
    assert len(results) == 1
