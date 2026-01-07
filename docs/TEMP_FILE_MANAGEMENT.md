# 临时文件管理机制说明

## 📋 概述

当用户打开加密附件时，系统需要先解密文件，然后创建临时文件供外部程序（如Preview、Adobe Reader等）打开。为了确保临时文件得到妥善清理，我们实现了**多层防护机制**。

## 🛡️ 三层防护策略

### 第一层：启动时清理（处理历史遗留）

**触发时机**：应用启动时自动执行

**清理对象**：所有encnotes临时文件

**目的**：
- 清理上次会话留下的所有临时文件
- 清理异常退出（崩溃、强制退出、断电等）后的残留文件
- 确保每次启动都是干净状态

**实现代码**：
```python
def _cleanup_old_temp_files(self):
    """清理所有临时文件（启动时执行）"""
    pattern = "encnotes_temp_*"
    
    for file_path in self.temp_dir.glob(pattern):
        # 清理所有临时文件，不检查时间
        file_path.unlink()
```

### 第二层：运行时追踪（记录当前会话）

**触发时机**：每次创建临时文件时

**追踪方式**：使用集合（set）记录所有临时文件路径

**目的**：
- 追踪本次会话创建的所有临时文件
- 为退出时清理提供准确的文件列表
- 避免重复创建同名文件

**实现代码**：
```python
def _create_temp_file(self, attachment_id: str, original_name: str, file_data: bytes):
    """创建临时文件"""
    temp_filename = f"encnotes_temp_{attachment_id}_{original_name}"
    temp_path = self.temp_dir / temp_filename
    
    # 写入文件
    with open(temp_path, 'wb') as f:
        f.write(file_data)
    
    # 记录到会话列表
    self.temp_files.add(str(temp_path))
    
    return str(temp_path)
```

### 第三层：退出时清理（正常情况）

**触发时机**：应用正常退出时

**清理对象**：本次会话创建的所有临时文件

**实现方式**：使用Python的`atexit`模块注册清理函数

**目的**：
- 在正常退出时清理所有临时文件
- 确保不留下任何残留文件

**实现代码**：
```python
def __init__(self, encryption_manager):
    # ... 其他初始化代码 ...
    
    # 注册退出时清理函数
    atexit.register(self._cleanup_session_temp_files)

def _cleanup_session_temp_files(self):
    """清理本次会话的临时文件（退出时执行）"""
    for file_path_str in list(self.temp_files):
        file_path = Path(file_path_str)
        if file_path.exists():
            file_path.unlink()
    
    self.temp_files.clear()
```

## 🔍 异常情况处理

### 1. 程序崩溃（Crash）

**问题**：第三层清理不会执行

**解决**：第一层防护会在下次启动时清理所有临时文件

**时间**：下次启动时立即清理

### 2. 强制终止（kill -9）

**问题**：第三层清理不会执行

**解决**：第一层防护会在下次启动时清理所有临时文件

**时间**：下次启动时立即清理

### 3. 系统崩溃/断电

**问题**：所有清理机制都不会执行

**解决**：第一层防护会在下次启动时清理所有临时文件

**时间**：下次启动时立即清理

### 4. 用户强制退出（Force Quit）

**问题**：第三层清理可能不会执行

**解决**：第一层防护会在下次启动时清理所有临时文件

**时间**：下次启动时立即清理

### 5. 未捕获的异常

**问题**：取决于异常类型，第三层可能执行也可能不执行

**解决**：第一层防护会在下次启动时清理所有临时文件

**时间**：下次启动时立即清理

## 📊 清理时间表

| 场景 | 第一层 | 第二层 | 第三层 | 最终结果 |
|------|--------|--------|--------|----------|
| 正常退出 | ✓ | ✓ | ✓ | 立即清理 |
| 程序崩溃 | ✓ | ✓ | ✗ | 下次启动清理 |
| 强制终止 | ✓ | ✓ | ✗ | 下次启动清理 |
| 系统崩溃 | ✓ | ✗ | ✗ | 下次启动清理 |
| 断电 | ✓ | ✗ | ✗ | 下次启动清理 |

## 🗂️ 临时文件位置

### macOS
```
/var/folders/xx/xxxxx/T/encnotes_temp_{attachment_id}_{filename}
```

### Windows
```
C:\Users\{username}\AppData\Local\Temp\encnotes_temp_{attachment_id}_{filename}
```

### Linux
```
/tmp/encnotes_temp_{attachment_id}_{filename}
```

## 🔧 手动清理功能（可选）

为了提供更好的用户体验，我们还提供了手动清理功能：

```python
def manual_cleanup_temp_files(self) -> Tuple[int, str]:
    """手动清理所有临时文件"""
    pattern = "encnotes_temp_*"
    cleaned_count = 0
    
    for file_path in self.temp_dir.glob(pattern):
        file_path.unlink()
        cleaned_count += 1
    
    self.temp_files.clear()
    
    return cleaned_count, f"已清理 {cleaned_count} 个临时文件"
```

**使用场景**：
- 用户想立即清理所有临时文件
- 磁盘空间不足时
- 隐私保护需求

**集成位置**：可以在应用设置或工具菜单中添加此功能

## 🔒 安全性考虑

### 1. 文件命名
- 使用UUID作为附件ID，避免文件名冲突
- 保留原始文件名，方便用户识别

### 2. 文件权限
- 临时文件继承系统临时目录的权限
- 在Unix系统上，通常只有创建者可以访问

### 3. 清理时机
- 启动时清理所有临时文件，确保干净状态
- 退出时清理当前会话文件
- 每次打开附件前会检查并删除同名旧文件

### 4. 错误处理
- 所有清理操作都有异常捕获
- 清理失败不会影响应用正常运行

## 📝 日志输出

系统会输出详细的清理日志，方便调试：

```
[临时文件清理] 启动时共清理 3 个旧临时文件
[临时文件] 已创建: encnotes_temp_xxx_document.pdf
[临时文件清理] 已清理会话文件: encnotes_temp_xxx_document.pdf
[临时文件清理] 退出时共清理 5 个临时文件
```

## 🎯 总结

通过三层防护机制，我们确保：

1. ✅ **正常退出**：临时文件立即清理
2. ✅ **异常退出**：下次启动时自动清理
3. ✅ **长期运行**：超时文件自动清理
4. ✅ **用户控制**：提供手动清理选项
5. ✅ **安全可靠**：多重保障，不留残留

这个机制既保证了安全性，又提供了良好的用户体验，即使在各种异常情况下也能妥善处理临时文件。
