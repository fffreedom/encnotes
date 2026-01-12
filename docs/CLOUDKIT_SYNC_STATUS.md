# CloudKit 同步状态报告

## 📋 当前状态

**日期**: 2026-01-11  
**问题**: 原生 CloudKit 在 Python/Qt 环境中崩溃（Illegal instruction: 4）  
**根本原因**: CloudKit 框架需要特定的运行环境（主线程 + RunLoop + 沙盒权限）

---

## 🔍 问题分析

### 尝试过的方案

#### 1. ❌ PyObjC 直接调用
```python
from CloudKit import CKContainer
container = CKContainer.containerWithIdentifier_("iCloud.com.encnotes.app")
# 崩溃: Illegal instruction: 4
```

**失败原因**:
- Python 线程环境不满足 CloudKit 要求
- 缺少 Objective-C RunLoop
- NSObject 继承问题

#### 2. ❌ Swift 脚本桥接
```bash
swift cloudkit_bridge.swift check-account
# 崩溃: Illegal instruction: 4
```

**失败原因**:
- 命令行工具默认没有 RunLoop
- 即使添加 RunLoop.current.run() 仍然崩溃
- 可能与沙盒权限有关

#### 3. ❌ Swift 编译可执行文件
```bash
swiftc -o cloudkit_bridge cloudkit_bridge.swift
./cloudkit_bridge check-account
# 崩溃: Illegal instruction: 4
```

**失败原因**:
- 独立可执行文件缺少必要的 entitlements
- 没有 iCloud 容器权限
- 无法访问用户的 iCloud 账户

---

## ✅ 可行方案

### 方案 1: 使用 iCloud Drive 文件同步（推荐）⭐

**原理**: 不使用 CloudKit API，而是直接读写 iCloud Drive 目录

```python
import os
from pathlib import Path

# iCloud Drive 路径
icloud_drive = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
sync_dir = icloud_drive / "encnotes"

# 保存笔记到 iCloud Drive
def save_note_to_icloud(note):
    note_file = sync_dir / f"{note['id']}.json"
    with open(note_file, 'w') as f:
        json.dump(note, f)
    # macOS 会自动同步到 iCloud
```

**优点**:
- ✅ 简单可靠，无需 CloudKit API
- ✅ 自动同步，macOS 系统负责
- ✅ 用户数据存储在自己的 iCloud Drive
- ✅ 无需开发者账户
- ✅ 完全去中心化

**缺点**:
- ⚠️ 需要用户手动启用 iCloud Drive
- ⚠️ 冲突解决需要自己实现
- ⚠️ 无法使用 CloudKit 的高级功能（订阅、推送等）

**实现难度**: ⭐⭐ (简单)

---

### 方案 2: 创建独立的 macOS 应用（最佳）⭐⭐⭐

**原理**: 将 encnotes 打包成真正的 macOS .app，配置正确的 entitlements

**步骤**:

1. **创建 Xcode 项目**
   - 使用 SwiftUI 或 AppKit
   - 嵌入 Python 运行时
   - 配置 iCloud 容器

2. **配置 Entitlements**
   ```xml
   <!-- encnotes.entitlements -->
   <key>com.apple.developer.icloud-container-identifiers</key>
   <array>
       <string>iCloud.com.encnotes.app</string>
   </array>
   <key>com.apple.developer.icloud-services</key>
   <array>
       <string>CloudKit</string>
   </array>
   ```

3. **Swift 封装 CloudKit**
   ```swift
   // CloudKitManager.swift
   class CloudKitManager {
       func syncNotes() {
           // CloudKit 操作
       }
   }
   ```

4. **Python 调用 Swift**
   - 使用 PyObjC 桥接
   - 或使用 subprocess 调用

**优点**:
- ✅ 完整的 CloudKit 功能
- ✅ 正确的沙盒权限
- ✅ 可以上架 Mac App Store
- ✅ 用户体验最佳

**缺点**:
- ⚠️ 需要 $99/年开发者账户（分发时）
- ⚠️ 开发复杂度高
- ⚠️ 需要学习 Swift/Xcode

**实现难度**: ⭐⭐⭐⭐⭐ (复杂)

---

### 方案 3: CloudKit Web Services（备选）⭐⭐

**原理**: 使用 HTTP REST API 访问 CloudKit

```python
import requests

def push_note_to_cloudkit(note):
    url = "https://api.apple-cloudkit.com/database/1/iCloud.com.encnotes.app/development/public/records/modify"
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    data = {
        "operations": [{
            "operationType": "create",
            "record": {
                "recordType": "Note",
                "fields": {
                    "title": {"value": note['title']},
                    "content": {"value": note['content']}
                }
            }
        }]
    }
    response = requests.post(url, json=data, headers=headers)
```

**优点**:
- ✅ 跨平台支持
- ✅ 不需要原生 SDK
- ✅ 可以在 Python 中直接使用

**缺点**:
- ❌ **数据存储在开发者的容器**（不符合你的需求）
- ❌ 需要管理 API Token
- ❌ 用户数据集中式存储
- ❌ 占用开发者的 CloudKit 配额

**实现难度**: ⭐⭐⭐ (中等)

**⚠️ 不推荐**: 因为你希望用户使用自己的 iCloud 空间

---

## 🎯 最终建议

### 短期方案（立即可用）

**使用 iCloud Drive 文件同步**

