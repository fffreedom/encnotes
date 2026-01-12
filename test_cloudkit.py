#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudKit API调用测试脚本
测试CloudKit API的实际调用
"""

import sys

print("=" * 60)
print("CloudKit API 调用测试")
print("=" * 60)

try:
    print("\n1. 导入模块...")
    from Foundation import NSObject, NSDate, NSNumber
    from CloudKit import CKContainer
    print("   ✓ 导入成功")
    
    print("\n2. 获取默认容器...")
    container = CKContainer.defaultContainer()
    print(f"   ✓ 默认容器: {container}")
    
    print("\n3. 获取指定容器...")
    container_id = "iCloud.com.encnotes.app"
    custom_container = CKContainer.containerWithIdentifier_(container_id)
    print(f"   ✓ 自定义容器: {custom_container}")
    
    print("\n4. 获取私有数据库...")
    private_db = custom_container.privateCloudDatabase()
    print(f"   ✓ 私有数据库: {private_db}")
    
    print("\n" + "=" * 60)
    print("✓ 所有API调用成功！")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ API调用失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)