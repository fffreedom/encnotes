# CloudKit 原生同步实现 - 使用指南

## 📋 概述

本文档说明如何使用和调试 encnotes 的原生 CloudKit 同步功能。

## ✅ 当前状态

- **CloudKit框架**: 已启用 (`CLOUDKIT_STABLE = True`)
- **日志级别**: 详细日志已添加
- **同步方式**: 用户使用自己的 iCloud 账户（去中心化）

## 🚀 使用步骤

### 1. 确认环境

```bash
# 检查 CloudKit 框架是否安装
python3 -c "from CloudKit import CKContainer; print('CloudKit 已安装')"

# 检查 iCloud 登录状态
defaults read MobileMeAccounts Accounts
```

### 2. 测试 CloudKit 初始化

```bash
cd /Users/freedom/project/nb/encnotes
python3 test_cloudkit_init.py
```

**预期输出**:
```
✓ cloudkit_native模块导入成功
✓ CloudKitNativeSync实例创建成功
✓ CloudKit容器初始化成功
```

### 3. 启动应用

```bash
python3 main.py
```

**查看日志**:
```bash
tail -f ~/Library/Group\ Containers/group.com.encnotes/encnotes.log
```

### 4. 启用 iCloud 同步

在应用菜单中：
1. 点击 **文件** → **iCloud 同步设置**
2. 点击 **启用 iCloud 同步**
3. 观察日志输出

## 📊 日志说明

### 关键日志点

#### 1. 模块导入
```
正在导入CloudKit框架...
✓ CloudKit框架导入成功
✓ 原生CloudKit已启用
```

#### 2. 实例创建
```
开始初始化CloudKitNativeSync, container_id=iCloud.com.encnotes.app
CloudKitNativeSync 实例创建成功（延迟初始化）
```

#### 3. 容器初始化
```
开始初始化CloudKit容器: iCloud.com.encnotes.app
正在创建CKContainer...
✓ CKContainer创建成功
正在获取私有数据库...
✓ 私有数据库获取成功
✓ CloudKit初始化完成
```

#### 4. 账户状态检查
```
开始检查iCloud账户状态...
调用 accountStatusWithCompletionHandler_...
账户状态检查请求已发送，等待回调...
账户状态码: 1
✓ iCloud账户可用
```

#### 5. 推送笔记
```
开始推送笔记，数量: 3
开始创建CKRecord对象，笔记数量: 3
成功创建3条CKRecord
创建CKModifyRecordsOperation...
操作已添加，正在上传 3 条笔记...
推送操作完成回调被调用
✓ 成功上传 3 条笔记
```

## 🐛 故障排查

### 问题 1: "Illegal instruction: 4"

**原因**: PyObjC 在某些情况下调用 CloudKit 会崩溃

**解决方案**:
1. 检查是否在主线程中运行
2. 确保 RunLoop 正常运行
3. 查看详细日志定位崩溃位置

**日志关键字**:
```bash
grep -i "illegal\|crash\|signal" ~/Library/Group\ Containers/group.com.encnotes/encnotes.log
```

### 问题 2: "CloudKit框架不可用"

**原因**: pyobjc-framework-CloudKit 未安装

**解决方案**:
```bash
pip3 install pyobjc-framework-CloudKit
```

### 问题 3: "未登录iCloud账户"

**原因**: 系统未登录 iCloud

**解决方案**:
1. 打开 **系统设置** → **Apple ID**
2. 登录 iCloud 账户
3. 确保 **iCloud Drive** 已启用

**验证**:
```bash
defaults read MobileMeAccounts Accounts
```

### 问题 4: "账户状态检查失败"

**原因**: 网络问题或 iCloud 服务不可用

**解决方案**:
1. 检查网络连接
2. 访问 https://www.apple.com/support/systemstatus/ 查看 iCloud 服务状态
3. 重启应用重试

### 问题 5: "推送失败"

**可能原因**:
- 网络问题
- iCloud 配额已满
- 记录冲突

**查看详细错误**:
```bash
grep "推送失败" ~/Library/Group\ Containers/group.com.encnotes/encnotes.log
```

## 🔍 调试技巧

### 1. 启用详细日志

