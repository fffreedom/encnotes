#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密管理器 - 实现端到端加密
使用AES-256加密笔记内容，密码通过PBKDF2派生密钥
"""

import os
import base64
import hashlib
import keyring
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from typing import Optional, Tuple
import json
from pathlib import Path


class EncryptionManager:
    """加密管理器类"""
    
    # 钥匙串服务名称
    KEYRING_SERVICE = "com.encnotes.encryption"
    KEYRING_USERNAME = "master_key"
    
    # 加密配置
    SALT_SIZE = 32  # 盐值大小（字节）
    KEY_SIZE = 32   # AES-256密钥大小（字节）
    IV_SIZE = 16    # AES初始化向量大小（字节）
    ITERATIONS = 100000  # PBKDF2迭代次数
    
    def __init__(self):
        """初始化加密管理器"""
        self.encryption_key = None
        self.is_unlocked = False
        
        # 配置文件路径
        self.config_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "encryption_config.json"
        
        # 加载配置
        self.load_config()
        
    def load_config(self):
        """加载加密配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"加载加密配置失败: {e}")
                self.config = {}
        else:
            self.config = {}
            
    def save_config(self):
        """保存加密配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存加密配置失败: {e}")
            
    def is_password_set(self) -> bool:
        """检查是否已设置密码"""
        return 'password_hash' in self.config and 'salt' in self.config
        
    def setup_password(self, password: str) -> Tuple[bool, str]:
        """
        首次设置密码
        
        Args:
            password: 用户密码
            
        Returns:
            (成功标志, 消息)
        """
        if self.is_password_set():
            return False, "密码已设置，请使用修改密码功能"
            
        try:
            # 生成随机盐值
            salt = os.urandom(self.SALT_SIZE)
            
            # 生成密码哈希（用于验证）
            password_hash = self._hash_password(password, salt)
            
            # 派生加密密钥
            encryption_key = self._derive_key(password, salt)
            
            # 保存配置
            self.config['password_hash'] = base64.b64encode(password_hash).decode('utf-8')
            self.config['salt'] = base64.b64encode(salt).decode('utf-8')
            self.config['encryption_enabled'] = True
            self.save_config()
            
            # 保存密钥到钥匙串
            self._save_key_to_keychain(encryption_key)
            
            # 设置当前密钥
            self.encryption_key = encryption_key
            self.is_unlocked = True
            
            return True, "密码设置成功"
            
        except Exception as e:
            return False, f"设置密码失败: {e}"
            
    def verify_password(self, password: str) -> Tuple[bool, str]:
        """
        验证密码并解锁
        
        Args:
            password: 用户输入的密码
            
        Returns:
            (成功标志, 消息)
        """
        if not self.is_password_set():
            return False, "密码未设置"
            
        try:
            # 获取存储的盐值和密码哈希
            salt = base64.b64decode(self.config['salt'])
            stored_hash = base64.b64decode(self.config['password_hash'])
            
            # 计算输入密码的哈希
            input_hash = self._hash_password(password, salt)
            
            # 验证密码
            if input_hash != stored_hash:
                return False, "密码错误"
                
            # 派生加密密钥
            encryption_key = self._derive_key(password, salt)
            
            # 设置当前密钥
            self.encryption_key = encryption_key
            self.is_unlocked = True
            
            # 保存密钥到钥匙串（用于自动解锁）
            self._save_key_to_keychain(encryption_key)
            
            return True, "解锁成功"
            
        except Exception as e:
            return False, f"验证密码失败: {e}"
            
    def change_password(self, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        修改密码
        
        Args:
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (成功标志, 消息)
        """
        if not self.is_password_set():
            return False, "密码未设置"
            
        try:
            # 验证旧密码
            success, message = self.verify_password(old_password)
            if not success:
                return False, "旧密码错误"
                
            # 生成新的盐值
            new_salt = os.urandom(self.SALT_SIZE)
            
            # 生成新的密码哈希
            new_password_hash = self._hash_password(new_password, new_salt)
            
            # 派生新的加密密钥
            new_encryption_key = self._derive_key(new_password, new_salt)
            
            # 保存新配置
            self.config['password_hash'] = base64.b64encode(new_password_hash).decode('utf-8')
            self.config['salt'] = base64.b64encode(new_salt).decode('utf-8')
            self.save_config()
            
            # 更新钥匙串中的密钥
            self._save_key_to_keychain(new_encryption_key)
            
            # 更新当前密钥
            self.encryption_key = new_encryption_key
            
            return True, "密码修改成功"
            
        except Exception as e:
            return False, f"修改密码失败: {e}"
            
    def try_auto_unlock(self) -> bool:
        """
        尝试使用钥匙串自动解锁
        
        Returns:
            是否成功解锁
        """
        if not self.is_password_set():
            return False
            
        try:
            # 从钥匙串读取密钥
            key_str = keyring.get_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME)
            
            if key_str:
                # 解码密钥
                encryption_key = base64.b64decode(key_str)
                
                # 设置当前密钥
                self.encryption_key = encryption_key
                self.is_unlocked = True
                
                return True
                
        except Exception as e:
            print(f"自动解锁失败: {e}")
            
        return False
        
    def encrypt(self, plaintext: str) -> str:
        """
        加密文本
        
        Args:
            plaintext: 明文
            
        Returns:
            加密后的Base64编码字符串
        """
        if not self.is_unlocked:
            raise RuntimeError("加密管理器未解锁")
            
        try:
            # 生成随机IV
            iv = os.urandom(self.IV_SIZE)
            
            # 创建加密器
            cipher = Cipher(
                algorithms.AES(self.encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # 填充明文（PKCS7）
            plaintext_bytes = plaintext.encode('utf-8')
            padded_plaintext = self._pad(plaintext_bytes)
            
            # 加密
            ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()
            
            # 组合IV和密文
            encrypted_data = iv + ciphertext
            
            # Base64编码
            return base64.b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            raise RuntimeError(f"加密失败: {e}")
            
    def decrypt(self, ciphertext: str) -> str:
        """
        解密文本
        
        Args:
            ciphertext: 加密后的Base64编码字符串
            
        Returns:
            解密后的明文
        """
        if not self.is_unlocked:
            raise RuntimeError("加密管理器未解锁")
            
        try:
            # Base64解码
            encrypted_data = base64.b64decode(ciphertext)
            
            # 分离IV和密文
            iv = encrypted_data[:self.IV_SIZE]
            ciphertext_bytes = encrypted_data[self.IV_SIZE:]
            
            # 创建解密器
            cipher = Cipher(
                algorithms.AES(self.encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # 解密
            padded_plaintext = decryptor.update(ciphertext_bytes) + decryptor.finalize()
            
            # 去除填充
            plaintext_bytes = self._unpad(padded_plaintext)
            
            # 解码为字符串
            return plaintext_bytes.decode('utf-8')
            
        except Exception as e:
            raise RuntimeError(f"解密失败: {e}")
    
    def encrypt_data(self, data: bytes) -> Tuple[bool, bytes]:
        """
        加密二进制数据（用于附件）
        
        Args:
            data: 原始二进制数据
            
        Returns:
            (成功标志, 加密后的数据)
        """
        if not self.is_unlocked:
            return False, b""
            
        try:
            # 生成随机IV
            iv = os.urandom(self.IV_SIZE)
            
            # 创建加密器
            cipher = Cipher(
                algorithms.AES(self.encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # 填充数据（PKCS7）
            padded_data = self._pad(data)
            
            # 加密
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # 组合IV和密文
            encrypted_data = iv + ciphertext
            
            return True, encrypted_data
            
        except Exception as e:
            print(f"加密数据失败: {e}")
            return False, b""
    
    def decrypt_data(self, encrypted_data: bytes) -> Tuple[bool, bytes]:
        """
        解密二进制数据（用于附件）
        
        Args:
            encrypted_data: 加密后的数据
            
        Returns:
            (成功标志, 解密后的数据)
        """
        if not self.is_unlocked:
            return False, b""
            
        try:
            # 分离IV和密文
            iv = encrypted_data[:self.IV_SIZE]
            ciphertext = encrypted_data[self.IV_SIZE:]
            
            # 创建解密器
            cipher = Cipher(
                algorithms.AES(self.encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # 解密
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # 去除填充
            data = self._unpad(padded_data)
            
            return True, data
            
        except Exception as e:
            print(f"解密数据失败: {e}")
            return False, b""
            
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        从密码派生加密密钥
        
        Args:
            password: 用户密码
            salt: 盐值
            
        Returns:
            派生的密钥
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
        
    def _hash_password(self, password: str, salt: bytes) -> bytes:
        """
        生成密码哈希（用于验证）
        
        Args:
            password: 用户密码
            salt: 盐值
            
        Returns:
            密码哈希
        """
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            self.ITERATIONS
        )
        
    def _save_key_to_keychain(self, key: bytes):
        """
        保存密钥到系统钥匙串
        
        Args:
            key: 加密密钥
        """
        try:
            key_str = base64.b64encode(key).decode('utf-8')
            keyring.set_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME, key_str)
        except Exception as e:
            print(f"保存密钥到钥匙串失败: {e}")
            
    def _pad(self, data: bytes) -> bytes:
        """
        PKCS7填充
        
        Args:
            data: 原始数据
            
        Returns:
            填充后的数据
        """
        padding_length = 16 - (len(data) % 16)
        padding = bytes([padding_length] * padding_length)
        return data + padding
        
    def _unpad(self, data: bytes) -> bytes:
        """
        去除PKCS7填充
        
        Args:
            data: 填充后的数据
            
        Returns:
            原始数据
        """
        padding_length = data[-1]
        return data[:-padding_length]
        
    def lock(self):
        """锁定加密管理器"""
        self.encryption_key = None
        self.is_unlocked = False
        
    def clear_keychain(self):
        """清除钥匙串中的密钥"""
        try:
            keyring.delete_password(self.KEYRING_SERVICE, self.KEYRING_USERNAME)
        except Exception as e:
            print(f"清除钥匙串失败: {e}")
