"""Unit tests for AttachmentManager."""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def attachment_manager(tmp_path, monkeypatch):
    """AttachmentManager using tmp_path for all storage."""
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))
    fake_keyring: dict = {}
    with patch("keyring.set_password", side_effect=lambda s, u, p: fake_keyring.__setitem__((s, u), p)), \
         patch("keyring.get_password", side_effect=lambda s, u: fake_keyring.get((s, u))), \
         patch("keyring.delete_password", side_effect=lambda s, u: fake_keyring.pop((s, u), None)):
        from encryption_manager import EncryptionManager
        from attachment_manager import AttachmentManager
        enc = EncryptionManager()
        mgr = AttachmentManager(enc)

        # Redirect storage paths so tests never touch ~/Library/...
        att_dir = tmp_path / "attachments"
        att_dir.mkdir(parents=True, exist_ok=True)
        trash_dir = att_dir / "_trash"
        trash_dir.mkdir(parents=True, exist_ok=True)

        mgr.attachments_dir = att_dir
        mgr.attachments_trash_dir = trash_dir
        mgr.metadata_file = att_dir / "metadata.json"
        mgr.metadata = {}  # fresh metadata

        yield mgr


@pytest.fixture
def sample_file(tmp_path):
    """A small temporary file to use as an attachment."""
    f = tmp_path / "sample.txt"
    f.write_text("hello attachment")
    return str(f)


def test_add_attachment(attachment_manager, sample_file):
    success, msg, att_id = attachment_manager.add_attachment(sample_file, note_id="note-001")
    assert success is True
    assert att_id is not None


def test_get_attachment_info(attachment_manager, sample_file):
    _, _, att_id = attachment_manager.add_attachment(sample_file, note_id="note-001")
    info = attachment_manager.get_attachment_info(att_id)
    assert info is not None
    assert "sample.txt" in info.get("original_name", "")


def test_delete_attachment(attachment_manager, sample_file):
    _, _, att_id = attachment_manager.add_attachment(sample_file, note_id="note-001")
    result = attachment_manager.defer_delete_attachment(att_id, note_id="note-001")
    assert result[0] is True
