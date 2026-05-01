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
    cur = conn.execute("SELECT COUNT(*) FROM enc_note WHERE ZISDELETED = 0")
    count = cur.fetchone()[0]
    conn.close()
    return count


def _count_folders():
    db = _db_path()
    if not os.path.exists(db):
        return 0
    conn = sqlite3.connect(db)
    cur = conn.execute("SELECT COUNT(*) FROM enc_folder")
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

    # Re-open in a fresh subprocess to avoid module caching issues
    import sys, json
    result = subprocess.run(
        [sys.executable, "-c",
         f"""
import os, sys
sys.path.insert(0, '.')
os.environ['ENCNOTES_TEST_DATA_DIR'] = '{E2E_DATA_DIR}'
from unittest.mock import patch
fake_keyring = {{}}
with patch('keyring.set_password', side_effect=lambda s,u,p: fake_keyring.__setitem__((s,u),p)), \\
     patch('keyring.get_password', side_effect=lambda s,u: fake_keyring.get((s,u))), \\
     patch('keyring.delete_password', side_effect=lambda s,u: fake_keyring.pop((s,u),None)):
    from note_manager import NoteManager
    mgr = NoteManager()
    notes = mgr.get_all_notes()
    print([n['title'] for n in notes])
    mgr.close()
"""],
        capture_output=True, text=True, cwd='/Users/freedom/project/nb/encnotes'
    )
    assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
    titles = eval(result.stdout.strip())
    assert "Persist Me" in titles

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
