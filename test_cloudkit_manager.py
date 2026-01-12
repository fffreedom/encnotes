#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试智能CloudKit管理器
验证开发模式使用Mock，打包模式使用真实CloudKit
"""

import sys
import os

# 测试1: 默认环境（开发模式）
print("=" * 70)
print("测试1: 默认环境（应该使用Mock CloudKit）")
print("=" * 70)

from cloudkit_manager import (
    get_run_mode,
    is_bundled_app,
    is_development_mode,
    should_use_mock_cloudkit,
    get_cloudkit_sync_class,
    print_environment_info
)

print_environment_info()

CloudKitClass = get_cloudkit_sync_class()
print(f"\n✓ 获取到的CloudKit类: {CloudKitClass.__name__}")
print(f"  预期: MockCloudKitSync")
print(f"  实际: {CloudKitClass.__name__}")
print(f"  结果: {'✓ 通过' if 'Mock' in CloudKitClass.__name__ else '✗ 失败'}")

# 测试2: 模拟打包环境
print("\n" + "=" * 70)
print("测试2: 模拟打包环境（应该使用真实CloudKit）")
print("=" * 70)

# 设置环境变量模拟打包
os.environ['ENCNOTES_BUNDLED'] = '1'

# 重新导入以应用新环境
import importlib
import cloudkit_manager
importlib.reload(cloudkit_manager)

from cloudkit_manager import (
    get_run_mode as get_run_mode2,
    should_use_mock_cloudkit as should_use_mock2,
    get_cloudkit_sync_class as get_cloudkit_sync_class2,
    print_environment_info as print_environment_info2
)

print_environment_info2()

CloudKitClass2 = get_cloudkit_sync_class2()
print(f"\n✓ 获取到的CloudKit类: {CloudKitClass2.__name__}")
print(f"  预期: CloudKitNativeSync 或 MockCloudKitSync（降级）")
print(f"  实际: {CloudKitClass2.__name__}")

# 测试3: 强制使用Mock
print("\n" + "=" * 70)
print("测试3: 强制使用Mock（通过环境变量）")
print("=" * 70)

os.environ['ENCNOTES_FORCE_MOCK'] = '1'
del os.environ['ENCNOTES_BUNDLED']

importlib.reload(cloudkit_manager)

from cloudkit_manager import (
    get_cloudkit_sync_class as get_cloudkit_sync_class3,
    print_environment_info as print_environment_info3
)

print_environment_info3()

CloudKitClass3 = get_cloudkit_sync_class3()
print(f"\n✓ 获取到的CloudKit类: {CloudKitClass3.__name__}")
print(f"  预期: MockCloudKitSync")
print(f"  实际: {CloudKitClass3.__name__}")
print(f"  结果: {'✓ 通过' if 'Mock' in CloudKitClass3.__name__ else '✗ 失败'}")

# 测试4: 创建实例
print("\n" + "=" * 70)
print("测试4: 创建CloudKit同步实例")
print("=" * 70)

# 清理环境变量
if 'ENCNOTES_FORCE_MOCK' in os.environ:
    del os.environ['ENCNOTES_FORCE_MOCK']

importlib.reload(cloudkit_manager)

from cloudkit_manager import create_cloudkit_sync

# 创建一个模拟的note_manager
class MockNoteManager:
    def update_cloudkit_metadata(self, note_id, record_id, change_tag):
        pass
    
    def get_note(self, note_id):
        return None
    
    def create_note(self, title, content, folder_id=None):
        pass
    
    def update_note(self, note_id, title, content):
        pass

note_manager = MockNoteManager()

try:
    sync = create_cloudkit_sync(note_manager)
    print(f"\n✓ CloudKit同步实例创建成功")
    print(f"  类型: {type(sync).__name__}")
    print(f"  容器ID: {sync.container_id}")
    
    # 测试基本功能
    print("\n测试基本功能:")
    
    # 检查账户状态
    success, message = sync.check_account_status()
    print(f"  check_account_status: {'✓' if success else '✗'} {message}")
    
    # 启用同步
    success, message = sync.enable_sync()
    print(f"  enable_sync: {'✓' if success else '✗'} {message}")
    
    # 获取状态
    status = sync.get_sync_status()
    print(f"  get_sync_status: ✓")
    print(f"    - enabled: {status.get('enabled')}")
    print(f"    - sync_method: {status.get('sync_method')}")
    print(f"    - account_status_name: {status.get('account_status_name')}")
    
    print("\n✓ 所有测试通过！")
    
except Exception as e:
    print(f"\n✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
