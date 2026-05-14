# NoteListWidget 选择事件调用链与 Bug 分析报告

> 分析对象：`encnotes` 项目中 `NoteListWidget` 笔记列表的点击单选 / 多选 / Shift 区间选 / Command 跳选 / 拖动 等选择事件
>
> 关注点：
>
> 1. 各类选择操作的函数调用链（含拖动）
> 2. `current_note_id` / `prev_note_id` 的设置变化流程
> 3. `_handle_previous_note_cleanup` 调用时 `current_note_id` 与 `prev_note_id` 不相等的场景
> 4. **编辑器即时保存机制 → 重新审视"切换前再保存"的必要性**
> 5. 选择相关操作的潜在 Bug

---

## 一、`NoteListWidget` 类定义

- **位置**：`encnotes/main_window.py:768`
- **继承**：`QListWidget`

### 1.1 类内部状态

```python
self.last_selected_row = None     # Shift 多选锚点
self.press_pos = None             # 鼠标按下位置
self.press_row = None             # 鼠标按下时的行号
self.was_in_multi_select = False  # 按下时是否处于多选状态
```

### 1.2 重写的事件方法

| 方法 | 行号 | 用途 |
|---|---|---|
| `paintEvent` | 790 | 自绘分隔线 |
| `mousePressEvent` | 940 | 分发到 4 种点击处理器 |
| `mouseReleaseEvent` | 1018 | 处理点击 / 拖动判别 |
| `contextMenuEvent` | 1043 | 右键菜单 |

### 1.3 信号连接

```python
# main_window.py:1840
self.note_list.currentItemChanged.connect(self.on_note_selected)
```

**仅连接** `currentItemChanged`，未连接 `itemClicked` / `itemSelectionChanged`。

---

## 二、4 种选择操作的完整调用链

### 2.1 普通点击（单选）

```
mousePressEvent (940)
  └─ _handle_normal_press (912)
       ├─ [若点击的项已在多选集合中] _keep_multi_select_for_drag (892)
       │    ├─ blockSignals(True) → setCurrentRow → blockSignals(False)
       │    └─ _update_visual_selection
       │       （此时不会触发 on_note_selected）
       └─ [否则] main_window.select_single_note (5164)
            ├─ _clear_all_selections
            ├─ selected_note_rows = {row}
            ├─ if _get_current_note_id(): save_current_note()      ← 保存旧笔记
            ├─ blockSignals(True) → setCurrentItem → blockSignals(False)
            ├─ _set_current_note_id(note_id)                       ← 设为新 id
            └─ _load_and_display_note(note_id)                     ← 加载新笔记

mouseReleaseEvent (1018)
  └─ [若 was_in_multi_select 且没有拖动] _handle_click_in_multi_select (1005)
       └─ select_single_note(press_row)                            ← 真正切换到单选
```

### 2.2 Shift + 点击（区间多选）

```
mousePressEvent (940)
  └─ _handle_shift_press (870)
       └─ main_window.select_note_range(last_selected_row, clicked_row)  (5224)
            ├─ _clear_all_selections
            ├─ selected_note_rows = {min..max}
            ├─ blockSignals(True) → setCurrentItem(end_row) → blockSignals(False)
            ├─ _set_current_note_id(note_id)                       ← 直接覆盖，未保存旧笔记
            └─ editor.setHtml(note['content'])                     ← 未走 _load_and_display_note
```

> ⚠️ 此调用链**没有调用 `save_current_note`**，旧笔记的修改未保存。

### 2.3 Command / Ctrl + 点击（跳选）

```
mousePressEvent (940)
  └─ _handle_command_press (860)
       └─ main_window.toggle_note_selection (5193)
            ├─ [若已选中] selected_note_rows.discard(row)
            │    └─ [若变空] save_current_note() → _set_current_note_id(None) → editor.clear()
            └─ [若未选中] save_current_note()                       ← 保存旧笔记
                 ├─ selected_note_rows.add(row)
                 ├─ blockSignals(True) → setCurrentItem → blockSignals(False)
                 ├─ _set_current_note_id(note_id)
                 └─ _load_and_display_note(note_id)
```

### 2.4 键盘上下箭头切换（QListWidget 默认行为）

