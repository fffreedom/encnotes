# 笔记推送流程说明

## 📋 概述

本文档详细说明 encnotes 应用中笔记推送到 iCloud 的完整流程，包括触发方式、调用链、关键代码和日志追踪方法。

## 🚀 推送触发方式

### 1. 手动触发（立即同步）

**操作路径**：菜单栏 → 同步 → 立即同步（快捷键：Ctrl+S）

**代码位置**：`main_window.py:4096`

```python
def sync_now(self):
    """立即同步到iCloud"""
    if not self.sync_manager.sync_enabled:
        QMessageBox.warning(self, "提示", "请先启用iCloud同步")
        return
        
    # 保存当前笔记
    self.save_current_note()
    
    # 执行同步
    success, message = self.sync_manager.sync_notes()
    
    if success:
        QMessageBox.information(self, "同步成功", message)
    else:
        QMessageBox.warning(self, "同步失败", message)
```

### 2. 自动触发（定时同步）

**触发间隔**：每 5 分钟自动执行一次

**代码位置**：`main_window.py:1158-1161`

```python
# 设置自动同步定时器（每5分钟）
self.sync_timer = QTimer()
self.sync_timer.timeout.connect(self.auto_sync)
self.sync_timer.start(300000)  # 5分钟 = 300000毫秒
```

## 🔄 完整调用链

```
用户点击"立即同步"
    ↓
MainWindow.sync_now()                    [main_window.py:4096]
    ↓
MainWindow.save_current_note()           [保存当前编辑的笔记]
    ↓
CloudKitSyncManager.sync_notes()         [icloud_sync.py:158]
    ↓
获取上次同步时间戳
    ↓
NoteManager.get_notes_modified_after()   [获取需要同步的笔记]
    ↓
CloudKitNativeSync.push_notes()          [cloudkit_native.py:202]
    ↓
将笔记转换为JSON
    ↓
_call_swift_bridge("push", ...)          [调用Swift桥接]
    ↓
subprocess.run(["swift", "cloudkit_bridge.swift", "push", ...])
    ↓
Swift脚本执行CloudKit API调用
    ↓
❌ Illegal instruction: 4 (崩溃)
```

## 📝 关键代码详解

### 第一步：检查同步状态

**文件**：`icloud_sync.py`

```python
def sync_notes(self) -> Tuple[bool, str]:
    """同步笔记到iCloud"""
    if not self.sync_enabled:
        return False, "同步未启用"
```

**日志输出**：
```
2026-01-11 15:30:15,385 INFO [cloudkit_native:305] 开始推送笔记，数量: 1
```

### 第二步：获取需要同步的笔记

**文件**：`icloud_sync.py`

```python
# 获取上次同步时间
last_sync = self.note_manager.get_sync_metadata('last_sync_timestamp')
last_sync_cocoa = float(last_sync) if last_sync else 0.0

# 获取需要同步的笔记（修改时间晚于上次同步）
modified_notes = self.note_manager.get_notes_modified_after(last_sync_cocoa)

if not modified_notes:
    return True, "没有需要同步的笔记"
```

**说明**：
- 只同步自上次同步后修改过的笔记（增量同步）
- 使用 Cocoa 时间戳格式（从 2001-01-01 开始的秒数）

### 第三步：调用原生 CloudKit

**文件**：`icloud_sync.py`

```python
# 使用原生CloudKit
if self.use_native and self.native_backend:
    def on_pushed(success, saved_count, message):
        """推送完成回调"""
        if success:
            # 更新同步时间
            now = datetime.now()
            cocoa_time = self.note_manager._timestamp_to_cocoa(now)
            self.note_manager.set_sync_metadata('last_sync_timestamp', str(cocoa_time))
            
            self.last_sync_time = now.isoformat()
            self.save_config()
            print(f"✓ {message}")
        else:
            print(f"✗ {message}")
    
    return self.native_backend.push_notes(modified_notes, on_pushed)
```

### 第四步：CloudKit 推送实现

**文件**：`cloudkit_native.py`

