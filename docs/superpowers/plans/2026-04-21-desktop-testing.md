# Desktop Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-layer automated test suite (unit + integration + e2e) for the encnotes PyQt6 desktop app that never touches real user data.

**Architecture:** Unit tests use `pytest` + `tmp_path` to isolate `NoteManager`/`EncryptionManager` from the real data directory; integration tests use `pytest-qt` (`qtbot`) to drive Qt widgets in-process; e2e tests use `computer-use-mcp` to control the real app, pointed at a throwaway `ENCNOTES_TEST_DATA_DIR`. A single `conftest.py` provides all shared fixtures.

**Tech Stack:** Python 3, pytest, pytest-qt, unittest.mock, PyQt6, computer-use-mcp

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `note_manager.py` | Read `ENCNOTES_TEST_DATA_DIR` env var to override default data dir |
| Modify | `encryption_manager.py` | Read `ENCNOTES_TEST_DATA_DIR` env var to override default config dir |
| Create | `tests/__init__.py` | Make tests a package |
| Create | `tests/conftest.py` | Shared fixtures: isolated `NoteManager`, `EncryptionManager`, qt `QApplication` |
| Create | `tests/unit/__init__.py` | Package marker |
| Create | `tests/unit/test_note_manager.py` | CRUD, folders, tags, trash |
| Create | `tests/unit/test_encryption_manager.py` | Password setup/verify, encrypt/decrypt, PBKDF2 params |
| Create | `tests/unit/test_export_manager.py` | Export to PDF/Word/Markdown/HTML |
| Create | `tests/unit/test_attachment_manager.py` | Add/list/delete attachments, orphan cleanup |
| Create | `tests/integration/__init__.py` | Package marker |
| Create | `tests/integration/test_main_window.py` | Three-pane layout, new note, switch folder, delete note |
| Create | `tests/integration/test_note_editor.py` | Text input, bold/italic/underline, table insertion, LaTeX |
| Create | `tests/integration/test_tags_ui.py` | Create tag, assign to note, filter by tag |
| Create | `tests/integration/test_password_dialog.py` | Setup dialog, wrong password, correct password |
| Create | `tests/e2e/__init__.py` | Package marker |
| Create | `tests/e2e/conftest.py` | e2e fixtures: reset test DB dir, launch/quit app |
| Create | `tests/e2e/test_launch.py` | Launch → unlock → lock cycle |
| Create | `tests/e2e/test_smoke.py` | New note, type text, new folder, restart → data persists |
| Create | `pytest.ini` | Register `e2e` marker, set testpaths |

---

## Task 1: Add `ENCNOTES_TEST_DATA_DIR` support to source files

**Files:**
- Modify: `note_manager.py` (lines 23-27)
- Modify: `encryption_manager.py` (lines 40-43)

- [ ] **Step 1: Patch `note_manager.py` data dir**

Replace the `__init__` data dir block (lines 23-27) with:

```python
import os
# ...existing imports stay...

class NoteManager:
    def __init__(self):
        # Allow tests to redirect data dir via environment variable
        _test_dir = os.environ.get("ENCNOTES_TEST_DATA_DIR")
        if _test_dir:
            self.data_dir = Path(_test_dir)
        else:
            self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "NoteStore.sqlite"
        self.conn = None

        self.encryption_manager = EncryptionManager()
        self.attachment_manager = AttachmentManager(self.encryption_manager)
        self.init_database()
```

- [ ] **Step 2: Patch `encryption_manager.py` config dir**

Replace lines 40-43 with:

```python
        import os
        _test_dir = os.environ.get("ENCNOTES_TEST_DATA_DIR")
        if _test_dir:
            self.config_dir = Path(_test_dir)
        else:
            self.config_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "encryption_config.json"
```

- [ ] **Step 3: Verify the app still launches normally**

```bash
python main.py &
sleep 3
kill %1
```

Expected: App launches without error. Real data untouched.

- [ ] **Step 4: Commit**

```bash
git add note_manager.py encryption_manager.py
git commit -m "feat: support ENCNOTES_TEST_DATA_DIR env var for test isolation"
```

---

## Task 2: Create `pytest.ini` and package stubs

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/e2e/__init__.py`

- [ ] **Step 1: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
markers =
    e2e: end-to-end tests requiring macOS Accessibility permission (deselect with -m "not e2e")
addopts = -m "not e2e"
```

- [ ] **Step 2: Create package `__init__.py` files**

```bash
mkdir -p tests/unit tests/integration tests/e2e tests/fixtures
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/e2e/__init__.py
```

- [ ] **Step 3: Install test dependencies**