1. 创建 `icloud_drive_sync.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iCloud Drive 文件同步实现
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

class iCloudDriveSync:
    """iCloud Drive 同步管理器"""
    
    def __init__(self, note_manager):
        self.note_manager = note_manager
        
        # iCloud Drive 路径
        self.icloud_drive = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        self.sync_dir = self.icloud_drive / "encnotes"
        
        # 创建同步目录
        if self.icloud_drive.exists():
            self.sync_dir.mkdir(exist_ok=True)
            self.available = True
        else:
            self.available = False
    
    def is_available(self) -> bool:
        """检查 iCloud Drive 是否可用"""
        return self.available and self.icloud_drive.exists()
    
    def push_notes(self, notes: List[Dict]) -> Tuple[bool, str]:
        """推送笔记到 iCloud Drive"""
        if not self.is_available():
            return False, "iCloud Drive 不可用"
        
        try:
            for note in notes:
                note_file = self.sync_dir / f"{note['id']}.json"
                with open(note_file, 'w', encoding='utf-8') as f:
                    json.dump(note, f, ensure_ascii=False, indent=2)
            
            return True, f"已保存 {len(notes)} 条笔记到 iCloud Drive"
        except Exception as e:
            return False, f"保存失败: {e}"
    
    def pull_notes(self) -> Tuple[bool, List[Dict]]:
        """从 iCloud Drive 拉取笔记"""
        if not self.is_available():
            return False, []
        
        try:
            notes = []
            for note_file in self.sync_dir.glob("*.json"):
                with open(note_file, 'r', encoding='utf-8') as f:
                    note = json.load(f)
                    notes.append(note)
            
            return True, notes
        except Exception as e:
            print(f"拉取失败: {e}")
            return False, []
    
    def merge_notes(self, remote_notes: List[Dict]) -> int:
        """合并远程笔记"""
        merged_count = 0
        
        for remote_note in remote_notes:
            note_id = remote_note['id']
            local_note = self.note_manager.get_note(note_id)
            
            if not local_note:
                # 创建新笔记
                self.note_manager.create_note(
                    title=remote_note['title'],
                    content=remote_note['content']
                )
                merged_count += 1
            elif remote_note['_cocoa_modified'] > local_note['_cocoa_modified']:
                # 更新笔记
                self.note_manager.update_note(
                    note_id,
                    title=remote_note['title'],
                    content=remote_note['content']
                )
                merged_count += 1
        
        return merged_count
```

2. 修改 `icloud_sync.py`，使用 iCloud Drive 同步：

```python
# 在 __init__ 中
if NATIVE_CLOUDKIT_AVAILABLE:
    # 尝试原生 CloudKit
    pass
else:
    # 使用 iCloud Drive
    from icloud_drive_sync import iCloudDriveSync
    self.drive_sync = iCloudDriveSync(note_manager)
    if self.drive_sync.is_available():
        self.use_drive = True
        print("✓ 使用 iCloud Drive 同步")
```

**优点**:
- 立即可用，无需等待
- 简单可靠
- 符合你的需求（用户自己的 iCloud 空间）

---

### 长期方案（未来改进）

**创建独立的 macOS 应用**

1. 学习 Swift 和 Xcode
2. 创建 macOS 应用项目
3. 嵌入 Python 运行时
4. 配置 CloudKit 权限
5. 实现完整的 CloudKit 同步

**时间投入**: 2-4 周  
**收益**: 完整的 iCloud 同步功能 + 可上架 App Store

---

## 📊 方案对比

| 方案 | 实现难度 | 开发时间 | 用户体验 | 是否符合需求 | 推荐度 |
|------|---------|---------|---------|------------|--------|
| iCloud Drive 文件同步 | ⭐⭐ | 1天 | ⭐⭐⭐⭐ | ✅ | ⭐⭐⭐⭐⭐ |
| 独立 macOS 应用 | ⭐⭐⭐⭐⭐ | 2-4周 | ⭐⭐⭐⭐⭐ | ✅ | ⭐⭐⭐⭐ |
| CloudKit Web Services | ⭐⭐⭐ | 3-5天 | ⭐⭐⭐ | ❌ | ⭐⭐ |
| 继续调试 PyObjC | ⭐⭐⭐⭐⭐ | 未知 | ❓ | ✅ | ⭐ |

---

## 🚀 行动计划

### 立即执行（今天）

1. ✅ 实现 `icloud_drive_sync.py`
2. ✅ 修改 `icloud_sync.py` 集成 iCloud Drive 同步
3. ✅ 测试同步功能
4. ✅ 更新用户界面提示

### 短期计划（本周）

1. 完善冲突解决机制
2. 添加同步状态指示器
3. 优化同步性能
4. 编写用户文档

### 长期计划（未来）

1. 学习 Swift 和 Xcode
2. 创建独立 macOS 应用
3. 实现完整 CloudKit 同步
4. 上架 Mac App Store

---

## 💡 总结

**当前最佳方案**: 使用 **iCloud Drive 文件同步**

**理由**:
1. ✅ 简单可靠，立即可用
2. ✅ 完全符合你的需求（用户自己的 iCloud 空间）
3. ✅ 无需开发者账户
4. ✅ 自动同步，用户体验好
5. ✅ 实现成本低

**CloudKit 原生 API 的问题**:
- 需要正确的沙盒权限和 entitlements
- 命令行工具无法获得这些权限
- 必须打包成 .app 才能正常工作
- 这需要大量额外工作

**结论**: 先使用 iCloud Drive 实现同步功能，让用户可以立即使用。未来有时间再考虑升级到完整的 macOS 应用。
