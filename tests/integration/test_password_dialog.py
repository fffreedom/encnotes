"""Integration tests for password dialogs using pytest-qt."""
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt


@pytest.fixture
def mock_encryption_manager():
    """Minimal mock of EncryptionManager for dialog tests."""
    mgr = MagicMock()
    mgr.is_password_set.return_value = False
    mgr.setup_password.return_value = (True, "ok")
    mgr.verify_password.return_value = (True, "ok")
    mgr.try_auto_unlock.return_value = False
    return mgr


def test_setup_password_dialog_shows(qtbot, mock_encryption_manager):
    """SetupPasswordDialog should be visible when opened."""
    from password_dialog import SetupPasswordDialog
    dialog = SetupPasswordDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.isVisible()


def test_unlock_dialog_shows(qtbot):
    """UnlockDialog should be visible when opened."""
    from password_dialog import UnlockDialog
    dialog = UnlockDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.isVisible()


def test_unlock_dialog_exposes_password(qtbot):
    """get_password() should return whatever was typed in the field after accept."""
    from password_dialog import UnlockDialog
    dialog = UnlockDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Find the password field and type into it
    fields = dialog.findChildren(QLineEdit)
    assert len(fields) >= 1
    qtbot.keyClicks(fields[0], "MySecret1")

    # accept() validates non-empty input, stores self.password, then closes.
    # Patch QMessageBox so no real dialog appears, and call accept directly.
    with patch("password_dialog.QMessageBox"):
        dialog.accept()

    assert dialog.get_password() == "MySecret1"