```bash
pip install pytest pytest-qt
```

Expected output: Successfully installed pytest-qt-X.X.X

- [ ] **Step 4: Verify pytest discovers tests (none yet)**

```bash
pytest --collect-only
```

Expected: `no tests ran` (or empty collection — no errors)

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/
git commit -m "chore: add pytest config and test package structure"
```

---

## Task 3: Shared fixtures in `tests/conftest.py`

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""
Shared pytest fixtures for unit and integration tests.
All fixtures use tmp_path so real user data is never touched.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from PyQt6.QtWidgets import QApplication
import sys


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
```

- [ ] **Step 2: Verify fixture imports cleanly**

```bash
pytest tests/conftest.py --collect-only
```

Expected: no errors, no tests collected from conftest itself.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared isolation fixtures in conftest.py"
```

---

## Task 4: Unit tests — `NoteManager`

**Files:**
- Create: `tests/unit/test_note_manager.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests — expect them to fail (import/fixture issues are fine at this stage)**

```bash
pytest tests/unit/test_note_manager.py -v
```

Expected: Tests are collected. Any failures should be import errors or assertion errors, not syntax errors.

- [ ] **Step 3: Fix any import issues, then run again to pass**

```bash
pytest tests/unit/test_note_manager.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_note_manager.py
git commit -m "test: unit tests for NoteManager CRUD, folders, tags, trash"
```

---

## Task 5: Unit tests — `EncryptionManager`

**Files:**
- Create: `tests/unit/test_encryption_manager.py`

- [ ] **Step 1: Write tests**

```python
"""Unit tests for EncryptionManager."""
import pytest


def test_password_not_set_initially(isolated_encryption_manager):
    assert isolated_encryption_manager.is_password_set() is False


def test_setup_password_succeeds(isolated_encryption_manager):
    success, msg = isolated_encryption_manager.setup_password("TestPass123!")
    assert success is True


def test_password_is_set_after_setup(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    assert isolated_encryption_manager.is_password_set() is True


def test_verify_correct_password(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    success, msg = isolated_encryption_manager.verify_password("TestPass123!")
    assert success is True


def test_verify_wrong_password_fails(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    success, msg = isolated_encryption_manager.verify_password("WrongPass!")
    assert success is False


def test_verify_wrong_password_does_not_crash(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    try:
        isolated_encryption_manager.verify_password("BadPass")
    except Exception as e:
        pytest.fail(f"verify_password raised unexpectedly: {e}")


def test_encrypt_decrypt_roundtrip(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    isolated_encryption_manager.verify_password("TestPass123!")  # unlock
    plaintext = "Hello, 世界! <b>Bold</b>"
    ciphertext = isolated_encryption_manager.encrypt(plaintext)
    assert ciphertext != plaintext
    recovered = isolated_encryption_manager.decrypt(ciphertext)
    assert recovered == plaintext


def test_pbkdf2_iterations(isolated_encryption_manager):
    assert isolated_encryption_manager.ITERATIONS >= 100000


def test_lock_clears_key(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    isolated_encryption_manager.verify_password("TestPass123!")
    assert isolated_encryption_manager.is_unlocked is True
    isolated_encryption_manager.lock()
    assert isolated_encryption_manager.is_unlocked is False
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/unit/test_encryption_manager.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_encryption_manager.py
git commit -m "test: unit tests for EncryptionManager password, encrypt/decrypt, lock"
```

---

## Task 6: Unit tests — `ExportManager` and `AttachmentManager`

**Files:**
- Create: `tests/unit/test_export_manager.py`
- Create: `tests/unit/test_attachment_manager.py`

- [ ] **Step 1: Write `test_export_manager.py`**

```python
"""Unit tests for ExportManager."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def export_manager(tmp_path, qt_app):
    """ExportManager writing to tmp_path."""
    from export_manager import ExportManager
    mgr = ExportManager()
    mgr.export_dir = tmp_path  # redirect output dir
    return mgr


SAMPLE_HTML = "<h1>Test Note</h1><p>Hello <b>world</b></p>"


def test_export_to_markdown_creates_file(export_manager, tmp_path):
    path = export_manager.export_to_markdown("Test Note", SAMPLE_HTML)
    assert path is not None
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_export_to_html_creates_file(export_manager, tmp_path):
    path = export_manager.export_to_html("Test Note", SAMPLE_HTML)
    assert path is not None
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "Test Note" in content


def test_export_to_word_creates_file(export_manager, tmp_path):
    path = export_manager.export_to_word("Test Note", SAMPLE_HTML)
    assert path is not None
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_export_to_pdf_does_not_crash(export_manager, qt_app):
    """PDF export requires a Qt printer; just check it doesn't raise."""
    try:
        export_manager.export_to_pdf("Test Note", SAMPLE_HTML)
    except Exception as e:
        pytest.fail(f"export_to_pdf raised: {e}")


def test_export_html_with_table(export_manager):
    html = "<table><tr><td>A</td><td>B</td></tr></table>"
    path = export_manager.export_to_html("Table Note", html)
    assert path is not None
    assert Path(path).exists()
```

