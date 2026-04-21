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
        stderr=subprocess.PIPE,
    )
    time.sleep(3)  # wait for window to appear
    yield proc
    proc.terminate()
    proc.wait(timeout=10)
    shutil.rmtree(E2E_DATA_DIR, ignore_errors=True)