```
QListWidget.keyPressEvent (未重写)
  └─ Qt 内部调用 setCurrentItem
       └─ 触发 currentItemChanged 信号                              ← 唯一真正走 on_note_selected 的路径
            └─ on_note_selected(current, previous)  (5119)
                 ├─ _handle_previous_note_cleanup(previous)         ← previous 是旧 item
                 │    ├─ prev_note_id = previous.data(...)
                 │    ├─ _update_item_widget_selection(previous, False)
                 │    ├─ current_note_id = _get_current_note_id()   ← 此时还是旧 id
                 │    ├─ if current_note_id != prev_note_id: return（守卫）
                 │    ├─ save_current_note(note_id=prev_note_id)
                 │    └─ _cleanup_note_attachment_trash(prev_note_id)
                 ├─ _update_item_widget_selection(current, True)
                 ├─ _set_current_note_id(current_id)
                 └─ _load_and_display_note(current_id)
```

### 2.5 拖动笔记到文件夹（NoteList → FolderList）

#### 配置

```python
# main_window.py:1756-1761
self.note_list.setDragEnabled(True)
self.note_list.setAcceptDrops(False)                                # 笔记列表不接受 drop
self.note_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)   # 只读拖出
# main_window.py:1610-1620
self.folder_list.setDragEnabled(True)
self.folder_list.setAcceptDrops(True)
self.folder_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
self.folder_list.setDefaultDropAction(Qt.DropAction.MoveAction)
```

笔记拖动 = NoteList 起拖、FolderList 接收，FolderList 才是 dropEvent 的承担者。

#### 完整事件序列

```
NoteListWidget.mousePressEvent (940)
  └─ _handle_normal_press / _handle_command_press / _handle_shift_press
       └─ 设置 selected_note_rows、记录 press_pos / press_row / was_in_multi_select

NoteListWidget.mouseMoveEvent (Qt 默认未重写)
  └─ 当移动距离超过 QApplication.startDragDistance() 时
       └─ Qt 调用 NoteListWidget.startDrag(supported_actions)（默认未重写）
            └─ 携带 application/x-qabstractitemmodeldatalist MIME 数据进入拖动循环

FolderListWidget.dragEnterEvent / dragMoveEvent (106)
  └─ _validate_drag_source → _handle_note_drag_move
       └─ 仅对文件夹 item 给出"在其上"的指示器；空白处 / 非文件夹 ignore()

[用户松开鼠标 → 仅触发以下两条路径之一]
（A）落在合法目标   → FolderListWidget.dropEvent (723)
（B）落在非法目标 / ESC → NoteListWidget.mouseReleaseEvent

(A) FolderListWidget.dropEvent (723)
     ├─ _get_drag_source_data: 读取 selected_note_rows 得到 src_note_ids
     │    若多选: 取 selected_note_rows
     │    若单选: 取 currentItem 的 UserRole
     ├─ _handle_note_drop (583)
     │    ├─ for note_id in reversed(src_note_ids):
     │    │     note_manager.move_note_to_folder(note_id, target_folder_id)
     │    └─ QTimer.singleShot(50, _delayed_refresh_note_ui)
     │          ├─ load_folders()
     │          ├─ load_notes(...)                ← 内部 setCurrentItem 可能触发 currentItemChanged
     │          └─ 重新选中拖出的目标笔记

(B) NoteListWidget.mouseReleaseEvent (1018)
     ├─ press_pos != None 且 was_in_multi_select == True
     ├─ _is_click_not_drag(release_pos): 距离 > 5 → False
     │    （拖动情况下不会进入 _handle_click_in_multi_select）
     └─ _clear_press_info
```

#### 拖动期间 `current_note_id` 的状态

| 阶段 | `_current_note_id` | 编辑器内容 | 备注 |
|---|---|---|---|
| press 之前 | A（用户当前看的笔记） | A 的 HTML | |
| press（多选项被点） | A | A | `_keep_multi_select_for_drag` 用 blockSignals 改 currentItem，不动 _current_note_id |
| 拖动中 | A | A | Qt 仅做拖动循环 |
| drop 完成（数据库迁移） | A | A | 数据库更新但内存 _current_note_id 仍是 A |
| `_delayed_refresh_note_ui` 之后 | 取决于 `load_notes` 的 setCurrentItem 是否触发信号 | 取决于是否走 `_load_and_display_note` | **可能产生新的 cleanup 调用** |

#### 拖动相关已知 / 潜在问题

