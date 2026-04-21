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
    pytest.importorskip("html2text", reason="html2text not installed")
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
