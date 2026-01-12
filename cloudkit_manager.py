#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloudKit管理器 - 智能选择Mock或真实CloudKit实现
开发时使用Mock，打包后使用真实CloudKit
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_bundled_app() -> bool:
    """检测是否在打包的应用中运行
    
    Returns:
        True: 打包应用
        False: 开发环境
    """
    # 方法1: 检查sys.frozen属性（py2app、PyInstaller等会设置）
    if getattr(sys, 'frozen', False):
        return True
    
    # 方法2: 检查是否在.app包内运行
    executable_path = Path(sys.executable)
    if '.app/Contents/' in str(executable_path):
        return True
    
    # 方法3: 检查环境变量
    if os.environ.get('ENCNOTES_BUNDLED') == '1':
        return True
    
    return False


def is_development_mode() -> bool:
    """检测是否在开发模式
    
    Returns:
        True: 开发模式
        False: 生产模式
    """
    # 方法1: 检查环境变量
    if os.environ.get('ENCNOTES_DEV_MODE') == '1':
        return True
    
    # 方法2: 检查是否在PyCharm中运行
    if 'PYCHARM_HOSTED' in os.environ:
        return True
    
    # 方法3: 检查DEBUG环境变量
    if os.environ.get('DEBUG') == '1':
        return True
    
    # 方法4: 检查是否从终端运行Python脚本（且未打包）
    # 如果是从终端运行且不是打包应用，默认为开发模式
    if not is_bundled_app():
        # 检查是否通过python命令运行
        if 'python' in sys.executable.lower():
            return True
    
    return False


def get_run_mode() -> str:
    """获取运行模式
    
    Returns:
        'bundled': 打包应用模式
        'development': 开发模式
        'production': 生产模式（未打包但非开发）
    """
    if is_bundled_app():
        return 'bundled'
    elif is_development_mode():
        return 'development'
    else:
        return 'production'


def should_use_mock_cloudkit() -> bool:
    """判断是否应该使用Mock CloudKit
    
    Returns:
        True: 使用Mock
        False: 使用真实CloudKit
    """
    mode = get_run_mode()
    
    # 开发模式：使用Mock
    if mode == 'development':
        return True
    
    # 打包模式：使用真实CloudKit
    if mode == 'bundled':
        return False
    
    # 生产模式：默认使用真实CloudKit
    # 但可以通过环境变量强制使用Mock
    if os.environ.get('ENCNOTES_FORCE_MOCK') == '1':
        return True
    
    return False


def get_cloudkit_sync_class():
    """获取CloudKit同步类
    
    根据运行环境自动选择Mock或真实实现
    - 开发模式：使用Mock CloudKit（不会崩溃）
    - 打包模式：使用PyObjC CloudKit（真实iCloud同步）
    
    Returns:
        CloudKit同步类
    """
    mode = get_run_mode()
    
    # 开发模式：使用Mock
    if mode == 'development':
        logger.info(f"🔧 运行模式: {mode} - 使用Mock CloudKit")
        print(f"🔧 运行模式: {mode} - 使用Mock CloudKit（开发调试）")
        from cloudkit_mock import MockCloudKitSync
        return MockCloudKitSync
    
    # 打包模式：尝试使用PyObjC
    logger.info(f"🔧 运行模式: {mode} - 尝试使用PyObjC CloudKit")
    print(f"🔧 运行模式: {mode} - 尝试使用PyObjC CloudKit（真实同步）")
    
    try:
        from cloudkit_pyobjc import CloudKitPyObjCSync, is_cloudkit_available
        
        if is_cloudkit_available():
            logger.info("✓ PyObjC CloudKit可用")
            print("✓ PyObjC CloudKit可用")
            return CloudKitPyObjCSync
        else:
            logger.warning("⚠️  PyObjC CloudKit不可用，降级到Mock")
            print("⚠️  PyObjC CloudKit不可用，降级到Mock")
            from cloudkit_mock import MockCloudKitSync
            return MockCloudKitSync
            
    except ImportError as e:
        logger.warning(f"⚠️  无法导入PyObjC CloudKit: {e}，降级到Mock")
        print(f"⚠️  无法导入PyObjC CloudKit: {e}，降级到Mock")
        from cloudkit_mock import MockCloudKitSync
        return MockCloudKitSync
    except Exception as e:
        logger.error(f"✗ PyObjC CloudKit初始化失败: {e}，降级到Mock")
        print(f"✗ PyObjC CloudKit初始化失败: {e}，降级到Mock")
        from cloudkit_mock import MockCloudKitSync
        return MockCloudKitSync


def create_cloudkit_sync(note_manager, container_id: Optional[str] = None):
    """创建CloudKit同步实例
    
    Args:
        note_manager: 笔记管理器实例
        container_id: CloudKit容器ID（可选）
        
    Returns:
        CloudKit同步实例
    """
    if container_id is None:
        container_id = "iCloud.com.encnotes.app"
    
    CloudKitSyncClass = get_cloudkit_sync_class()
    
    try:
        sync_instance = CloudKitSyncClass(note_manager, container_id)
        logger.info(f"✓ CloudKit同步实例创建成功: {CloudKitSyncClass.__name__}")
        return sync_instance
    except Exception as e:
        logger.error(f"✗ CloudKit同步实例创建失败: {e}", exc_info=True)
        
        # 失败时降级到Mock
        logger.info("降级到Mock CloudKit")
        from cloudkit_mock import MockCloudKitSync
        return MockCloudKitSync(note_manager, container_id)


def print_environment_info():
    """打印环境信息（用于调试）"""
    mode = get_run_mode()
    use_mock = should_use_mock_cloudkit()
    
    print("\n" + "=" * 60)
    print("EncNotes CloudKit 环境信息")
    print("=" * 60)
    print(f"运行模式: {mode}")
    print(f"是否打包: {is_bundled_app()}")
    print(f"开发模式: {is_development_mode()}")
    print(f"使用Mock: {use_mock}")
    print(f"Python路径: {sys.executable}")
    print(f"工作目录: {os.getcwd()}")
    
    # 环境变量
    env_vars = [
        'ENCNOTES_BUNDLED',
        'ENCNOTES_DEV_MODE',
        'ENCNOTES_FORCE_MOCK',
        'DEBUG',
        'PYCHARM_HOSTED'
    ]
    print("\n环境变量:")
    for var in env_vars:
        value = os.environ.get(var, '(未设置)')
        print(f"  {var} = {value}")
    
    print("=" * 60 + "\n")


# 导出主要接口
__all__ = [
    'get_cloudkit_sync_class',
    'create_cloudkit_sync',
    'is_bundled_app',
    'is_development_mode',
    'get_run_mode',
    'should_use_mock_cloudkit',
    'print_environment_info'
]


if __name__ == "__main__":
    # 测试环境检测
    print_environment_info()
    
    # 测试获取CloudKit类
    CloudKitClass = get_cloudkit_sync_class()
    print(f"\n将使用的CloudKit类: {CloudKitClass.__name__}")
