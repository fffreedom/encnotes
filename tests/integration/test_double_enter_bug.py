"""
回归测试：双回车 bug 修复验证

Bug 描述：光标在第 0 行（标题行）或第 1 行（正文第一行）末尾时，
连续按两次回车只会产生一个新行，而不是两个。

修复方案：在 keyPressEvent 中拦截 Return 键，对带有 MinimumHeight/FixedHeight
blockFormat 或带有显式 blockCharFormat.fontSize 的空块，直接调用
cursor.insertBlock() 绕过 Qt 缺陷，并移除无需再用的延迟 _apply_block_format 机制。

相关代码：note_editor.py -> _handle_return_on_minimum_height_block
"""
import sys
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, "/Users/freedom/project/nb/encnotes")


@pytest.fixture(scope="module")
def app():
    """Module-scoped QApplication（避免重复创建）。"""
    instance = QApplication.instance() or QApplication(sys.argv)
    return instance


@pytest.fixture
def text_edit(app, qtbot):
    """直接使用 PasteImageTextEdit（NoteEditor 内部的 QTextEdit 子类）来测试键盘行为。"""
    from note_editor import PasteImageTextEdit
    widget = PasteImageTextEdit()
    qtbot.addWidget(widget)
    widget.show()
    widget.setFocus()
    qtbot.waitExposed(widget)
    return widget


def _process_events(qtbot, ms=50):
    """处理 Qt 事件队列，包括 QTimer.singleShot(0) 注册的回调。"""
    qtbot.wait(ms)


# ─────────────────────────────────────────────
# 场景一：光标在第 0 行（标题行）末尾，连续按两次回车
# ─────────────────────────────────────────────

class TestDoubleEnterFromTitleLine:
    """标题行（block 0）末尾连续两次回车应产生两个新行。"""

    def test_single_enter_from_empty_title_creates_one_new_block(self, text_edit, qtbot):
        """单次回车应使文档从 1 行变为 2 行（基准测试）。"""
        text_edit.clear()
        _process_events(qtbot)

        before = text_edit.document().blockCount()
        assert before == 1, f"清空后应只有 1 行，实际 {before} 行"

        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        after = text_edit.document().blockCount()
        assert after == 2, f"单次回车后应有 2 行，实际 {after} 行"

    def test_double_enter_from_empty_title_creates_two_new_blocks(self, text_edit, qtbot):
        """
        核心回归测试（场景一）：
        清空编辑器（光标在第 0 行），连续按两次回车，文档应从 1 行变为 3 行。
        """
        text_edit.clear()
        _process_events(qtbot)

        assert text_edit.document().blockCount() == 1

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_first = text_edit.document().blockCount()
        assert after_first == 2, f"第一次回车后应有 2 行，实际 {after_first} 行"

        # 第二次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_second = text_edit.document().blockCount()
        assert after_second == 3, (
            f"第二次回车后应有 3 行（双回车 bug 检测），实际 {after_second} 行。"
            "如果是 2 行，说明 setBlockFormat(MinimumHeight) bug 仍然存在！"
        )

    def test_double_enter_from_title_with_text_creates_two_new_blocks(self, text_edit, qtbot):
        """
        标题行有内容时，光标移到末尾，连续两次回车应产生两个新行。
        """
        text_edit.clear()
        _process_events(qtbot)

        # 在第 0 行输入标题文字
        qtbot.keyClicks(text_edit, "My Title")
        _process_events(qtbot)

        # 确保光标在行末
        cursor = text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.EndOfBlock)
        text_edit.setTextCursor(cursor)
        _process_events(qtbot)

        before = text_edit.document().blockCount()

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_first = text_edit.document().blockCount()
        assert after_first == before + 1, f"第一次回车后应增加 1 行，实际 {after_first}"

        # 第二次回车（此时光标在新空行，即第 1 行）
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_second = text_edit.document().blockCount()
        assert after_second == before + 2, (
            f"第二次回车后应增加 2 行（共 {before + 2} 行），实际 {after_second} 行。"
            "双回车 bug 仍存在！"
        )


# ─────────────────────────────────────────────
# 场景二：光标在第 1 行（正文第一行）末尾，连续两次回车
# ─────────────────────────────────────────────