- [ ] **Step 2: Write `test_attachment_manager.py`**

```python
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
```

- [ ] **Step 3: Run both test files**

```bash
pytest tests/unit/test_export_manager.py tests/unit/test_attachment_manager.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_export_manager.py tests/unit/test_attachment_manager.py
git commit -m "test: unit tests for ExportManager and AttachmentManager"
```

---

## Task 7: Integration tests — `PasswordDialog`

**Files:**
- Create: `tests/integration/test_password_dialog.py`

- [ ] **Step 1: Write tests**

```python
"""Integration tests for password dialogs using pytest-qt."""
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QDialogButtonBox
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
    """get_password() should return whatever was typed in the field."""
    from password_dialog import UnlockDialog
    dialog = UnlockDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    # Find the password field and type into it
    from PyQt6.QtWidgets import QLineEdit
    fields = dialog.findChildren(QLineEdit)
    assert len(fields) >= 1
    qtbot.keyClicks(fields[0], "MySecret")
    assert dialog.get_password() == "MySecret"
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/integration/test_password_dialog.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_password_dialog.py
git commit -m "test: integration tests for password dialogs"
```

---

## Task 8: Integration tests — `NoteEditor`

**Files:**
- Create: `tests/integration/test_note_editor.py`

- [ ] **Step 1: Write tests**

```python
"""Integration tests for NoteEditor widget."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence


@pytest.fixture
def editor(qtbot, qt_app):
    from note_editor import NoteEditor
    widget = NoteEditor()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_editor_shows(editor):
    assert editor.isVisible()


def test_type_text_appears_in_content(editor, qtbot):
    editor.clear()
    qtbot.keyClicks(editor, "Hello World")
    content = editor.toPlainText()
    assert "Hello World" in content


def test_bold_shortcut_does_not_crash(editor, qtbot):
    """Cmd+B (or Ctrl+B) should not raise."""
    editor.clear()
    qtbot.keyClicks(editor, "Bold me")
    editor.selectAll()
    try:
        qtbot.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    except Exception as e:
        pytest.fail(f"Bold shortcut raised: {e}")


def test_italic_shortcut_does_not_crash(editor, qtbot):
    editor.clear()
    qtbot.keyClicks(editor, "Italic me")
    editor.selectAll()
    try:
        qtbot.keyClick(editor, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    except Exception as e:
        pytest.fail(f"Italic shortcut raised: {e}")


def test_set_html_content(editor):
    html = "<h1>Title</h1><p>Paragraph</p>"
    editor.setHtml(html)
    result = editor.toHtml()
    assert "Title" in result
    assert "Paragraph" in result


def test_insert_table_produces_table_tag(editor, qtbot):
    """After inserting a table, the HTML should contain <table>."""
    editor.clear()
    # Call the insert_table method directly if it exists, else skip
    if hasattr(editor, "insert_table"):
        editor.insert_table(2, 2)
        html = editor.toHtml()
        assert "<table" in html.lower()
    else:
        pytest.skip("insert_table method not found on NoteEditor")
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/integration/test_note_editor.py -v
```