- **B1 ⚠️ 多选拖动时被拖项不一定包含 `_current_note_id`**：
  Cmd 跳选可能让 `selected_note_rows` 不包含当前 `_current_note_id` 对应行，但 `_get_drag_source_data` 直接遍历 `selected_note_rows`，结果是"拖了 ABC 但编辑器一直显示 D"。drop 后 D 仍在原文件夹，ABC 被搬走。这是当前行为，**未必是 bug，但易引起用户困惑**。
- **B2 ⚠️ drop 之后没有显式调用 `save_current_note`**：
  如果用户编辑了 A，正在拖动 ABC（A 被拖走），`_handle_note_drop` 仅做数据库移动，最后 `_delayed_refresh_note_ui` 走 `load_notes`。`load_notes` 内部的 setCurrentItem 触发 `currentItemChanged` → `on_note_selected` 才走到 `_handle_previous_note_cleanup` 才保存 A。一旦 `load_notes` 触发的 previous 与 `_get_current_note_id()` 不一致（场景 A），守卫 return，**A 的最新编辑会丢失**。
- **B3 拖动后的"重新选中"链路**：
  `_delayed_refresh_note_ui` 重新填充列表后 setCurrentItem 时，是否 blockSignals 没在拖动路径里再次确认；如果没 block，会触发 `on_note_selected`，previous 是旧 widget item（已 deleteLater），prev_note_id 是 A，_get_current_note_id() 仍是 A → cleanup 通过守卫 → 触发 `save_current_note(note_id=A)`，此时编辑器显示的还是 A，是**正确**的。这条路径反而是拖动场景下 A 唯一的保存机会。
- **B4 ESC 取消拖动**：
  Qt 取消拖动时既不触发 dropEvent 也不一定触发 mouseReleaseEvent（行为依赖平台）。`press_pos`、`was_in_multi_select` 的清理依赖 mouseReleaseEvent，可能残留状态污染下一次点击判定（实际测试在 macOS 上可观测到偶发现象）。

---

## 三、`current_note_id` / `previous_note_id` 状态流转

### 3.1 `_current_note_id` 的实现（main_window.py:4673-4701）

注意它**不是单一变量**，而是按视图分桶：

```python
self._last_note_per_view: dict[view_key, note_id]
# view_key 形如 "folder:xxx" / "system:all_notes" / "tag:xxx"
```

所以 `_get_current_note_id()` 返回的是**当前视图**的最近笔记 id；切换文件夹时整个 key 都变了。

### 3.2 各路径下的状态变化对比

| 操作路径 | 旧 id 是否保存 | `_set_current_note_id` 时机 | `previous_item` 来源 |
|---|---|---|---|
| **键盘 ↑↓**（走信号） | 走 `_handle_previous_note_cleanup` 内保存 | cleanup 之后 | Qt 信号传入 |
| **普通点击新行** | `select_single_note` 主动保存 | blockSignals 内 setCurrentItem 之后 | 信号被阻塞，无 |
| **Shift 区间** | ❌ **未保存** | blockSignals 内 setCurrentItem 之后 | 信号被阻塞，无 |
| **Cmd 跳选（新增）** | 主动保存 | blockSignals 内 setCurrentItem 之后 | 信号被阻塞，无 |
| **拖动判别后的兜底** | 走 `select_single_note` | 同上 | 同上 |

---

## 四、`_handle_previous_note_cleanup` 何时 prev / cur 不相等

代码位置：`main_window.py:4955-4999`

```python
prev_note_id = previous_item.data(Qt.ItemDataRole.UserRole)
current_note_id = self._get_current_note_id()
if current_note_id != prev_note_id:
    logger.warning(...)
    return  # 跳过保存
```

### 4.1 触发不相等的具体场景

| # | 场景 | 原因 |
|---|---|---|
| **A** | **文件夹切换 → 新文件夹有上次笔记** | `on_folder_changed` 调用 `load_notes(last_note_id)`，内部 `setCurrentItem(新视图笔记)` 触发 `currentItemChanged`。此时 `_get_current_view_key()` 已是新视图，`_get_current_note_id()` 返回的是新视图的笔记 id，与 `prev_note_id`（旧视图的笔记）必然不同。注释 4978-4979 也明确指出了这点。 |
| **B** | **删除当前笔记后** | 4577-4578：删除时 `_set_current_note_id(None)`，之后列表重新选中后触发信号，previous 是已删除项的旧 widget item，cur 是新值 |
| **C** | **`load_notes` 期间多次 setCurrentItem** | load_notes 多处 setCurrentItem 触发信号（2462、2477）；如果其中某次没有 blockSignals，previous 与 `_current_note_id` 可能错位 |

