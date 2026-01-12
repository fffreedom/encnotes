#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 PyObjC 直接调用 CloudKit
避免子进程调用，直接在主进程中使用 CloudKit 框架
"""

import sys
import json
import logging
from typing import Optional, Dict, List, Tuple, Callable
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

# 尝试导入 PyObjC 框架
PYOBJC_AVAILABLE = False
CLOUDKIT_AVAILABLE = False

try:
    from Foundation import NSBundle, NSProcessInfo
    from CloudKit import (
        CKContainer,
        CKRecord,
        CKRecordID,
        CKQuery,
        CKQueryOperation,
        CKModifyRecordsOperation,
        NSPredicate
    )
    import objc
    
    PYOBJC_AVAILABLE = True
    CLOUDKIT_AVAILABLE = True
    logger.info("✓ PyObjC 和 CloudKit 框架加载成功")
    print("✓ PyObjC 和 CloudKit 框架加载成功")
    
except ImportError as e:
    logger.error(f"PyObjC 或 CloudKit 框架加载失败: {e}")
    print(f"✗ PyObjC 或 CloudKit 框架加载失败: {e}")
    print("提示: 请安装 PyObjC: pip install pyobjc-framework-CloudKit")


def print_bundle_and_entitlements():
    """打印当前应用的 Bundle ID 和 Entitlements 信息"""
    if not PYOBJC_AVAILABLE:
        print("PyObjC 不可用，无法获取 Bundle 信息")
        return
    
    print("\n" + "="*60)
    print("Bundle 和 Entitlements 信息")
    print("="*60)
    
    # 获取主 Bundle
    main_bundle = NSBundle.mainBundle()
    
    # 1. Bundle Identifier
    bundle_id = main_bundle.bundleIdentifier()
    print(f"Bundle ID: {bundle_id if bundle_id else '❌ 未设置'}")
    
    # 2. Bundle Path
    bundle_path = main_bundle.bundlePath()
    print(f"Bundle Path: {bundle_path}")
    
    # 3. Executable Path
    executable_path = main_bundle.executablePath()
    print(f"Executable Path: {executable_path if executable_path else '未知'}")
    
    # 4. Info.plist 信息
    info_dict = main_bundle.infoDictionary()
    if info_dict:
        print(f"\nInfo.plist 关键信息:")
        print(f"  - CFBundleName: {info_dict.get('CFBundleName', '未设置')}")
        print(f"  - CFBundleIdentifier: {info_dict.get('CFBundleIdentifier', '未设置')}")
        print(f"  - CFBundleVersion: {info_dict.get('CFBundleVersion', '未设置')}")
        print(f"  - CFBundleShortVersionString: {info_dict.get('CFBundleShortVersionString', '未设置')}")
    
    # 5. 进程信息
    process_info = NSProcessInfo.processInfo()
    print(f"\n进程信息:")
    print(f"  - Process Name: {process_info.processName()}")
    print(f"  - Process ID: {process_info.processIdentifier()}")
    
    # 6. 尝试读取 Entitlements（从代码签名中）
    print(f"\nEntitlements 信息:")
    try:
        # 使用 Security 框架读取 Entitlements
        from Security import (
            SecTaskCreateFromSelf,
            SecTaskCopyValueForEntitlement,
            kCFAllocatorDefault
        )
        
        # 创建当前任务的引用
        task = SecTaskCreateFromSelf(kCFAllocatorDefault)
        
        if task:
            # 读取 CloudKit 相关的 Entitlements
            entitlements_to_check = [
                "com.apple.developer.icloud-container-identifiers",
                "com.apple.developer.icloud-services",
                "com.apple.developer.ubiquity-container-identifiers",
                "com.apple.application-identifier",
                "com.apple.developer.team-identifier"
            ]
            
            has_entitlements = False
            for entitlement_key in entitlements_to_check:
                value = SecTaskCopyValueForEntitlement(task, entitlement_key, None)
                if value is not None:
                    has_entitlements = True
                    print(f"  ✓ {entitlement_key}:")
                    if isinstance(value, (list, tuple)):
                        for item in value:
                            print(f"      - {item}")
                    else:
                        print(f"      {value}")
            
            if not has_entitlements:
                print("  ❌ 未找到任何 CloudKit 相关的 Entitlements")
                print("  提示: 应用可能没有正确配置 iCloud 权限")
        else:
            print("  ❌ 无法创建 Security Task")
            
    except ImportError:
        print("  ⚠️  Security 框架不可用，无法读取 Entitlements")
    except Exception as e:
        print(f"  ⚠️  读取 Entitlements 失败: {e}")
    
    print("="*60 + "\n")


class CloudKitPyObjCSync:
    """使用 PyObjC 直接调用 CloudKit 的同步管理器"""
    
    def __init__(self, note_manager, container_id="iCloud.com.encnotes.app"):
        """初始化 CloudKit 同步管理器
        
        Args:
            note_manager: 笔记管理器实例
            container_id: CloudKit 容器 ID
        """
        logger.info(f"开始初始化 CloudKitPyObjCSync, container_id={container_id}")
        
        if not CLOUDKIT_AVAILABLE:
            raise RuntimeError("CloudKit 框架不可用，请安装 PyObjC")
        
        self.note_manager = note_manager
        self.container_id = container_id
        
        # 打印 Bundle 和 Entitlements 信息
        print_bundle_and_entitlements()
        
        # 检查 Bundle ID
        main_bundle = NSBundle.mainBundle()
        bundle_id = main_bundle.bundleIdentifier()
        
        if not bundle_id:
            error_msg = (
                "❌ 当前进程没有 Bundle ID，无法使用 CloudKit\n"
                "原因: Python 解释器作为独立进程运行，没有应用包结构\n"
                "解决方案:\n"
                "  1. 将 Python 应用打包为 .app 格式\n"
                "  2. 配置 Info.plist 和 Entitlements\n"
                "  3. 进行代码签名\n"
                "当前进程信息:\n"
                f"  - Executable: {main_bundle.executablePath()}\n"
                f"  - Bundle Path: {main_bundle.bundlePath()}"
            )
            logger.error(error_msg)
            print(error_msg)
            raise RuntimeError("当前进程没有 Bundle ID，无法使用 CloudKit")
        
        # 初始化 CloudKit 容器（如果有 Bundle ID 才尝试）
        try:
            logger.info(f"正在初始化 CloudKit 容器: {container_id}")
            print(f"\n⚠️  警告: 即将尝试初始化 CloudKit 容器")
            print(f"如果应用没有正确的 Entitlements，可能会崩溃...")
            
            self.container = CKContainer.containerWithIdentifier_(container_id)
            self.private_database = self.container.privateCloudDatabase()
            logger.info("✓ CloudKit 容器初始化成功")
            print("✓ CloudKit 容器初始化成功")
        except Exception as e:
            logger.error(f"CloudKit 容器初始化失败: {e}", exc_info=True)
            print(f"✗ CloudKit 容器初始化失败: {e}")
            raise
        
        # 同步状态
        self.sync_enabled = False
        self.is_syncing = False
        self.account_status = None
        
        # 回调函数
        self.status_callback = None
        self.progress_callback = None
        
        logger.info("CloudKitPyObjCSync 实例创建成功")
        print("CloudKitPyObjCSync 实例创建成功")
    
    def check_account_status(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """检查 iCloud 账户状态
        
        Args:
            completion_handler: 完成回调函数 (success: bool, status: int, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("开始检查 iCloud 账户状态...")
        print("\n正在检查 iCloud 账户状态...")
        
        if not CLOUDKIT_AVAILABLE:
            return False, "CloudKit 框架不可用"
        
        # 使用信号量等待异步回调
        import threading
        result_container = {'status': None, 'error': None}
        semaphore = threading.Semaphore(0)
        
        def callback(status, error):
            """账户状态检查回调"""
            result_container['status'] = status
            result_container['error'] = error
            semaphore.release()
        
        # 调用 CloudKit API
        try:
            self.container.accountStatusWithCompletionHandler_(callback)
            
            # 等待回调完成（最多 10 秒）
            if semaphore.acquire(timeout=10):
                status = result_container['status']
                error = result_container['error']
                
                if error:
                    error_msg = f"检查账户状态失败: {error.localizedDescription()}"
                    logger.error(error_msg)
                    print(f"✗ {error_msg}")
                    if completion_handler:
                        completion_handler(False, 0, error_msg)
                    return False, error_msg
                
                # 状态码: 0=无法确定, 1=可用, 2=受限, 3=未登录
                status_names = {
                    0: "无法确定",
                    1: "可用",
                    2: "受限",
                    3: "未登录"
                }
                
                self.account_status = status
                status_name = status_names.get(status, "未知")
                message = f"iCloud 账户{status_name}"
                is_available = (status == 1)
                
                if is_available:
                    self.sync_enabled = True
                    logger.info(f"✓ {message}")
                    print(f"✓ {message}")
                else:
                    logger.warning(f"✗ {message}")
                    print(f"✗ {message}")
                
                if completion_handler:
                    completion_handler(is_available, status, message)
                
                return is_available, message
            else:
                error_msg = "检查账户状态超时"
                logger.error(error_msg)
                print(f"✗ {error_msg}")
                if completion_handler:
                    completion_handler(False, 0, error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"检查账户状态异常: {e}"
            logger.error(error_msg, exc_info=True)
            print(f"✗ {error_msg}")
            if completion_handler:
                completion_handler(False, 0, error_msg)
            return False, error_msg
    
    def enable_sync(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """启用同步
        
        Args:
            completion_handler: 完成回调函数 (success: bool, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("开始启用 iCloud 同步...")
        
        if not CLOUDKIT_AVAILABLE:
            return False, "CloudKit 框架不可用"
        
        def on_status_checked(success, status, message):
            """账户状态检查完成回调"""
            if success:
                logger.info("✓ iCloud 同步已启用（使用 PyObjC）")
                print("✓ iCloud 同步已启用（使用 PyObjC）")
                if completion_handler:
                    completion_handler(True, "iCloud 同步已启用")
            else:
                logger.warning(f"账户状态检查失败: {message}")
                if completion_handler:
                    completion_handler(False, message)
        
        return self.check_account_status(on_status_checked)
    
    def push_notes(self, notes: List[Dict], completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """推送笔记到CloudKit
        
        Args:
            notes: 笔记列表
            completion_handler: 完成回调函数 (success: bool, saved_count: int, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info(f"开始推送笔记到CloudKit，数量: {len(notes) if notes else 0}")
        
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
            
            # 创建CKRecord列表
            records_to_save = []
            note_id_map = {}  # 映射 CKRecord -> note_id
            
            for note in notes:
                try:
                    note_id = note.get('id')
                    if not note_id:
                        continue
                    
                    # 创建或获取CKRecord
                    record_name = note.get('cloudkit_record_id')
                    if record_name:
                        # 更新现有记录
                        record_id = CKRecordID.alloc().initWithRecordName_(record_name)
                        record = CKRecord.alloc().initWithRecordType_recordID_("Note", record_id)
                    else:
                        # 创建新记录
                        record = CKRecord.alloc().initWithRecordType_("Note")
                    
                    # 设置字段
                    record.setObject_forKey_(note_id, "identifier")
                    record.setObject_forKey_(note.get('title', ''), "title")
                    record.setObject_forKey_(note.get('content', ''), "content")
                    record.setObject_forKey_(note.get('_cocoa_created', 0.0), "creationDate")
                    record.setObject_forKey_(note.get('_cocoa_modified', 0.0), "modificationDate")
                    record.setObject_forKey_(note.get('is_favorite', False), "isFavorite")
                    record.setObject_forKey_(note.get('is_deleted', False), "isDeleted")
                    
                    folder_id = note.get('folder_id')
                    if folder_id:
                        record.setObject_forKey_(folder_id, "folderID")
                    
                    records_to_save.append(record)
                    note_id_map[id(record)] = note_id
                    
                except Exception as e:
                    logger.error(f"创建CKRecord失败: {e}")
                    continue
            
            if not records_to_save:
                self.is_syncing = False
                return True, "没有有效的笔记需要同步"
            
            # 使用信号量等待异步操作
            import threading
            result_container = {'success': False, 'saved_count': 0, 'error': None}
            semaphore = threading.Semaphore(0)
            
            def modify_completion(saved_records, deleted_record_ids, error):
                """修改操作完成回调"""
                if error:
                    result_container['error'] = error
                    result_container['success'] = False
                else:
                    result_container['success'] = True
                    result_container['saved_count'] = len(saved_records) if saved_records else 0
                    
                    # 更新本地元数据
                    if saved_records:
                        for record in saved_records:
                            try:
                                note_id = note_id_map.get(id(record))
                                if note_id:
                                    record_id = record.recordID().recordName()
                                    change_tag = record.recordChangeTag() or ""
                                    self.note_manager.update_cloudkit_metadata(
                                        note_id, record_id, change_tag
                                    )
                            except Exception as e:
                                logger.error(f"更新元数据失败: {e}")
                
                semaphore.release()
            
            # 创建修改操作
            modify_op = CKModifyRecordsOperation.alloc().initWithRecordsToSave_recordIDsToDelete_(
                records_to_save, None
            )
            modify_op.setDatabase_(self.private_database)
            modify_op.setModifyRecordsCompletionBlock_(modify_completion)
            
            # 执行操作
            self.private_database.addOperation_(modify_op)
            
            # 等待完成（最多60秒）
            if semaphore.acquire(timeout=60):
                self.is_syncing = False
                
                if result_container['success']:
                    saved_count = result_container['saved_count']
                    message = f"成功上传 {saved_count} 条笔记"
                    logger.info(f"✓ {message}")
                    print(f"✓ {message}")
                    
                    if completion_handler:
                        completion_handler(True, saved_count, message)
                    
                    return True, message
                else:
                    error = result_container['error']
                    error_msg = f"上传失败: {error.localizedDescription() if error else '未知错误'}"
                    logger.error(error_msg)
                    print(f"✗ {error_msg}")
                    
                    if completion_handler:
                        completion_handler(False, 0, error_msg)
                    
                    return False, error_msg
            else:
                self.is_syncing = False
                error_msg = "上传超时"
                logger.error(error_msg)
                
                if completion_handler:
                    completion_handler(False, 0, error_msg)
                
                return False, error_msg
                
        except Exception as e:
            self.is_syncing = False
            error_msg = f"推送异常: {e}"
            logger.error(error_msg, exc_info=True)
            print(f"✗ {error_msg}")
            
            if completion_handler:
                completion_handler(False, 0, error_msg)
            
            return False, error_msg
    
    def pull_notes(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """从CloudKit拉取笔记
        
        Args:
            completion_handler: 完成回调函数 (success: bool, records: List, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("开始从CloudKit拉取笔记...")
        
        if not self.sync_enabled:
            return False, "同步未启用"
        
        try:
            # 创建查询
            predicate = NSPredicate.predicateWithValue_(True)  # 查询所有记录
            query = CKQuery.alloc().initWithRecordType_predicate_("Note", predicate)
            
            # 使用信号量等待异步操作
            import threading
            result_container = {'success': False, 'records': [], 'error': None}
            semaphore = threading.Semaphore(0)
            
            def query_completion(results, error):
                """查询完成回调"""
                if error:
                    result_container['error'] = error
                    result_container['success'] = False
                else:
                    result_container['success'] = True
                    
                    # 转换CKRecord为字典
                    records = []
                    if results:
                        for record in results:
                            try:
                                record_dict = {
                                    'recordID': record.recordID().recordName(),
                                    'recordChangeTag': record.recordChangeTag() or "",
                                    'identifier': record.objectForKey_("identifier"),
                                    'title': record.objectForKey_("title") or "",
                                    'content': record.objectForKey_("content") or "",
                                    'creationDate': record.objectForKey_("creationDate") or 0.0,
                                    'modificationDate': record.objectForKey_("modificationDate") or 0.0,
                                    'isFavorite': record.objectForKey_("isFavorite") or False,
                                    'isDeleted': record.objectForKey_("isDeleted") or False,
                                    'folderID': record.objectForKey_("folderID")
                                }
                                records.append(record_dict)
                            except Exception as e:
                                logger.error(f"转换记录失败: {e}")
                                continue
                    
                    result_container['records'] = records
                
                semaphore.release()
            
            # 执行查询
            self.private_database.performQuery_inZoneWithID_completionHandler_(
                query, None, query_completion
            )
            
            # 等待完成（最多60秒）
            if semaphore.acquire(timeout=60):
                if result_container['success']:
                    records = result_container['records']
                    count = len(records)
                    message = f"成功拉取 {count} 条笔记"
                    logger.info(f"✓ {message}")
                    print(f"✓ {message}")
                    
                    if completion_handler:
                        completion_handler(True, records, message)
                    
                    return True, message
                else:
                    error = result_container['error']
                    error_msg = f"拉取失败: {error.localizedDescription() if error else '未知错误'}"
                    logger.error(error_msg)
                    print(f"✗ {error_msg}")
                    
                    if completion_handler:
                        completion_handler(False, [], error_msg)
                    
                    return False, error_msg
            else:
                error_msg = "拉取超时"
                logger.error(error_msg)
                
                if completion_handler:
                    completion_handler(False, [], error_msg)
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"拉取异常: {e}"
            logger.error(error_msg, exc_info=True)
            print(f"✗ {error_msg}")
            
            if completion_handler:
                completion_handler(False, [], error_msg)
            
            return False, error_msg
    
    def merge_remote_records(self, records: List[Dict]) -> int:
        """合并远程记录到本地数据库
        
        Args:
            records: CloudKit记录列表
            
        Returns:
            合并的笔记数量
        """
        if not records:
            return 0
        
        merged_count = 0
        
        try:
            for record in records:
                try:
                    note_id = record.get('identifier')
                    title = record.get('title', '无标题')
                    content = record.get('content', '')
                    
                    if not note_id:
                        continue
                    
                    remote_modified = record.get('modificationDate', 0.0)
                    
                    # 检查本地是否存在
                    local_note = self.note_manager.get_note(note_id)
                    
                    if not local_note:
                        # 创建新笔记
                        folder_id = record.get('folderID')
                        self.note_manager.create_note(
                            title=title,
                            content=content,
                            folder_id=folder_id
                        )
                        merged_count += 1
                        logger.info(f"创建新笔记: {title}")
                        
                    elif remote_modified > local_note['_cocoa_modified']:
                        # 更新笔记
                        self.note_manager.update_note(
                            note_id,
                            title=title,
                            content=content
                        )
                        merged_count += 1
                        logger.info(f"更新笔记: {title}")
                    
                    # 更新元数据
                    record_id = record.get('recordID', '')
                    change_tag = record.get('recordChangeTag', '')
                    if record_id:
                        self.note_manager.update_cloudkit_metadata(note_id, record_id, change_tag)
                    
                except Exception as e:
                    logger.error(f"合并单条记录失败: {e}")
                    continue
            
            return merged_count
            
        except Exception as e:
            logger.error(f"合并记录失败: {e}")
            return merged_count
    
    def setup_subscription(self, completion_handler: Optional[Callable] = None):
        """设置CloudKit订阅
        
        Args:
            completion_handler: 完成回调函数 (success: bool, message: str)
        """
        logger.info("设置CloudKit订阅...")
        
        # TODO: 实现订阅功能
        # 订阅可以让应用在数据变化时收到通知
        
        if completion_handler:
            completion_handler(True, "订阅功能待实现")
    
    def disable_sync(self) -> Tuple[bool, str]:
        """禁用同步"""
        self.sync_enabled = False
        logger.info("iCloud 同步已禁用")
        return True, "iCloud 同步已禁用"
    
    def get_sync_status(self) -> Dict:
        """获取同步状态信息"""
        status_names = {
            0: "无法确定",
            1: "可用",
            2: "受限",
            3: "未登录"
        }
        
        return {
            'enabled': self.sync_enabled,
            'is_syncing': self.is_syncing,
            'account_status': self.account_status,
            'account_status_name': status_names.get(self.account_status, "未知"),
            'cloudkit_available': CLOUDKIT_AVAILABLE,
            'sync_method': 'Native CloudKit (PyObjC)' if CLOUDKIT_AVAILABLE else 'Unavailable',
            'container_id': self.container_id
        }


def is_cloudkit_available() -> bool:
    """检查 CloudKit 是否可用"""
    return CLOUDKIT_AVAILABLE


# 测试代码
if __name__ == "__main__":
    print("CloudKit PyObjC 测试")
    print("="*60)
    
    # 打印 Bundle 和 Entitlements 信息
    print_bundle_and_entitlements()
    
    if CLOUDKIT_AVAILABLE:
        print("\n测试 CloudKit 容器初始化...")
        try:
            # 创建一个模拟的 note_manager
            class MockNoteManager:
                pass
            
            sync = CloudKitPyObjCSync(MockNoteManager(), "iCloud.com.encnotes.app")
            
            print("\n测试账户状态检查...")
            success, message = sync.check_account_status()
            print(f"结果: {message}")
            
            print("\n同步状态:")
            status = sync.get_sync_status()
            for key, value in status.items():
                print(f"  {key}: {value}")
                
        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("CloudKit 不可用，跳过测试")
