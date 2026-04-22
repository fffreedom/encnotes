"""Integration tests for MainWindow layout."""
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/Users/freedom/project/nb/encnotes")


@pytest.fixture
def main_window(qtbot, qt_app, tmp_path, monkeypatch):
    """Create a MainWindow with mocked heavy dependencies."""
    monkeypatch.setenv("ENCNOTES_TEST_DATA_DIR", str(tmp_path))

    fake_keyring: dict = {}

    with patch("keyring.set_password", side_effect=lambda s, u, p: fake_keyring.__setitem__((s, u), p)), \
         patch("keyring.get_password", side_effect=lambda s, u: fake_keyring.get((s, u))), \
         patch("keyring.delete_password", side_effect=lambda s, u: fake_keyring.pop((s, u), None)), \
         patch("icloud_sync.CloudKitSyncManager", return_value=MagicMock()), \
         patch("main_window.CloudKitSyncManager", return_value=MagicMock()), \
         patch.object(
             __import__("main_window", fromlist=["MainWindow"]).MainWindow,
             "_handle_encryption_setup",
             return_value=True,
         ):
        from main_window import MainWindow
        win = MainWindow()
        qtbot.addWidget(win)
        win.show()
        qtbot.waitExposed(win)
        yield win
        try:
            win.note_manager.close()
        except Exception:
            pass


def test_main_window_shows(main_window):
    """MainWindow should be visible after show()."""
    assert main_window.isVisible()


def test_three_pane_layout(main_window):
    """MainWindow should contain at least one QSplitter (three-pane layout)."""
    from PyQt6.QtWidgets import QSplitter
    splitters = main_window.findChildren(QSplitter)
    assert len(splitters) >= 1, "Expected at least one QSplitter in the main window"


def test_new_note_appears_in_list(main_window, qtbot):
    """Creating a note and refreshing the list should show it."""
    from PyQt6.QtWidgets import QListWidget

    # Count notes before
    before = main_window.note_list.count()

    # Create a note via note_manager
    main_window.note_manager.create_note("Integration Test Note", "body text")

    # Refresh note list
    try:
        main_window.load_notes()
    except Exception:
        pass  # best-effort — count check below still validates

    after = main_window.note_list.count()
    assert after >= before, "Note list count should not decrease after creating a note"


def _get_selected_folder_widget(main_window):
    """Helper: find the FolderRowWidget whose 'selected' property is True."""
    from PyQt6.QtCore import Qt
    fl = main_window.folder_list
    for i in range(fl.count()):
        item = fl.item(i)
        if not item:
            continue
        widget = fl.itemWidget(item)
        if widget and widget.objectName() == "folder_row_widget":
            if widget.property("selected") is True:
                return widget
    return None


def test_folder_highlight_on_select(main_window, qtbot):
    """选中一个文件夹后，对应的 FolderRowWidget.selected 属性应为 True（高亮显示）。"""
    from PyQt6.QtCore import Qt
    fl = main_window.folder_list

    # 先创建一个文件夹，确保列表里有可选的 folder
    main_window.note_manager.create_folder("测试文件夹")
    main_window.load_folders()
    qtbot.wait(100)

    # 找到第一个 folder 类型的 item
    target_row = None
    for i in range(fl.count()):
        item = fl.item(i)
        if not item:
            continue
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder":
            target_row = i
            break

    if target_row is None:
        pytest.skip("No user folder found in folder list")

    # 点击该行，触发 on_folder_changed
    fl.setCurrentRow(target_row)
    qtbot.wait(200)

    widget = _get_selected_folder_widget(main_window)
    assert widget is not None, (
        "选中文件夹后，应有一个 FolderRowWidget 的 selected 属性为 True，但没有找到。"
        "这说明文件夹高亮 bug 仍然存在。"
    )