在 `cloudkit_native.py` 顶部修改日志级别：

```python
logging.basicConfig(level=logging.DEBUG)
```

### 2. 单步测试

使用 `test_cloudkit_init.py` 逐步测试：

```python
# 只测试导入
python3 -c "from cloudkit_native import is_cloudkit_available; print(is_cloudkit_available())"

# 测试实例化
python3 test_cloudkit_init.py
```

### 3. 监控 CloudKit 操作

```bash
# 实时查看日志
tail -f ~/Library/Group\ Containers/group.com.encnotes/encnotes.log | grep -i cloudkit

# 查看所有 CloudKit 相关日志
grep -i cloudkit ~/Library/Group\ Containers/group.com.encnotes/encnotes.log
```

### 4. 检查 CloudKit 数据

```bash
# 查看本地缓存（模拟实现）
ls -la ~/Library/Group\ Containers/group.com.encnotes/CloudKit/

# 查看同步配置
cat ~/Library/Group\ Containers/group.com.encnotes/sync_config.json
```

## 📝 日志级别说明

| 级别 | 用途 | 示例 |
|------|------|------|
| DEBUG | 详细调试信息 | 记录字段设置、对象创建 |
| INFO | 关键操作信息 | 初始化成功、同步完成 |
| WARNING | 警告信息 | 同步未启用、账户受限 |
| ERROR | 错误信息 | 初始化失败、推送失败 |

## 🎯 关键代码位置

### 初始化流程
```
cloudkit_native.py:
  - __init__()          # 创建实例（延迟初始化）
  - _init_cloudkit()    # 初始化容器和数据库
  - check_account_status()  # 检查账户状态
```

### 同步流程
```
cloudkit_native.py:
  - enable_sync()       # 启用同步
  - push_notes()        # 推送笔记
  - _create_ck_record() # 创建 CloudKit 记录
  - pull_notes()        # 拉取笔记
  - merge_remote_records()  # 合并远程记录
```

### 回调处理
```
cloudkit_native.py:
  - handle_status()     # 账户状态回调
  - handle_zone_saved() # Zone 创建回调
  - handle_completion() # 推送完成回调
  - query_completion_block()  # 查询完成回调
```

## 🔧 常用命令

```bash
# 清理 CloudKit 缓存
rm -rf ~/Library/Group\ Containers/group.com.encnotes/CloudKit/

# 重置同步配置
rm ~/Library/Group\ Containers/group.com.encnotes/sync_config.json

# 查看最近 50 行日志
tail -50 ~/Library/Group\ Containers/group.com.encnotes/encnotes.log

# 搜索错误日志
grep -i "error\|fail\|exception" ~/Library/Group\ Containers/group.com.encnotes/encnotes.log

# 统计同步次数
grep "成功上传" ~/Library/Group\ Containers/group.com.encnotes/encnotes.log | wc -l
```

## 📚 相关文档

- [CLOUDKIT_WEB_SERVICES.md](./CLOUDKIT_WEB_SERVICES.md) - CloudKit Web Services 说明
- [CLOUDKIT_STATUS.md](./CLOUDKIT_STATUS.md) - CloudKit 状态说明
- [Apple CloudKit 文档](https://developer.apple.com/documentation/cloudkit)

## ⚠️ 注意事项

1. **主线程要求**: CloudKit 操作必须在主线程或有效的 RunLoop 中执行
2. **异步操作**: 所有 CloudKit 操作都是异步的，需要使用回调处理结果
3. **错误处理**: 网络错误、冲突等都需要妥善处理
4. **数据隔离**: 每个用户的数据自动隔离，存储在各自的私有数据库
5. **免费额度**: 用户使用自己的 iCloud 空间，开发者无需付费

## 🎉 成功标志

当看到以下日志时，说明 CloudKit 同步正常工作：

```
✓ CloudKit框架已导入并启用
✓ CloudKit初始化成功: iCloud.com.encnotes.app
✓ iCloud账户可用
✓ 成功上传 X 条笔记
```

## 🆘 获取帮助

如果遇到问题：

1. 查看日志文件
2. 运行测试脚本
3. 检查系统 iCloud 状态
4. 查看本文档的故障排查部分
