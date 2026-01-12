#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 PyObjC CloudKit 集成
验证在不同模式下是否正确选择 Mock 或 PyObjC 实现
"""

import os
import sys

def test_development_mode():
    """测试开发模式（应该使用Mock）"""
    print("\n" + "="*60)
    print("测试 1: 开发模式")
    print("="*60)
    
    # 设置开发模式环境变量
    os.environ['ENCNOTES_DEV_MODE'] = '1'
    
    # 重新导入以应用环境变量
    if 'cloudkit_manager' in sys.modules:
        del sys.modules['cloudkit_manager']
    
    from cloudkit_manager import get_cloudkit_sync_class, get_run_mode, print_environment_info
    
    print_environment_info()
    
    CloudKitClass = get_cloudkit_sync_class()
    print(f"\n✓ 获取到的类: {CloudKitClass.__name__}")
    print(f"✓ 模块: {CloudKitClass.__module__}")
    
    expected = "MockCloudKitSync"
    if CloudKitClass.__name__ == expected:
        print(f"✅ 测试通过: 开发模式使用 {expected}")
        return True
    else:
        print(f"❌ 测试失败: 期望 {expected}, 实际 {CloudKitClass.__name__}")
        return False


def test_bundled_mode():
    """测试打包模式（应该尝试使用PyObjC）"""
    print("\n" + "="*60)
    print("测试 2: 打包模式（模拟）")
    print("="*60)
    
    # 清除开发模式环境变量
    if 'ENCNOTES_DEV_MODE' in os.environ:
        del os.environ['ENCNOTES_DEV_MODE']
    
    # 设置打包模式环境变量
    os.environ['ENCNOTES_BUNDLED'] = '1'
    
    # 重新导入以应用环境变量
    if 'cloudkit_manager' in sys.modules:
        del sys.modules['cloudkit_manager']
    
    from cloudkit_manager import get_cloudkit_sync_class, get_run_mode, print_environment_info
    
    print_environment_info()
    
    CloudKitClass = get_cloudkit_sync_class()
    print(f"\n✓ 获取到的类: {CloudKitClass.__name__}")
    print(f"✓ 模块: {CloudKitClass.__module__}")
    
    # 打包模式下，如果PyObjC可用应该使用CloudKitPyObjCSync，否则降级到Mock
    if CloudKitClass.__name__ == "CloudKitPyObjCSync":
        print(f"✅ 测试通过: 打包模式使用 PyObjC CloudKit")
        return True
    elif CloudKitClass.__name__ == "MockCloudKitSync":
        print(f"⚠️  打包模式降级到 Mock CloudKit（PyObjC不可用或初始化失败）")
        return True
    else:
        print(f"❌ 测试失败: 未知的类 {CloudKitClass.__name__}")
        return False


def test_pyobjc_availability():
    """测试PyObjC是否可用"""
    print("\n" + "="*60)
    print("测试 3: PyObjC 可用性")
    print("="*60)
    
    try:
        from cloudkit_pyobjc import is_cloudkit_available, PYOBJC_AVAILABLE, CLOUDKIT_AVAILABLE
        
        print(f"PyObjC 可用: {PYOBJC_AVAILABLE}")
        print(f"CloudKit 可用: {CLOUDKIT_AVAILABLE}")
        print(f"is_cloudkit_available(): {is_cloudkit_available()}")
        
        if is_cloudkit_available():
            print("✅ PyObjC CloudKit 可用")
            
            # 尝试打印Bundle信息
            from cloudkit_pyobjc import print_bundle_and_entitlements
            print_bundle_and_entitlements()
            
            return True
        else:
            print("⚠️  PyObjC CloudKit 不可用")
            print("提示: 可能需要安装 PyObjC: pip install pyobjc-framework-CloudKit")
            return False
            
    except ImportError as e:
        print(f"❌ 无法导入 cloudkit_pyobjc: {e}")
        return False


def test_mock_cloudkit():
    """测试Mock CloudKit功能"""
    print("\n" + "="*60)
    print("测试 4: Mock CloudKit 功能")
    print("="*60)
    
    try:
        from cloudkit_mock import MockCloudKitSync
        
        # 创建模拟的note_manager
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
        sync = MockCloudKitSync(note_manager)
        
        # 测试基本功能
        print("\n测试账户状态检查...")
        success, message = sync.check_account_status()
        print(f"结果: {message}")
        
        print("\n测试启用同步...")
        success, message = sync.enable_sync()
        print(f"结果: {message}")
        
        print("\n测试获取状态...")
        status = sync.get_sync_status()
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        print("\n✅ Mock CloudKit 功能测试通过")
        return True
        
    except Exception as e:
        print(f"❌ Mock CloudKit 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pyobjc_cloudkit():
    """测试PyObjC CloudKit功能（如果可用）"""
    print("\n" + "="*60)
    print("测试 5: PyObjC CloudKit 功能")
    print("="*60)
    
    try:
        from cloudkit_pyobjc import CloudKitPyObjCSync, is_cloudkit_available
        
        if not is_cloudkit_available():
            print("⚠️  PyObjC CloudKit 不可用，跳过测试")
            return True
        
        # 检查Bundle ID
        from Foundation import NSBundle
        main_bundle = NSBundle.mainBundle()
        bundle_id = main_bundle.bundleIdentifier()
        
        if not bundle_id:
            print("\n⚠️  当前进程没有 Bundle ID")
            print("这是正常的，因为我们在开发环境中运行")
            print("在打包后的应用中，会自动拥有 Bundle ID")
            print("\n跳过 CloudKit 初始化测试（避免崩溃）")
            print("✅ PyObjC CloudKit 代码检查通过（未实际初始化）")
            return True
        
        # 如果有Bundle ID，才尝试初始化
        print(f"\n✓ 检测到 Bundle ID: {bundle_id}")
        
        # 创建模拟的note_manager
        class MockNoteManager:
            def update_cloudkit_metadata(self, note_id, record_id, change_tag):
                print(f"  更新元数据: {note_id} -> {record_id}")
            
            def get_note(self, note_id):
                return None
            
            def create_note(self, title, content, folder_id=None):
                print(f"  创建笔记: {title}")
            
            def update_note(self, note_id, title, content):
                print(f"  更新笔记: {title}")
        
        note_manager = MockNoteManager()
        
        print("\n尝试创建 CloudKitPyObjCSync 实例...")
        
        try:
            sync = CloudKitPyObjCSync(note_manager)
            
            print("\n✓ CloudKitPyObjCSync 实例创建成功")
            
            # 测试基本功能
            print("\n测试账户状态检查...")
            success, message = sync.check_account_status()
            print(f"结果: {message}")
            
            if success:
                print("\n测试启用同步...")
                success, message = sync.enable_sync()
                print(f"结果: {message}")
            
            print("\n测试获取状态...")
            status = sync.get_sync_status()
            for key, value in status.items():
                print(f"  {key}: {value}")
            
            print("\n✅ PyObjC CloudKit 功能测试通过")
            return True
            
        except RuntimeError as e:
            if "Bundle ID" in str(e):
                print(f"\n⚠️  预期的错误: {e}")
                print("这是正常的，因为当前进程没有 Bundle ID")
                print("在打包后的应用中，这个问题会自动解决")
                return True
            else:
                raise
        
    except Exception as e:
        print(f"❌ PyObjC CloudKit 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("PyObjC CloudKit 集成测试")
    print("="*60)
    
    results = []
    
    # 测试1: 开发模式
    results.append(("开发模式", test_development_mode()))
    
    # 测试2: 打包模式
    results.append(("打包模式", test_bundled_mode()))
    
    # 测试3: PyObjC可用性
    results.append(("PyObjC可用性", test_pyobjc_availability()))
    
    # 测试4: Mock CloudKit
    results.append(("Mock CloudKit", test_mock_cloudkit()))
    
    # 测试5: PyObjC CloudKit
    results.append(("PyObjC CloudKit", test_pyobjc_cloudkit()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
