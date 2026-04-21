# 桌面程序测试方案设计

**日期**：2026-04-21  
**项目**：加密笔记（encnotes）— PyQt6 Mac 风格备忘录应用  
**状态**：待实现

---

## 背景

项目为基于 PyQt6 的 Mac 风格桌面备忘录应用，支持加密存储、iCloud 同步、富文本编辑、数学公式等功能。目前已有少量手动测试脚本（`test_editor.py`, `test_tags.py` 等），但缺乏系统化的自动化测试框架。

`computer-use-mcp` 工具每次使用时弹出辅助功能权限窗口，原因是 macOS 强制要求控制其他应用的工具必须在「系统设置 → 隐私与安全性 → 辅助功能」中授权。**解决方案**：在系统设置中手动为终端应用（Terminal/iTerm2/Warp）开启辅助功能权限，一次授权后永久有效。

---

## 目标

建立三层测试体系，覆盖所有核心功能：

1. **单元测试**：测试业务逻辑（加密、笔记管理、导出、附件）
2. **集成测试**：测试 Qt UI 组件交互（pytest-qt，进程内驱动）
3. **端到端测试**：测试真实应用启动与核心路径（computer-use-mcp）

---

## 目录结构

```
tests/
├── conftest.py                   # pytest 全局 fixtures（app、db、加密初始化）
├── unit/                         # 单元测试（纯逻辑，无 GUI）
│   ├── test_note_manager.py
│   ├── test_encryption_manager.py
│   ├── test_export_manager.py
│   └── test_attachment_manager.py
├── integration/                  # 集成测试（pytest-qt，进程内 Qt 交互）
│   ├── test_main_window.py
│   ├── test_note_editor.py
│   ├── test_tags_ui.py
│   └── test_password_dialog.py
├── e2e/                          # 端到端测试（computer-use-mcp，真实应用）
│   ├── test_launch.py            # 启动 + 解锁流程
│   └── test_smoke.py             # 核心路径冒烟测试
└── fixtures/                     # 测试数据（示例笔记、图片等）
```

---

## 工具栈

| 层级 | 工具 | 用途 |
|------|------|------|
| 单元 | `pytest` | 纯 Python 逻辑测试 |
| 集成 | `pytest-qt`（`qtbot`） | Qt 控件交互、信号测试 |
| 端到端 | `computer-use-mcp` | 真实应用截图 + 点击验证 |

---

## 第一层：单元测试

所有单元测试使用 `tmp_path` fixture 创建临时数据库，测试间完全隔离，可并行运行。加密测试使用固定测试密码，不依赖系统钥匙串。

### test_note_manager.py
- 创建/读取/更新/删除笔记（CRUD）
- 文件夹创建、重命名、删除
- 标签创建、关联笔记、按标签筛选
- 回收站：移入、恢复、清空

### test_encryption_manager.py
- 密码设置与验证
- 笔记内容加密/解密正确性
- 错误密码返回失败（不崩溃）
- PBKDF2 密钥派生参数验证（迭代次数 >= 100000）

### test_export_manager.py
- 导出为 PDF / Word / Markdown / HTML
- 含图片、表格、数学公式的笔记导出不报错
- 导出文件内容基本校验（文件非空、格式正确）

### test_attachment_manager.py
- 添加附件、获取附件列表
- 删除附件、孤立文件清理

---

## 第二层：集成测试（pytest-qt）

使用 `qtbot.addWidget()` 管理控件生命周期，测试后自动清理。用 `qtbot.keyClicks()` / `qtbot.mouseClick()` 模拟用户输入。信号测试用 `qtbot.waitSignal()` 捕获异步事件。主窗口测试 mock 掉 iCloud 同步，避免网络依赖。

### test_main_window.py
- 主窗口启动、三栏布局正确渲染
- 新建笔记 → 出现在笔记列表中
- 切换文件夹 → 笔记列表刷新
- 删除笔记 → 移入回收站

### test_note_editor.py
- 输入文本 → 内容正确保存
- 粗体/斜体/下划线快捷键触发格式变化
- 插入表格 → HTML 中出现 `<table>` 标签
- 粘贴图片 → 编辑器内显示图片
- LaTeX 公式插入 → 渲染为图片不报错

### test_tags_ui.py
- 创建标签、在笔记上添加标签
- 按标签筛选 → 列表只显示对应笔记

### test_password_dialog.py
- 首次启动弹出设置密码对话框
- 输入错误密码 → 提示错误，不进入主界面
- 输入正确密码 → 关闭对话框，进入主界面

---

## 第三层：端到端测试（computer-use-mcp）

### 前提条件（一次性操作）
「系统设置 → 隐私与安全性 → 辅助功能」→ 添加终端应用并开启开关。

### test_launch.py — 启动与解锁流程
- 启动应用 → 截图验证密码对话框出现
- 输入正确密码 → 截图验证主窗口三栏布局显示
- 锁定（Cmd+Shift+L）→ 截图验证回到锁定状态

### test_smoke.py — 核心路径冒烟测试
- 新建笔记 → 截图验证笔记出现在列表
- 在编辑器输入文字 → 截图验证内容显示
- 新建文件夹 → 截图验证文件夹列表更新
- 退出并重启应用 → 截图验证数据持久化（笔记仍存在）

### 设计原则
- 每个 e2e 测试前通过脚本重置测试数据库（独立测试路径），不影响真实数据
- 截图验证用区域截图 + 关键词/颜色检查，不依赖像素级对比
- e2e 测试标记为 `@pytest.mark.e2e`，默认不在普通 `pytest` 中运行，本地按需执行（`pytest -m e2e`）
- 每个步骤之间等待 UI 响应完成

---

## 运行方式

```bash
# 安装依赖
pip install pytest pytest-qt

# 运行单元 + 集成测试
pytest tests/unit tests/integration -v

# 运行端到端测试（需先授权辅助功能）
pytest tests/e2e -m e2e -v

# 运行全部测试
pytest tests/ -v
```

---

## 不在本方案范围内

- CI/CD 自动化集成（可后续扩展）
- iCloud 同步的真实网络测试（mock 替代）
- 性能/压力测试