```python
def push_notes(self, notes: List[Dict], completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
    """推送笔记到CloudKit"""
    logger.info(f"开始推送笔记，数量: {len(notes) if notes else 0}")
    
    if not CLOUDKIT_STABLE:
        logger.error("CloudKit框架不可用")
        return False, "CloudKit框架不可用"
    
    if not self.sync_enabled:
        logger.warning("同步未启用")
        return False, "同步未启用"
    
    if self.is_syncing:
        logger.warning("正在同步中")
        return False, "正在同步中..."
    
    if not notes:
        logger.info("没有需要同步的笔记")
        return True, "没有需要同步的笔记"
    
    try:
        self.is_syncing = True
        logger.info("设置同步状态为True")
        
        # 将笔记转换为JSON
        notes_json = json.dumps(notes, ensure_ascii=False)
        
        # 调用Swift桥接推送
        success, result = self._call_swift_bridge("push", input_data=notes_json)
        
        # ... 处理结果
```

**日志输出**：
```
2026-01-11 15:30:15,385 INFO [cloudkit_native:305] 开始推送笔记，数量: 1
2026-01-11 15:30:15,385 INFO [cloudkit_native:313] CloudKit未初始化，开始初始化...
2026-01-11 15:30:15,386 INFO [cloudkit_native:106] 开始初始化CloudKit容器: iCloud.com.encnotes.app
2026-01-11 15:30:15,386 INFO [cloudkit_native:109] 正在创建CKContainer...
```

### 第五步：Swift 桥接调用

**文件**：`cloudkit_native.py`

```python
def _call_swift_bridge(self, action: str, input_data: Optional[str] = None) -> Tuple[bool, Any]:
    """调用Swift桥接脚本"""
    swift_script = Path(__file__).parent / "cloudkit_bridge.swift"
    
    cmd = ["swift", str(swift_script), action, self.container_id]
    if input_data:
        cmd.append(input_data)
    
    logger.debug(f"执行Swift命令: {' '.join(cmd[:3])}...")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # 返回码 -4 = Illegal instruction: 4
    if result.returncode != 0:
        logger.error(f"Swift脚本执行失败，返回码: {result.returncode}")
        return False, result.stderr
```

**问题所在**：
- Swift 脚本尝试调用 CloudKit 框架
- CloudKit 需要在真正的 macOS 应用环境中运行
- 命令行脚本无法满足 CloudKit 的运行要求
- 导致 `Illegal instruction: 4` 崩溃

## 🔍 日志追踪方法

### 查看实时日志

```bash
# 实时监控日志
tail -f ~/Library/Group\ Containers/group.com.encnotes/encnotes.log

# 或使用测试脚本
./test_cloudkit.sh run
```

### 关键日志标识

| 日志内容 | 含义 | 位置 |
|---------|------|------|
| `开始推送笔记，数量: N` | 开始推送流程 | cloudkit_native.py:305 |
| `CloudKit未初始化，开始初始化...` | 首次推送需要初始化 | cloudkit_native.py:313 |
| `正在创建CKContainer...` | 创建CloudKit容器 | cloudkit_native.py:109 |
| `Illegal instruction: 4` | Swift脚本崩溃 | 系统错误 |
| `成功上传 N 条笔记` | 推送成功（理想情况） | cloudkit_native.py |

### 完整日志示例

```log
2026-01-11 15:30:02,673 INFO [__main__:77] Logging initialized
2026-01-11 15:30:03,183 INFO [cloudkit_native:69] 开始初始化CloudKitNativeSync, container_id=iCloud.com.encnotes.app
2026-01-11 15:30:03,184 INFO [cloudkit_native:91] CloudKitNativeSync 实例创建成功（延迟初始化）
2026-01-11 15:30:03,184 INFO [stdout:59] ✓ 使用原生CloudKit实现

[用户点击"立即同步"]

2026-01-11 15:30:15,385 INFO [cloudkit_native:305] 开始推送笔记，数量: 1
2026-01-11 15:30:15,385 INFO [cloudkit_native:313] CloudKit未初始化，开始初始化...
2026-01-11 15:30:15,386 INFO [cloudkit_native:106] 开始初始化CloudKit容器: iCloud.com.encnotes.app
2026-01-11 15:30:15,386 INFO [cloudkit_native:109] 正在创建CKContainer...

[崩溃发生]
Illegal instruction: 4
```

## ⚠️ 当前问题

### 问题描述

当用户点击"立即同步"按钮时，应用会崩溃并显示 `Illegal instruction: 4` 错误。

