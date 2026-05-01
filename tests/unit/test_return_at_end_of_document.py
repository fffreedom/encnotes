#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for pressing Return at the end of document (last empty block).

Bug: pressing Return twice at end of line only produces one new line.
Root cause: when a QTextBlock has MinimumHeight set on its QTextBlockFormat
(lineHeightType == 1 or 3), Qt's QTextEdit.keyPressEvent(Return) does NOT
insert a new block — it only clears the paragraph format.

Old code called setBlockFormat(MinimumHeight) on blocks 0 and 1.
Each time the user pressed Return from those blocks, the new block inherited
MinimumHeight. Those new blocks were serialised to HTML and re-loaded into
the editor. _clear_legacy_minimum_height() only cleared blocks 0 and 1,
leaving all blocks ≥ 2 with the bad format still set.
"""

import sys
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent, QTextCursor, QTextBlockFormat
from PyQt6.QtCore import Qt, QEvent


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def text_edit(qt_app):
    """Create a PasteImageTextEdit instance (the inner editor) for testing."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from note_editor import PasteImageTextEdit
    widget = PasteImageTextEdit()
    yield widget
    widget.deleteLater()


def _press_return(widget):
    """Simulate a Return key press on the widget."""
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(event)


def _set_minimum_height_on_block(text_edit, block_number, line_height=28):
    """
    Set MinimumHeight (lineHeightType=1) on the given block.

    This simulates what old serialised HTML data contains: old code called
    setBlockFormat(MinimumHeight) on blocks 0 and 1; new blocks created by
    pressing Return inherited that format and were saved to the DB.
    """
    doc = text_edit.document()
    block = doc.findBlockByNumber(block_number)
    assert block.isValid(), f"Block {block_number} is not valid"
    cursor = QTextCursor(block)
    fmt = cursor.blockFormat()
    fmt.setLineHeight(line_height, 1)  # 1 == QTextBlockFormat.LineHeightTypes.MinimumHeight
    cursor.setBlockFormat(fmt)
    # Verify the format was set
    updated_fmt = doc.findBlockByNumber(block_number).blockFormat()
    assert updated_fmt.lineHeightType() == 1, (
        f"Failed to set MinimumHeight on block {block_number}: "
        f"lineHeightType={updated_fmt.lineHeightType()}"
    )


# ---------------------------------------------------------------------------
# Tests that REPRODUCE the bug (MinimumHeight present on target block)
# ---------------------------------------------------------------------------

def test_return_at_end_of_document_with_minimum_height_inserts_new_line(text_edit):
    """
    Pressing Return on the last empty block that has MinimumHeight set
    should still insert a new line.

    Reproduces the bug: Qt treats Return on a MinimumHeight block as
    "clear paragraph format" rather than "insert new paragraph".
    The fix must intercept this case and ensure a new block is inserted.
    """
    text_edit.setPlainText("测试标题\n行内容\n")

    doc = text_edit.document()
    assert doc.blockCount() == 3, f"Expected 3 blocks initially, got {doc.blockCount()}"

    # Simulate old serialised HTML: block 2 (the trailing empty paragraph)
    # has MinimumHeight inherited from the Return pressed on block 1.
    _set_minimum_height_on_block(text_edit, 2)

    # Move cursor to the last block (the trailing empty paragraph)
    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 2, (
        f"Cursor should be on block 2 (last empty), got {cursor.block().blockNumber()}"
    )
    assert cursor.block().text() == "", (
        f"Last block should be empty, got {repr(cursor.block().text())}"
    )

    # Action: press Return on the last empty block that has MinimumHeight
    _press_return(text_edit)

    # Assertion: block count must increase by 1
    new_count = doc.blockCount()
    assert new_count == 4, (
        f"Pressing Return at end-of-document block with MinimumHeight should increase "
        f"blockCount from 3 to 4, but got {new_count}. This is the double-Return bug."
    )


def test_return_at_middle_block_with_minimum_height_inserts_new_line(text_edit):
    """
    Pressing Return on an empty block in the MIDDLE of the document that has
    MinimumHeight set should still work correctly.
    """
    text_edit.setPlainText("测试标题\n行内容\n\n更多内容")

    doc = text_edit.document()
    assert doc.blockCount() == 4

    # Set MinimumHeight on block 2 (middle empty line)
    _set_minimum_height_on_block(text_edit, 2)

    # Move cursor to block 2 (the middle empty line)
    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 2
    assert cursor.block().text() == ""

    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 5, (
        f"Pressing Return at a middle empty block with MinimumHeight should increase "
        f"blockCount from 4 to 5, but got {new_count}."
    )


def test_return_at_non_empty_line_with_minimum_height_inserts_new_line(text_edit):
    """
    Pressing Return at the end of a non-empty line that has MinimumHeight set
    should still insert a new block.
    """
    text_edit.setPlainText("测试标题\n行内容")
    doc = text_edit.document()
    assert doc.blockCount() == 2

    # Set MinimumHeight on block 1 (non-empty "行内容" block)
    _set_minimum_height_on_block(text_edit, 1)

    # Move to end of "行内容" (block 1)
    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 1
    assert cursor.block().text() == "行内容"

    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 3, (
        f"Pressing Return at end of non-empty line with MinimumHeight should increase "
        f"blockCount from 2 to 3, but got {new_count}."
    )


# ---------------------------------------------------------------------------
# Sanity checks: Return without MinimumHeight should continue to work
# ---------------------------------------------------------------------------