class TestDoubleEnterFromBodyFirstLine:
    """正文第一行（block 1）末尾连续两次回车应产生两个新行。"""

    def _move_cursor_to_block(self, text_edit, block_number):
        """将光标移动到指定块的末尾。"""
        doc = text_edit.document()
        block = doc.findBlockByNumber(block_number)
        cursor = text_edit.textCursor()
        cursor.setPosition(block.position() + max(0, block.length() - 1))
        text_edit.setTextCursor(cursor)

    def test_double_enter_from_empty_body_first_line_creates_two_new_blocks(self, text_edit, qtbot):
        """
        核心回归测试（场景二）：
        准备两行文档（标题行 + 空的正文第一行），光标在正文第一行，
        连续两次回车，文档应从 2 行变为 4 行。
        """
        text_edit.clear()
        _process_events(qtbot)

        # 让文档先有两行：先按一次回车从标题行创建正文第一行
        qtbot.keyClicks(text_edit, "Title")
        _process_events(qtbot)
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        assert text_edit.document().blockCount() == 2, "准备阶段：应有 2 行"
        # 确保光标在第 1 行（正文第一行）
        cursor = text_edit.textCursor()
        assert cursor.block().blockNumber() == 1, f"光标应在第 1 行，实际在第 {cursor.block().blockNumber()} 行"

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_first = text_edit.document().blockCount()
        assert after_first == 3, f"第一次回车后应有 3 行，实际 {after_first} 行"

        # 第二次回车（光标在第 2 行，已超出 set_input_format 的作用范围，属于正常行为）
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_second = text_edit.document().blockCount()
        assert after_second == 4, (
            f"第二次回车后应有 4 行，实际 {after_second} 行。"
            "双回车 bug 仍存在！"
        )

    def test_double_enter_from_body_first_line_with_text(self, text_edit, qtbot):
        """正文第一行有内容时，光标在末尾连续两次回车也应产生两个新行。"""
        text_edit.clear()
        _process_events(qtbot)

        # 标题行
        qtbot.keyClicks(text_edit, "Title")
        _process_events(qtbot)
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        # 在正文第一行输入内容
        qtbot.keyClicks(text_edit, "Body line one")
        _process_events(qtbot)

        before = text_edit.document().blockCount()
        assert before == 2

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_first = text_edit.document().blockCount()
        assert after_first == 3, f"第一次回车后应有 3 行，实际 {after_first} 行"

        # 第二次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_second = text_edit.document().blockCount()
        assert after_second == 4, (
            f"第二次回车后应有 4 行，实际 {after_second} 行。"
        )


# ─────────────────────────────────────────────
# 场景三：从标题行（block 0）按回车的完整行为验证
# ─────────────────────────────────────────────