### 根本原因

1. **CloudKit 运行环境限制**：
   - CloudKit 框架必须在真正的 macOS 应用环境中运行
   - 需要 Bundle ID、Entitlements、应用签名等
   - 命令行脚本（包括 Swift 脚本）无法满足这些要求

2. **当前架构问题**：
   - Python 应用通过 subprocess 调用 Swift 脚本
   - Swift 脚本尝试使用 CloudKit 框架
   - 系统拒绝执行，导致崩溃

### 影响范围

- ✅ 应用启动正常
- ✅ 所有笔记功能正常
- ✅ 本地存储正常
- ❌ **一旦点击同步按钮就会崩溃**

## 💡 解决方案

### 推荐方案：改用 iCloud Drive 文件同步

**优点**：
- ✅ 用户使用自己的 iCloud 账户
- ✅ 占用用户自己的 iCloud 空间
- ✅ 自动跨设备同步
- ✅ 去中心化架构
- ✅ 实现简单，1天即可完成
- ✅ 稳定可靠，不会崩溃

**实现方式**：
将笔记数据库保存到 iCloud Drive 目录：
```
~/Library/Mobile Documents/com~apple~CloudDocs/encnotes/
```

系统会自动处理同步，无需调用任何 CloudKit API。

### 替代方案：创建独立 macOS 应用

**缺点**：
- ❌ 需要 2-4 周开发时间
- ❌ 需要开发者账户（$99/年）
- ❌ 需要重写大量代码
- ❌ 维护成本高

## 🎯 测试推送功能

### 手动测试

1. 启动应用
2. 创建或编辑一条笔记
3. 点击菜单：同步 → 立即同步
4. 观察日志输出

### 使用测试脚本

```bash
# 运行测试脚本
./test_cloudkit.sh run

# 或直接运行Python测试
python test_cloudkit_init.py
```

### 模拟推送测试

```bash
# 创建测试脚本
cat > /tmp/test_push.py << 'EOF'
import subprocess
import json

notes = [{
    "identifier": "test-1",
    "title": "测试笔记",
    "content": "内容",
    "created": "2026-01-11T15:00:00Z",
    "modified": "2026-01-11T15:00:00Z"
}]

result = subprocess.run(
    ["swift", "cloudkit_bridge.swift", "push", "iCloud.com.encnotes.app", json.dumps(notes)],
    capture_output=True,
    text=True
)

print(f"返回码: {result.returncode}")
print(f"输出: {result.stdout}")
print(f"错误: {result.stderr}")
EOF

python /tmp/test_push.py
```

**预期结果**：返回码 `-4`（Illegal instruction: 4）

## 📚 相关文档

- [CloudKit 实现指南](CLOUDKIT_IMPLEMENTATION_GUIDE.md)
- [CloudKit 使用指南](CLOUDKIT_USAGE_GUIDE.md)
- [CloudKit 当前状态](CLOUDKIT_CURRENT_STATUS.md)
- [CloudKit 问题分析](CLOUDKIT_ISSUE_ANALYSIS.md)

## 🔧 调试技巧

### 1. 启用详细日志

在 `cloudkit_native.py` 中设置日志级别：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 2. 检查同步状态

```python
# 在Python控制台中
from icloud_sync import CloudKitSyncManager
from note_manager import NoteManager

nm = NoteManager()
sm = CloudKitSyncManager(nm)

print(f"同步已启用: {sm.sync_enabled}")
print(f"使用原生实现: {sm.use_native}")
print(f"后端可用: {sm.native_backend is not None}")
```

### 3. 查看需要同步的笔记

```python
# 获取需要同步的笔记
last_sync = nm.get_sync_metadata('last_sync_timestamp')
modified_notes = nm.get_notes_modified_after(float(last_sync) if last_sync else 0.0)

print(f"需要同步的笔记数量: {len(modified_notes)}")
for note in modified_notes:
    print(f"  - {note['title']} (修改时间: {note['_cocoa_modified']})")
```

## 📞 获取帮助

如果遇到问题：

1. 查看日志文件：`~/Library/Group Containers/group.com.encnotes/encnotes.log`
2. 运行测试脚本：`./test_cloudkit.sh run`
3. 查看相关文档（见上方"相关文档"部分）

---

**最后更新**：2026-01-11