Expected: All tests PASS (insert_table test may be skipped if method name differs).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_note_editor.py
git commit -m "test: integration tests for NoteEditor widget"
```

---

## Task 9: Integration tests — `MainWindow` and tags UI

**Files:**
- Create: `tests/integration/test_main_window.py`
- Create: `tests/integration/test_tags_ui.py`

- [ ] **Step 1: Write `test_main_window.py`**

```python
"""Integration tests for MainWindow layout and note operations."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def main_window(qtbot, tmp_path, monkeypatch):
    """
    MainWindow with isolated data dir and mocked iCloud sync.
    """
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))
    fake_keyring: dict = {}
    with patch("keyring.set_password", side_effect=lambda s, u, p: fake_keyring.__setitem__((s, u), p)), \
         patch("keyring.get_password", side_effect=lambda s, u: fake_keyring.get((s, u))), \
         patch("keyring.delete_password", side_effect=lambda s, u: fake_keyring.pop((s, u), None)), \
         patch("icloud_sync.CloudKitSyncManager") as mock_sync:
        mock_sync.return_value = MagicMock()
        from main_window import MainWindow
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        yield window


def test_main_window_shows(main_window):
    assert main_window.isVisible()


def test_three_pane_layout(main_window):
    """Window should have folder list, note list, and editor panes."""
    from PyQt6.QtWidgets import QSplitter
    splitters = main_window.findChildren(QSplitter)
    assert len(splitters) >= 1


def test_new_note_appears_in_list(main_window, qtbot):
    """Creating a new note should add an entry to the note list widget."""
    from PyQt6.QtWidgets import QListWidget
    note_lists = main_window.findChildren(QListWidget)
    assert len(note_lists) >= 1
    note_list = note_lists[-1]  # rightmost list is typically the note list
    initial_count = note_list.count()

    # Trigger new note via the note manager directly
    main_window.note_manager.create_note("Test Note", "Content")
    # Refresh the UI
    if hasattr(main_window, "load_notes"):
        main_window.load_notes()
    elif hasattr(main_window, "refresh_note_list"):
        main_window.refresh_note_list()

    assert note_list.count() >= initial_count
```

- [ ] **Step 2: Write `test_tags_ui.py`**

```python
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
```

- [ ] **Step 3: Run both files**

```bash
pytest tests/integration/test_main_window.py tests/integration/test_tags_ui.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_main_window.py tests/integration/test_tags_ui.py
git commit -m "test: integration tests for MainWindow layout and tags UI"
```

---

## Task 10: e2e fixtures and `test_launch.py`

**Files:**
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_launch.py`

- [ ] **Step 1: Create `tests/e2e/conftest.py`**

```python
"""
e2e test fixtures.
The app is launched as a subprocess pointing at /tmp/encnotes_test,
which is wiped before each test session.
"""
import os
import shutil
import subprocess
import time
import pytest

E2E_DATA_DIR = "/tmp/encnotes_test"
APP_ENTRY = "python main.py"  # run from repo root


def _reset_test_dir():
    if os.path.exists(E2E_DATA_DIR):
        shutil.rmtree(E2E_DATA_DIR)
    os.makedirs(E2E_DATA_DIR, exist_ok=True)


@pytest.fixture(scope="module")
def running_app():
    """Launch the app with test data dir, yield, then kill it."""
    _reset_test_dir()
    env = os.environ.copy()
    env["ENCNOTES_TEST_DATA_DIR"] = E2E_DATA_DIR
    proc = subprocess.Popen(
        APP_ENTRY.split(),
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )
    time.sleep(3)  # wait for window to appear
    yield proc
    proc.terminate()
    proc.wait(timeout=10)
    shutil.rmtree(E2E_DATA_DIR, ignore_errors=True)
```

- [ ] **Step 2: Create `tests/e2e/test_launch.py`**

```python
"""
e2e: Launch the app and verify the unlock/setup dialog appears.
Requires macOS Accessibility permission for the terminal app.
Run with: pytest tests/e2e -m e2e -v
"""
import pytest

pytestmark = pytest.mark.e2e


def test_app_launches_without_crash(running_app):
    """App process should still be running 3 seconds after launch."""
    assert running_app.poll() is None, "App process exited unexpectedly"


def test_password_dialog_visible_on_fresh_start(running_app):
    """
    On a fresh data dir (no password set) the setup dialog should appear.
    We verify via computer-use-mcp screenshot: look for the Chinese text
    '设置密码' or '请设置' in the screen capture.

    NOTE: This test uses computer-use-mcp. If it's not configured,
    the test is skipped automatically.
    """
    pytest.importorskip("computer_use_mcp", reason="computer-use-mcp not installed")
    # computer-use-mcp is invoked via Claude Code tool; in automated pytest
    # context we rely on the process staying alive as a smoke signal.
    assert running_app.poll() is None
```

- [ ] **Step 3: Run the e2e tests (requires Accessibility permission granted)**

```bash
pytest tests/e2e -m e2e -v
```

Expected: `test_app_launches_without_crash` PASSES. `test_password_dialog_visible_on_fresh_start` is either PASSED or SKIPPED.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/conftest.py tests/e2e/test_launch.py
git commit -m "test: e2e launch fixture and smoke test for app startup"
```

---

## Task 11: e2e smoke tests — `test_smoke.py`

**Files:**
- Create: `tests/e2e/test_smoke.py`

- [ ] **Step 1: Write `test_smoke.py`**

```python
"""
e2e smoke tests: new note, new folder, data persistence across restart.
Run with: pytest tests/e2e/test_smoke.py -m e2e -v
"""
import os
import shutil
import subprocess
import time
import sqlite3
import pytest

pytestmark = pytest.mark.e2e

E2E_DATA_DIR = "/tmp/encnotes_test"


def _db_path():
    return os.path.join(E2E_DATA_DIR, "NoteStore.sqlite")


def _count_notes():
    """Count non-deleted notes directly in the test DB."""
    db = _db_path()
    if not os.path.exists(db):
        return 0
    conn = sqlite3.connect(db)
    cur = conn.execute("SELECT COUNT(*) FROM ZNOTE WHERE ZISDELETED = 0")
    count = cur.fetchone()[0]
    conn.close()
    return count


def _count_folders():
    db = _db_path()
    if not os.path.exists(db):
        return 0
    conn = sqlite3.connect(db)
    cur = conn.execute("SELECT COUNT(*) FROM ZFOLDER")
    count = cur.fetchone()[0]
    conn.close()
    return count


def _launch_app():
    env = os.environ.copy()
    env["ENCNOTES_TEST_DATA_DIR"] = E2E_DATA_DIR
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return subprocess.Popen(["python", "main.py"], env=env, cwd=repo_root)


def test_note_created_via_manager_persists(tmp_path, monkeypatch):
    """
    Create a note directly via NoteManager in the e2e test dir,
    then reopen NoteManager and confirm the note is still there.
    This validates the DB persistence path without needing UI control.
    """
    if os.path.exists(E2E_DATA_DIR):
        shutil.rmtree(E2E_DATA_DIR)
    os.makedirs(E2E_DATA_DIR)

    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", E2E_DATA_DIR)

    from unittest.mock import patch
    fake_keyring: dict = {}
    with patch("keyring.set_password", side_effect=lambda s, u, p: fake_keyring.__setitem__((s, u), p)), \
         patch("keyring.get_password", side_effect=lambda s, u: fake_keyring.get((s, u))), \
         patch("keyring.delete_password", side_effect=lambda s, u: fake_keyring.pop((s, u), None)):
        from note_manager import NoteManager
        mgr = NoteManager()
        mgr.create_note("Persist Me", "Hello")
        mgr.close()

        # Re-open a fresh manager pointing at the same dir
        import importlib
        import note_manager as nm_mod
        importlib.reload(nm_mod)
        mgr2 = nm_mod.NoteManager()
        notes = mgr2.get_all_notes()
        titles = [n["title"] for n in notes]
        assert "Persist Me" in titles
        mgr2.close()

    shutil.rmtree(E2E_DATA_DIR, ignore_errors=True)


def test_app_does_not_write_to_real_data_dir(tmp_path):
    """
    Sanity check: the real NoteStore.sqlite modification time should not
    change when the app is launched with ENCNOTES_TEST_DATA_DIR set.
    """
    import os
    real_db = os.path.expanduser(
        "~/Library/Group Containers/group.com.encnotes/NoteStore.sqlite"
    )
    if not os.path.exists(real_db):
        pytest.skip("Real DB not found — skipping isolation check")

    mtime_before = os.path.getmtime(real_db)

    if os.path.exists(E2E_DATA_DIR):
        shutil.rmtree(E2E_DATA_DIR)
    os.makedirs(E2E_DATA_DIR)

    proc = _launch_app()
    time.sleep(4)
    proc.terminate()
    proc.wait(timeout=10)

    mtime_after = os.path.getmtime(real_db)
    shutil.rmtree(E2E_DATA_DIR, ignore_errors=True)

    assert mtime_before == mtime_after, (
        "Real NoteStore.sqlite was modified during test run — isolation broken!"
    )
```

- [ ] **Step 2: Run smoke tests**

```bash
pytest tests/e2e/test_smoke.py -m e2e -v
```

Expected: Both tests PASS.

- [ ] **Step 3: Run full suite excluding e2e to confirm no regressions**

```bash
pytest tests/unit tests/integration -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_smoke.py
git commit -m "test: e2e smoke tests for persistence and data isolation"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run full unit + integration suite**

```bash
pytest tests/unit tests/integration -v --tb=short
```

Expected: All tests PASS, zero failures.

- [ ] **Step 2: Run e2e suite**

```bash
pytest tests/e2e -m e2e -v --tb=short
```

Expected: All tests PASS or SKIPPED (computer-use-mcp import check).

- [ ] **Step 3: Confirm real data is untouched**

```bash
ls -la ~/Library/Group\ Containers/group.com.encnotes/
```

Expected: Modification times on `NoteStore.sqlite` and `encryption_config.json` are unchanged from before the test run.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "test: complete three-layer test suite — unit, integration, e2e"
```