### 4.2 核心问题根因

`_get_current_note_id()` **不是真正"当前编辑器中显示的笔记"**，而是"当前视图的最近笔记"。两者在视图切换瞬间会不一致，导致守卫 return 跳过保存。

---

## 五、发现的 Bug 列表（按严重程度排列）

### Bug #1 ⚠️【高危】Shift 多选未保存旧笔记，会丢失未保存内容

- **位置**：`select_note_range` (5224-5255)

- **触发步骤**：
  1. 用户编辑笔记 A（已修改但未触发自动保存，或正处于 debounce 间隔）
  2. 用户 Shift + 点击笔记 D 进行区间选择
  3. `_handle_shift_press → select_note_range`，**该函数从头到尾没调用 `save_current_note`**
  4. 直接 `editor.setHtml(note['content'])` 用 D 的内容覆盖了 A 的内容
  5. **A 的修改永久丢失**

- **对比**：`select_single_note` (5178-5179) 和 `toggle_note_selection` (5207-5208) 都在切换前主动调用 `save_current_note`，唯独 `select_note_range` 漏了。

- **修复建议**：

  ```python
  def select_note_range(self, start_row, end_row):
      self._clear_all_selections()
      # 修复：先保存当前笔记
      if self._get_current_note_id():
          self.save_current_note()
      ...
  ```

---

### Bug #2 ⚠️【高危】Shift 多选未走 `_load_and_display_note`，跳过光标恢复 / 旧格式清理 / 编辑器初始化标志

- **位置**：`select_note_range` (5251-5253)

  ```python
  self.editor.blockSignals(True)
  self.editor.setHtml(note['content'])
  self.editor.blockSignals(False)
  ```

- **对比 `_load_and_display_note` (5075) 还会做**：
  - `restore_cursor_position(note)` — 恢复光标位置
  - `_editor_initialized = True` — 关键标志
  - `logger.info` 记录加载

- **影响**：
  - Shift 选择后，光标停留在 HTML 顶部，不在用户上次保存的位置
  - 若 `_editor_initialized` 还是 False，后续 `save_current_note` 会被 5465-5466 行的检查直接跳过 → **保存被静默跳过**
  - 旧版 `MinimumHeight` 等格式清理也会被绕过

- **修复建议**：将这三行替换为 `self._load_and_display_note(note_id)`。

---

### Bug #3 ⚠️【中危】`_handle_previous_note_cleanup` 在视图切换时跳过保存可能丢数据

- **位置**：4984-4989

  ```python
  if current_note_id != prev_note_id:
      logger.warning(...)
      return  # 跳过保存
  ```

- **触发**：场景 A（文件夹切换）。此时 `prev_note_id` 是旧文件夹的笔记，编辑器里此刻显示的可能仍然是它（如果新视图笔记还没 setHtml 完）。

- **问题分析**：
  - 注释声称「编辑器内容已属于 current_note_id，由 `on_folder_changed` 负责保存」
  - 但 `on_folder_changed` (4825-4837) 仅在「目标视图为空」时才保存；「目标视图有笔记」时它依赖 `on_note_selected` 来保存——而 `on_note_selected` 在这条 if 分支里又**直接 return 跳过保存**
  - 形成**死角**：旧文件夹笔记 A 被编辑 → 切换到新文件夹（新文件夹有上次笔记 B）→ A 既没在 `on_folder_changed` 里保存（因为 will_have_notes=True），又没在 `_handle_previous_note_cleanup` 里保存（因为守卫 return）→ **A 丢数据**

- **修复建议**：把 `on_folder_changed` 中 `will_have_notes=True` 分支改成无条件 `self.save_current_note()`，保证旧笔记一定保存；或者在 `_handle_previous_note_cleanup` 守卫 return 之前用 prev_note_id 显式保存一次。

---

### Bug #4【中危】多选 → 单选切换的状态一致性

- **触发链**：
  1. Shift 选 [A,B,C,D]（执行 `select_note_range`，`_set_current_note_id(D)`，编辑器显示 D）
  2. 用户编辑 D
  3. 普通点击 B（`_handle_normal_press` → `_is_item_in_multi_select(B)` 为真 → `_keep_multi_select_for_drag`）
  4. 鼠标释放 → `_handle_click_in_multi_select` → `select_single_note(B)`
  5. `select_single_note` 5178：`if self._get_current_note_id(): save_current_note()` — 此时 `_get_current_note_id()` 返回 D，保存的就是 D，是正确的 ✅