class TestEnterFromTitleLine:
    """从标题行按回车的行为验证：光标位置、文本分割、格式继承。"""

    def test_enter_at_end_of_title_moves_cursor_to_block1(self, text_edit, qtbot):
        """标题行末尾按回车后，光标应落在第 1 行（block 1）。"""
        text_edit.clear()
        _process_events(qtbot)

        qtbot.keyClicks(text_edit, "My Title")
        _process_events(qtbot)

        # 确保光标在第 0 行末尾
        cursor = text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.EndOfBlock)
        text_edit.setTextCursor(cursor)
        _process_events(qtbot)

        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        cursor_after = text_edit.textCursor()
        assert cursor_after.block().blockNumber() == 1, (
            f"回车后光标应在第 1 行，实际在第 {cursor_after.block().blockNumber()} 行"
        )

    def test_enter_in_middle_of_title_splits_text(self, text_edit, qtbot):
        """在标题行中间按回车，应将标题文字分割到两个块。"""
        text_edit.clear()
        _process_events(qtbot)

        qtbot.keyClicks(text_edit, "HelloWorld")
        _process_events(qtbot)

        # 将光标移到 "Hello" 和 "World" 之间（第 5 个字符之后）
        doc = text_edit.document()
        block0 = doc.findBlockByNumber(0)
        cursor = text_edit.textCursor()
        cursor.setPosition(block0.position() + 5)
        text_edit.setTextCursor(cursor)
        _process_events(qtbot)

        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        block0_text = doc.findBlockByNumber(0).text()
        block1_text = doc.findBlockByNumber(1).text()
        assert block0_text == "Hello", f"第 0 行应为 'Hello'，实际为 '{block0_text}'"
        assert block1_text == "World", f"第 1 行应为 'World'，实际为 '{block1_text}'"

    def test_enter_at_start_of_title_inserts_blank_block_above(self, text_edit, qtbot):
        """在标题行开头按回车，应在第 0 行前插入空行，原标题变为第 1 行。"""
        text_edit.clear()
        _process_events(qtbot)

        qtbot.keyClicks(text_edit, "My Title")
        _process_events(qtbot)

        # 光标移到第 0 行开头
        cursor = text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.StartOfBlock)
        text_edit.setTextCursor(cursor)
        _process_events(qtbot)

        before_count = text_edit.document().blockCount()
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        after_count = text_edit.document().blockCount()
        assert after_count == before_count + 1, (
            f"开头回车后行数应 +1，before={before_count}, after={after_count}"
        )
        # 原来的 "My Title" 应向下移动到第 1 行
        block1_text = text_edit.document().findBlockByNumber(1).text()
        assert block1_text == "My Title", (
            f"原标题应在第 1 行，实际第 1 行内容为 '{block1_text}'"
        )

    def test_double_enter_at_end_of_title_with_text_produces_correct_structure(self, text_edit, qtbot):
        """
        标题有内容，光标在末尾连续两次回车，验证最终文档结构：
          block 0: "My Title"（原标题内容保留）
          block 1: ""（第一次回车产生的空行）
          block 2: ""（第二次回车产生的空行）
        """
        text_edit.clear()
        _process_events(qtbot)

        qtbot.keyClicks(text_edit, "My Title")
        _process_events(qtbot)

        cursor = text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.EndOfBlock)
        text_edit.setTextCursor(cursor)
        _process_events(qtbot)

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        # 第二次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        doc = text_edit.document()
        assert doc.blockCount() == 3, (
            f"双回车后应有 3 行，实际 {doc.blockCount()} 行（双回车 bug！）"
        )
        assert doc.findBlockByNumber(0).text() == "My Title", "第 0 行应保留标题文字"
        assert doc.findBlockByNumber(1).text() == "", "第 1 行应为空行"
        assert doc.findBlockByNumber(2).text() == "", "第 2 行应为空行"

        # 光标应在第 2 行
        final_cursor = text_edit.textCursor()
        assert final_cursor.block().blockNumber() == 2, (
            f"最终光标应在第 2 行，实际在第 {final_cursor.block().blockNumber()} 行"
        )


# ─────────────────────────────────────────────
# 验证修复后不再有 "手动 insertBlock" 补丁
# ─────────────────────────────────────────────

class TestNoManualInsertBlockPatch:
    """确认 keyPressEvent 中已不存在手动 insertBlock 的补丁代码（这是 bug 的旧补丁）。"""

    def test_no_extra_block_inserted_on_normal_enter(self, text_edit, qtbot):
        """
        普通情况下按一次回车精确增加 1 行（而不是因为手动 insertBlock 而增加 2 行）。
        """
        text_edit.clear()
        _process_events(qtbot)

        # 先输入一些内容
        qtbot.keyClicks(text_edit, "Hello")
        _process_events(qtbot)
        before = text_edit.document().blockCount()

        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after = text_edit.document().blockCount()

        assert after == before + 1, (
            f"一次回车只应增加 1 行，但增加了 {after - before} 行。"
            "可能 insertBlock 补丁被错误地保留了！"
        )


# ─────────────────────────────────────────────
# Bug 回归：旧笔记（含 MinimumHeight 格式）加载后双回车是否正常
# ─────────────────────────────────────────────

