#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bundle ID 和 Entitlements 检查工具
在尝试使用 CloudKit 前，先检查当前进程的权限配置
"""

import sys

def check_bundle_info():
    """检查并打印 Bundle ID 和 Entitlements 信息"""
    
    print("\n" + "="*70)
    print("Bundle ID 和 Entitlements 检查")
    print("="*70)
    
    try:
        from Foundation import NSBundle, NSProcessInfo
        print("✓ Foundation 框架加载成功")
    except ImportError as e:
        print(f"✗ Foundation 框架加载失败: {e}")
        print("提示: 请安装 PyObjC: pip install pyobjc-framework-Cocoa")
        return False
    
    # 1. 获取主 Bundle
    main_bundle = NSBundle.mainBundle()
    
    # 2. Bundle Identifier
    bundle_id = main_bundle.bundleIdentifier()
    print(f"\n📦 Bundle Identifier:")
    if bundle_id:
        print(f"   ✓ {bundle_id}")
    else:
        print(f"   ✗ 未设置 (这是问题的根源!)")
    
    # 3. Bundle Path
    bundle_path = main_bundle.bundlePath()
    print(f"\n📁 Bundle Path:")
    print(f"   {bundle_path}")
    
    # 4. Executable Path
    executable_path = main_bundle.executablePath()
    print(f"\n⚙️  Executable Path:")
    print(f"   {executable_path if executable_path else '未知'}")
    
    # 5. Info.plist 信息
    info_dict = main_bundle.infoDictionary()
    print(f"\n📄 Info.plist 信息:")
    if info_dict:
        keys_to_check = [
            'CFBundleName',
            'CFBundleIdentifier',
            'CFBundleVersion',
            'CFBundleShortVersionString',
            'CFBundleExecutable'
        ]
        for key in keys_to_check:
            value = info_dict.get(key, '❌ 未设置')
            print(f"   - {key}: {value}")
    else:
        print("   ❌ 无法读取 Info.plist")
    
    # 6. 进程信息
    process_info = NSProcessInfo.processInfo()
    print(f"\n🔧 进程信息:")
    print(f"   - Process Name: {process_info.processName()}")
    print(f"   - Process ID: {process_info.processIdentifier()}")
    print(f"   - Arguments: {' '.join(process_info.arguments()[:3])}...")
    
    # 7. 尝试读取 Entitlements
    print(f"\n🔐 Entitlements 信息:")
    try:
        from Security import (
            SecTaskCreateFromSelf,
            SecTaskCopyValueForEntitlement,
            kCFAllocatorDefault
        )
        print("   ✓ Security 框架加载成功")
        
        # 创建当前任务的引用
        task = SecTaskCreateFromSelf(kCFAllocatorDefault)
        
        if task:
            # CloudKit 相关的 Entitlements
            entitlements_to_check = [
                ("com.apple.developer.icloud-container-identifiers", "iCloud 容器标识符"),
                ("com.apple.developer.icloud-services", "iCloud 服务"),
                ("com.apple.developer.ubiquity-container-identifiers", "Ubiquity 容器"),
                ("com.apple.application-identifier", "应用标识符"),
                ("com.apple.developer.team-identifier", "团队标识符"),
                ("com.apple.security.app-sandbox", "App Sandbox"),
            ]
            
            has_any_entitlement = False
            for entitlement_key, description in entitlements_to_check:
                value = SecTaskCopyValueForEntitlement(task, entitlement_key, None)
                if value is not None:
                    has_any_entitlement = True
                    print(f"\n   ✓ {description} ({entitlement_key}):")
                    if isinstance(value, (list, tuple)):
                        for item in value:
                            print(f"       - {item}")
                    else:
                        print(f"       {value}")
            
            if not has_any_entitlement:
                print("\n   ❌ 未找到任何 Entitlements")
                print("   这意味着当前进程没有任何特殊权限")
        else:
            print("   ❌ 无法创建 Security Task")
            
    except ImportError:
        print("   ⚠️  Security 框架不可用")
        print("   提示: pip install pyobjc-framework-Security")
    except Exception as e:
        print(f"   ⚠️  读取 Entitlements 失败: {e}")
    
    # 8. 诊断结果
    print(f"\n" + "="*70)
    print("诊断结果")
    print("="*70)
    
    if not bundle_id:
        print("❌ 问题: 当前进程没有 Bundle ID")
        print("\n原因:")
        print("   Python 解释器作为独立进程运行，不是一个完整的 macOS 应用包")
        print("\n影响:")
        print("   - 无法使用 CloudKit API（会直接崩溃）")
        print("   - 无法使用其他需要 Entitlements 的系统框架")
        print("\n解决方案:")
        print("   1. 将 Python 应用打包为 .app 格式")
        print("      使用工具: py2app, PyInstaller, briefcase")
        print("   2. 创建 Info.plist 文件，设置 CFBundleIdentifier")
        print("   3. 创建 Entitlements.plist 文件，添加 CloudKit 权限:")
        print("      <key>com.apple.developer.icloud-container-identifiers</key>")
        print("      <array>")
        print("          <string>iCloud.com.encnotes.app</string>")
        print("      </array>")
        print("   4. 使用 codesign 进行代码签名:")
        print("      codesign --entitlements Entitlements.plist -s 'Developer ID' YourApp.app")
        return False
    else:
        print("✓ 当前进程有 Bundle ID，可以尝试使用 CloudKit")
        print("\n⚠️  注意:")
        print("   即使有 Bundle ID，如果没有正确的 Entitlements，")
        print("   调用 CloudKit API 时仍然会崩溃")
        return True
    
    print("="*70 + "\n")


def test_cloudkit_import():
    """测试是否可以安全导入 CloudKit 框架"""
    print("\n" + "="*70)
    print("CloudKit 框架导入测试")
    print("="*70)
    
    print("\n⚠️  警告: 如果没有正确的 Entitlements，导入 CloudKit 可能会崩溃")
    print("按 Ctrl+C 取消，或按 Enter 继续...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n已取消")
        return False
    
    try:
        print("\n正在导入 CloudKit 框架...")
        from CloudKit import CKContainer
        print("✓ CloudKit 框架导入成功")
        
        print("\n正在尝试创建 CloudKit 容器...")
        print("⚠️  这一步最容易崩溃...")
        
        container = CKContainer.containerWithIdentifier_("iCloud.com.encnotes.app")
        print("✓ CloudKit 容器创建成功!")
        print("\n🎉 恭喜! 你的应用配置正确，可以使用 CloudKit")
        return True
        
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("CloudKit 权限检查工具")
    print("="*70)
    print("\n这个工具会检查当前 Python 进程是否有使用 CloudKit 的权限")
    print("它会输出 Bundle ID 和 Entitlements 信息，帮助诊断问题")
    
    # 检查 Bundle 信息
    has_bundle_id = check_bundle_info()
    
    # 如果有 Bundle ID，询问是否测试 CloudKit
    if has_bundle_id:
        test_cloudkit_import()
    else:
        print("\n由于没有 Bundle ID，跳过 CloudKit 测试")
        print("（测试会导致崩溃）")
    
    print("\n" + "="*70)
    print("检查完成")
    print("="*70 + "\n")