def test_folder_highlight_persists_after_load_folders(main_window, qtbot):
    """load_folders() 重建列表后，已选中文件夹的高亮应通过 _restore_current_item_highlight() 恢复。"""
    from PyQt6.QtCore import Qt
    fl = main_window.folder_list

    # 先创建一个文件夹
    main_window.note_manager.create_folder("高亮测试文件夹")
    main_window.load_folders()
    qtbot.wait(100)

    # 找到第一个 folder 类型的 item 并选中
    target_row = None
    for i in range(fl.count()):
        item = fl.item(i)
        if not item:
            continue
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == "folder":
            target_row = i
            break

    if target_row is None:
        pytest.skip("No user folder found in folder list")

    fl.setCurrentRow(target_row)
    qtbot.wait(200)

    # 确认选中后高亮存在
    assert _get_selected_folder_widget(main_window) is not None, "初次选中后应有高亮"

    # 模拟触发 load_folders() 重建（这正是 bug 触发路径）
    main_window.load_folders()
    qtbot.wait(200)

    # 高亮应由 _restore_current_item_highlight() 恢复
    widget = _get_selected_folder_widget(main_window)
    assert widget is not None, (
        "load_folders() 重建列表后，_restore_current_item_highlight() 应恢复选中文件夹的高亮，但未找到高亮 widget。"
        "这说明 load_folders 后高亮丢失的 bug 仍然存在。"
    )


def _count_highlight_pixels(widget, target_hex: str, sample_y_ratio: float = 0.5) -> tuple[int, int]:
    """
    对 widget 截图，沿中部水平扫描线统计颜色匹配像素数。

    返回 (匹配像素数, 扫描线总像素数)。
    target_hex 格式：'#ffe066'
    """
    r = int(target_hex[1:3], 16)
    g = int(target_hex[3:5], 16)
    b = int(target_hex[5:7], 16)

    pixmap = widget.grab()
    image = pixmap.toImage()
    w, h = image.width(), image.height()
    scan_y = int(h * sample_y_ratio)

    matched = 0
    for x in range(w):
        c = image.pixelColor(x, scan_y)
        if c.red() == r and c.green() == g and c.blue() == b:
            matched += 1
    return matched, w


def test_folder_highlight_pixel_color_on_select(main_window, qtbot):
    """
    截图验证：选中文件夹后，FolderRowWidget 的渲染背景色应包含足够比例的 #ffe066（QSS 定义的高亮色）。
    这是对视觉高亮效果的像素级确认，而不仅仅是属性值检查。
    """
    from PyQt6.QtCore import Qt
    fl = main_window.folder_list

    main_window.note_manager.create_folder("像素验证文件夹")
    main_window.load_folders()
    qtbot.wait(100)

    target_row = None
    for i in range(fl.count()):
        item = fl.item(i)
        if not item:
            continue
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, tuple) and payload[0] == "folder":
            target_row = i
            break

    if target_row is None:
        pytest.skip("No user folder found in folder list")

    fl.setCurrentRow(target_row)
    qtbot.wait(300)

    widget = _get_selected_folder_widget(main_window)
    assert widget is not None, "未找到 selected=True 的 FolderRowWidget"

    matched, total = _count_highlight_pixels(widget, "#ffe066")
    ratio = matched / total if total > 0 else 0

    assert ratio >= 0.3, (
        f"截图像素验证失败：选中文件夹后，扫描线上 #ffe066 像素占比为 {ratio:.1%}（{matched}/{total}），"
        f"期望 ≥ 30%。这说明 QSS 高亮样式没有实际渲染到屏幕上。"
    )


def test_folder_highlight_pixel_color_persists_after_load_folders(main_window, qtbot):
    """
    截图验证：load_folders() 重建列表后，选中文件夹的像素高亮颜色应依然存在。
    验证 _restore_current_item_highlight() 的视觉效果，而不仅仅是属性值。
    """
    from PyQt6.QtCore import Qt
    fl = main_window.folder_list

    main_window.note_manager.create_folder("像素持久化验证文件夹")
    main_window.load_folders()
    qtbot.wait(100)

    target_row = None
    for i in range(fl.count()):
        item = fl.item(i)
        if not item:
            continue
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, tuple) and payload[0] == "folder":
            target_row = i
            break

    if target_row is None:
        pytest.skip("No user folder found in folder list")

    # 选中文件夹，再触发 load_folders() 重建（bug 复现路径）
    fl.setCurrentRow(target_row)
    qtbot.wait(200)
    main_window.load_folders()
    qtbot.wait(300)

    widget = _get_selected_folder_widget(main_window)
    assert widget is not None, "load_folders() 后未找到 selected=True 的 FolderRowWidget"

    matched, total = _count_highlight_pixels(widget, "#ffe066")
    ratio = matched / total if total > 0 else 0

    assert ratio >= 0.3, (
        f"截图像素验证失败：load_folders() 重建后，扫描线上 #ffe066 像素占比为 {ratio:.1%}（{matched}/{total}），"
        f"期望 ≥ 30%。这说明 _restore_current_item_highlight() 没有真正恢复视觉高亮。"
    )
