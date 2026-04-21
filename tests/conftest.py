"""
Shared pytest fixtures for unit and integration tests.
All fixtures use tmp_path so real user data is never touched.
"""
import os
import sys
import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication


# ── Qt Application (one per session) ──────────────────────────────────────────
@pytest.fixture(scope="session")
def qt_app():
    """Single QApplication instance for the whole test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── Isolated EncryptionManager ─────────────────────────────────────────────────
@pytest.fixture
def isolated_encryption_manager(tmp_path, monkeypatch):
    """
    EncryptionManager that writes to tmp_path instead of
    ~/Library/Group Containers/group.com.encnotes/.
    Keyring is mocked so system keychain is never touched.
    """
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))

    # Mock keyring so tests don't touch macOS Keychain
    fake_keyring: dict = {}

    def fake_set_password(service, username, password):
        fake_keyring[(service, username)] = password

    def fake_get_password(service, username):
        return fake_keyring.get((service, username))

    def fake_delete_password(service, username):
        fake_keyring.pop((service, username), None)

    with patch("keyring.set_password", side_effect=fake_set_password), \
         patch("keyring.get_password", side_effect=fake_get_password), \
         patch("keyring.delete_password", side_effect=fake_delete_password):
        from encryption_manager import EncryptionManager
        manager = EncryptionManager()
        yield manager


# ── Isolated NoteManager ───────────────────────────────────────────────────────
@pytest.fixture
def isolated_note_manager(tmp_path, monkeypatch):
    """
    NoteManager that uses a fresh SQLite DB in tmp_path.
    Encryption is mocked to return plaintext (encryption correctness
    is tested separately in test_encryption_manager.py).
    """
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))

    fake_keyring: dict = {}

    def fake_set_password(service, username, password):
        fake_keyring[(service, username)] = password

    def fake_get_password(service, username):
        return fake_keyring.get((service, username))

    def fake_delete_password(service, username):
        fake_keyring.pop((service, username), None)

    with patch("keyring.set_password", side_effect=fake_set_password), \
         patch("keyring.get_password", side_effect=fake_get_password), \
         patch("keyring.delete_password", side_effect=fake_delete_password):
        from note_manager import NoteManager
        manager = NoteManager()
        yield manager
        manager.close()