- **结论**：此路径在隔离场景下逻辑正确。**但 Bug #1 + Bug #2 已在 `select_note_range` 时埋下隐患**——D 的 `_editor_initialized` 可能没被正确触发，5465 处会跳过保存。

---

### Bug #5【低危】`toggle_note_selection` 的 `editor.clear()` 不会复位 `_editor_initialized`

- **位置**：5202-5203

  ```python
  self._set_current_note_id(None)
  self.editor.clear()
  ```

- **问题**：这里 `editor.clear()` 后没改 `_editor_initialized`。下次再选笔记走 `_load_and_display_note` 没问题（它会重新置 True）。但若中间有 `save_current_note` 被异步触发，会去保存 `note_id=None` 的笔记，需检查 `save_current_note` 对 `note_id=None` 的兜底（5460-5461 注释说会用 `_get_current_note_id()`，此时是 None，应该会早 return，但需要验证）。

---

### Bug #6【低危】`_handle_normal_press` 把已在多选集合的项当作"保持多选"，导致状态不一致

- **位置**：925-935

  ```python
  if is_in_multi_select:
      self._keep_multi_select_for_drag(...)  # 不切换
  else:
      self.main_window.select_single_note(...)  # 切换
  ```

- **问题**：用户多选 [A,B,C] 后想单击 B 切换到只看 B。第一次 mousePress 走 `_keep_multi_select_for_drag`，需要 mouseRelease 时根据「不是拖动」才会切换（1031-1035）。这依赖 `was_in_multi_select=True` 且没拖动。逻辑链较脆弱：
  - 若 `selected_note_rows` 只剩 1 项，`was_in_multi_select = len > 1 = False`（902 行判断），mouseRelease 不会触发切换 → 用户点 B 不会重新加载 B 内容（虽然已经在显示 B，影响小）
  - 如果点 A（不是当前 currentItem），press 时 `setCurrentRow(A)` 改 currentItem 但 blockSignals 阻断 on_note_selected → 编辑器还显示 B，但 currentItem 变成 A → **状态不一致**

- **评估**：状态不一致 bug，但通常用户会马上松开鼠标触发 release 路径，影响有限。

---

## 六、总结建议

按优先级修复：

1. **Bug #1, #2（必修）**：在 `select_note_range` 头部加 `save_current_note()`，把 setHtml 三行换成 `_load_and_display_note(note_id)`
2. **Bug #3（必修）**：让 `on_folder_changed` 在切换前**无条件保存**当前笔记，不要依赖下游的 `on_note_selected` 路径
3. **架构建议**：把"当前编辑器显示的笔记 id"和"视图的最近笔记 id"用**两个独立变量**管理：
   - 前者代表编辑器真实状态，用于保存判断
   - 后者用于视图记忆
   - 这样可以彻底消除 `_handle_previous_note_cleanup` 里 prev != current 的歧义

---

## 附录：关键文件 / 行号速查

| 名称 | 文件 | 行号 |
|---|---|---|
| `NoteListWidget` 类 | `main_window.py` | 768 |
| `mousePressEvent` | `main_window.py` | 940 |
| `mouseReleaseEvent` | `main_window.py` | 1018 |
| `_handle_normal_press` | `main_window.py` | 912 |
| `_handle_shift_press` | `main_window.py` | 870 |
| `_handle_command_press` | `main_window.py` | 860 |
| `_keep_multi_select_for_drag` | `main_window.py` | 892 |
| `_handle_click_in_multi_select` | `main_window.py` | 1005 |
| `_get_current_note_id` / `_set_current_note_id` | `main_window.py` | 4673-4701 |
| `on_note_selected` | `main_window.py` | 5119 |
| `_handle_previous_note_cleanup` | `main_window.py` | 4955-4999 |
| `select_single_note` | `main_window.py` | 5164 |
| `toggle_note_selection` | `main_window.py` | 5193 |
| `select_note_range` | `main_window.py` | 5224 |
| `_load_and_display_note` | `main_window.py` | 5044 |
| `currentItemChanged` 连接 | `main_window.py` | 1840 |
| `on_folder_changed` | `main_window.py` | 4825-4837 |