def test_return_at_end_of_document_last_empty_block_inserts_new_line(text_edit):
    """
    Baseline: pressing Return on the last empty block (no MinimumHeight)
    should still insert a new line.
    """
    text_edit.setPlainText("测试标题\n行内容\n")

    doc = text_edit.document()
    assert doc.blockCount() == 3, f"Expected 3 blocks initially, got {doc.blockCount()}"

    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 2
    assert cursor.block().text() == ""

    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 4, (
        f"Pressing Return at end-of-document empty block should increase blockCount from 3 to 4, "
        f"but got {new_count}. This is the double-Return bug."
    )


def test_return_at_middle_empty_block_still_inserts_new_line(text_edit):
    """
    Baseline: pressing Return on an empty block in the MIDDLE of the document
    (no MinimumHeight) should still work correctly.
    """
    text_edit.setPlainText("测试标题\n行内容\n\n更多内容")

    doc = text_edit.document()
    assert doc.blockCount() == 4

    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 2
    assert cursor.block().text() == ""

    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 5, (
        f"Pressing Return at a middle empty block should increase blockCount from 4 to 5, "
        f"but got {new_count}."
    )


def test_return_at_non_empty_line_inserts_new_line(text_edit):
    """
    Baseline: pressing Return on a non-empty line (no MinimumHeight) should
    insert a new block.
    """
    text_edit.setPlainText("测试标题\n行内容")
    doc = text_edit.document()
    assert doc.blockCount() == 2

    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)

    assert cursor.block().blockNumber() == 1
    assert cursor.block().text() == "行内容"

    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 3, (
        f"Pressing Return at end of non-empty line should increase blockCount from 2 to 3, "
        f"but got {new_count}."
    )


# ---------------------------------------------------------------------------
# Tests for explicit charFormat fontPointSize on empty block (HTML reload bug)
# ---------------------------------------------------------------------------

def _load_html_note(text_edit, title="bug1测试标题", body_lines=None):
    """
    Load a note via setHtml, which sets blockCharFormat.fontSize on all blocks.
    This replicates what happens when a saved note is loaded from the database.
    Returns the note's HTML string.
    """
    if body_lines is None:
        body_lines = ["第一行内容", "X", "Y"]
    body_html = "".join(f'<p style="font-size:14pt;">{line}</p>' for line in body_lines)
    html = (
        '<html><head><meta charset="utf-8"></head><body>'
        f'<p style="font-size:28pt; font-weight:bold;">{title}</p>'
        f'{body_html}'
        '</body></html>'
    )
    text_edit.setHtml(html)
    return html


def _move_cursor_to_new_empty_block_after_last_line(text_edit):
    """
    Press Return at the end of the last line to create a new empty block,
    then return the new cursor (positioned on the empty block).
    This matches the exact state that triggers the bug in the live app.
    """
    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)
    _press_return(text_edit)
    return text_edit.textCursor()


def test_return_on_empty_block_after_html_load_inserts_new_line(text_edit):
    """
    After loading a note from HTML (which sets blockCharFormat.fontSize=14 on
    all blocks), pressing Return at the end of the last line creates a new empty
    block. Pressing Return again on that empty block must insert ANOTHER new block.

    Root cause: Qt's super().keyPressEvent(Return) on an empty block where
    blockCharFormat.fontPointSize() > 0 produces delta=0 (clears charFmt instead
    of inserting a new paragraph). The fix must intercept this case and call
    cursor.insertBlock() directly.
    """
    _load_html_note(text_edit, body_lines=["第一行内容", "Y"])
    doc = text_edit.document()
    # After HTML load: 3 blocks (title + 第一行内容 + Y)
    assert doc.blockCount() == 3, f"Expected 3 blocks after HTML load, got {doc.blockCount()}"

    # First Return: move cursor to end of 'Y', press Return → creates empty block 3
    new_cursor = _move_cursor_to_new_empty_block_after_last_line(text_edit)
    assert doc.blockCount() == 4, (
        f"Expected 4 blocks after 1st Return, got {doc.blockCount()}"
    )
    assert new_cursor.block().blockNumber() == 3
    assert new_cursor.block().text() == ""

    # Verify the bug condition: the new empty block has blockCharFmt.fontSize > 0
    block_char_fmt_size = new_cursor.blockCharFormat().fontPointSize()
    assert block_char_fmt_size > 0, (
        f"Test setup error: expected blockCharFmt.fontPointSize > 0, got {block_char_fmt_size}"
    )

    # Second Return on the empty block — this is where the bug occurs
    _press_return(text_edit)

    new_count = doc.blockCount()
    assert new_count == 5, (
        f"Pressing Return on empty block (blockCharFmt.fontSize={block_char_fmt_size}) "
        f"after HTML load should increase blockCount from 4 to 5, but got {new_count}. "
        f"This is the HTML-reload double-Return bug."
    )


def test_consecutive_returns_after_html_load_all_insert_new_lines(text_edit):
    """
    Pressing Return multiple times at the end of an HTML-loaded note should
    always insert a new block — even after the first Return creates an empty
    block with blockCharFmt.fontSize=14.
    """
    _load_html_note(text_edit, body_lines=["第一行内容", "X", "Y"])
    doc = text_edit.document()
    assert doc.blockCount() == 4, f"Expected 4 blocks after HTML load, got {doc.blockCount()}"

    cursor = text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    text_edit.setTextCursor(cursor)

    # Press Return 3 times — each should produce a new block
    for i in range(1, 4):
        bc_before = doc.blockCount()
        _press_return(text_edit)
        bc_after = doc.blockCount()
        assert bc_after == bc_before + 1, (
            f"Return press #{i}: expected blockCount {bc_before + 1}, got {bc_after}. "
            f"HTML-reload double-Return bug."
        )
