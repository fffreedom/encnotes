"""Integration tests for NoteEditor widget."""
import pytest
from PyQt6.QtCore import Qt


@pytest.fixture
def editor(qtbot, qt_app):
    import sys
    sys.path.insert(0, "/Users/freedom/project/nb/encnotes")
    from note_editor import NoteEditor
    widget = NoteEditor()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_editor_shows(editor):
    assert editor.isVisible()


def test_type_text_appears_in_content(editor, qtbot):
    editor.clear()
    qtbot.keyClicks(editor.text_edit, "Hello World")
    content = editor.toPlainText()
    assert "Hello World" in content


def test_bold_shortcut_does_not_crash(editor, qtbot):
    """Cmd+B (or Ctrl+B) should not raise."""
    editor.clear()
    qtbot.keyClicks(editor.text_edit, "Bold me")
    editor.text_edit.selectAll()
    try:
        qtbot.keyClick(editor.text_edit, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    except Exception as e:
        pytest.fail(f"Bold shortcut raised: {e}")


def test_italic_shortcut_does_not_crash(editor, qtbot):
    editor.clear()
    qtbot.keyClicks(editor.text_edit, "Italic me")
    editor.text_edit.selectAll()
    try:
        qtbot.keyClick(editor.text_edit, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
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
    if hasattr(editor, "insert_table"):
        editor.insert_table()
        html = editor.toHtml()
        assert "<table" in html.lower()
    else:
        pytest.skip("insert_table method not found on NoteEditor")