class TestLegacyMinimumHeightMigration:
    """回归测试：旧版 HTML 中残留的 MinimumHeight 被清除后，双回车应恢复正常。"""

    def _set_minimum_height_on_block(self, text_edit, block_number, line_height_px=20):
        """在指定块上手动设置 MinimumHeight，模拟旧版保存的笔记数据。"""
        from PyQt6.QtGui import QTextBlockFormat
        doc = text_edit.document()
        block = doc.findBlockByNumber(block_number)
        cursor = text_edit.textCursor()
        cursor.setPosition(block.position())
        cursor.select(cursor.SelectionType.BlockUnderCursor)
        fmt = QTextBlockFormat()
        # LineHeightTypes.MinimumHeight == 3
        fmt.setLineHeight(line_height_px, 3)
        cursor.mergeBlockFormat(fmt)

    def _clear_minimum_height(self, text_edit, block_numbers=(0, 1)):
        """模拟 _clear_legacy_minimum_height 的行为（在 PasteImageTextEdit 层执行）。"""
        from PyQt6.QtGui import QTextBlockFormat
        doc = text_edit.document()
        for block_number in block_numbers:
            block = doc.findBlockByNumber(block_number)
            if not block.isValid():
                continue
            fmt = block.blockFormat()
            if fmt.lineHeightType() == 3:
                cursor = text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(cursor.SelectionType.BlockUnderCursor)
                new_fmt = QTextBlockFormat()
                new_fmt.setLineHeight(0, 0)
                text_edit.blockSignals(True)
                cursor.mergeBlockFormat(new_fmt)
                text_edit.blockSignals(False)

    def test_minimum_height_on_block1_fix_handles_double_enter(self, text_edit, qtbot):
        """
        回归测试：即使 block 0 带有 MinimumHeight（旧版数据），
        _handle_return_on_minimum_height_block 拦截后按回车仍能正确插入新段落。

        注意：原始 Qt 行为下，MinimumHeight 块的 Return 会被识别为"清除段落格式"，
        但 keyPressEvent 中的防御性修复 (_handle_return_on_minimum_height_block)
        已拦截此情况，直接调用 cursor.insertBlock()，因此行数应正确增加。
        """
        text_edit.clear()
        _process_events(qtbot)

        # block 0 是空的，给它设置 MinimumHeight（模拟旧版保存数据）
        self._set_minimum_height_on_block(text_edit, block_number=0, line_height_px=20)
        _process_events(qtbot)

        # 确认 block 0 有 MinimumHeight
        block0_fmt = text_edit.document().findBlockByNumber(0).blockFormat()
        if block0_fmt.lineHeightType() != 3:
            import pytest
            pytest.skip("MinimumHeight 设置失败，无法验证修复行为")

        before = text_edit.document().blockCount()
        assert before == 1

        # 从有 MinimumHeight 的 block 0 按回车 — 修复后应正确增加一行
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after = text_edit.document().blockCount()

        assert after == before + 1, (
            f"MinimumHeight 块上按回车后行数应 +1（修复已生效），"
            f"但 before={before}, after={after}。"
        )

    def test_clearing_minimum_height_fixes_double_enter_bug(self, text_edit, qtbot):
        """
        核心回归测试：清除 MinimumHeight 后，旧笔记的双回车 bug 应消失。
        """
        text_edit.clear()
        _process_events(qtbot)

        # 准备：标题行 + 正文第一行
        qtbot.keyClicks(text_edit, "Title")
        _process_events(qtbot)
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)

        assert text_edit.document().blockCount() == 2

        # 人为给 block 1 加上 MinimumHeight（模拟旧版数据）
        self._set_minimum_height_on_block(text_edit, block_number=1, line_height_px=20)
        _process_events(qtbot)

        # 清除 MinimumHeight（模拟 _clear_legacy_minimum_height）
        self._clear_minimum_height(text_edit, block_numbers=(0, 1))
        _process_events(qtbot)

        # 确认已清除
        block1_fmt = text_edit.document().findBlockByNumber(1).blockFormat()
        assert block1_fmt.lineHeightType() != 3, "清除后 block 1 不应有 MinimumHeight 格式"

        # 光标移到第 0 行末尾
        cursor = text_edit.textCursor()
        cursor.setPosition(text_edit.document().findBlockByNumber(0).position() + len("Title"))
        text_edit.setTextCursor(cursor)

        # 第一次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_first = text_edit.document().blockCount()
        assert after_first == 3, f"第一次回车后应有 3 行，实际 {after_first} 行"

        # 第二次回车
        qtbot.keyClick(text_edit, Qt.Key.Key_Return)
        _process_events(qtbot)
        after_second = text_edit.document().blockCount()
        assert after_second == 4, (
            f"清除 MinimumHeight 后第二次回车应有 4 行（双回车 bug 已修复），"
            f"实际 {after_second} 行。"
        )

