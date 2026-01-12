# CloudKit Web Services 详解

## 概述

CloudKit Web Services 是 Apple 提供的基于 HTTP 的 REST API，允许开发者通过标准的 Web 请求访问 CloudKit 数据库，而无需使用原生的 iOS/macOS SDK。

## 工作机制

### 架构图

```
┌──────────────────┐
│  Python 应用      │
│  (encnotes)      │
└────────┬─────────┘
         │ HTTPS + JSON
         │
         ▼
┌──────────────────────────────────┐
│  CloudKit Web Services API       │
│  https://api.apple-cloudkit.com  │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  CloudKit 数据库                  │
│  ├── Public Database             │
│  ├── Private Database            │
│  └── Shared Database             │
└──────────────────────────────────┘
```

### 核心特点

1. **跨平台** - 可在 Windows、Linux、macOS 上使用
2. **语言无关** - 支持任何能发送 HTTP 请求的语言
3. **标准协议** - 使用 REST API 和 JSON
4. **无需原生框架** - 不依赖 PyObjC、Swift 等

## API 端点

### 基础 URL

```
https://api.apple-cloudkit.com/database/1/{container}/{environment}/{database}/
```

参数说明：
- `container`: CloudKit 容器 ID（如 `iCloud.com.encnotes.app`）
- `environment`: 环境（`development` 或 `production`）
- `database`: 数据库类型（`public`、`private` 或 `shared`）

### 主要操作端点

| 操作 | 端点 | 方法 | 说明 |
|------|------|------|------|
| 查询记录 | `records/lookup` | POST | 根据 recordName 查询 |
| 搜索记录 | `records/query` | POST | 使用查询条件搜索 |
| 修改记录 | `records/modify` | POST | 创建、更新、删除记录 |
| 查询区域 | `zones/lookup` | POST | 查询自定义区域 |
| 修改区域 | `zones/modify` | POST | 创建、修改区域 |

## 认证机制

### 1. Server-to-Server 认证（推荐）

使用 API Token 进行认证，适合服务器端应用。

#### 获取 API Token

1. 访问 [CloudKit Dashboard](https://icloud.developer.apple.com/dashboard/)
2. 选择你的容器
3. 进入 "API Access" 标签
4. 生成 Server-to-Server Key

#### 使用示例

```python
import requests
import json

# API Token（从 CloudKit Dashboard 获取）
API_TOKEN = "your_api_token_here"

# 容器配置
CONTAINER_ID = "iCloud.com.encnotes.app"
ENVIRONMENT = "development"  # 或 "production"
DATABASE = "private"

# 基础 URL
BASE_URL = f"https://api.apple-cloudkit.com/database/1/{CONTAINER_ID}/{ENVIRONMENT}/{DATABASE}/"

# 请求头
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# 查询记录
def query_records(record_type):
    url = BASE_URL + "records/query"
    payload = {
        "query": {
            "recordType": record_type
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# 创建记录
def create_record(record_type, fields):
    url = BASE_URL + "records/modify"
    payload = {
        "operations": [{
            "operationType": "create",
            "record": {
                "recordType": record_type,
                "fields": fields
            }
        }]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
```

### 2. User 认证

使用用户的 iCloud 凭证进行认证，需要实现签名算法。

```python
import hmac
import hashlib
import base64
from datetime import datetime

def generate_signature(date, request_body, private_key):
    """生成请求签名"""
    message = f"{date}:{request_body}"
    signature = hmac.new(
        private_key.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()

# 使用签名
date = datetime.utcnow().isoformat() + 'Z'
signature = generate_signature(date, request_body, private_key)

headers = {
    "X-Apple-CloudKit-Request-KeyID": key_id,
    "X-Apple-CloudKit-Request-ISO8601Date": date,
    "X-Apple-CloudKit-Request-SignatureV1": signature,
    "Content-Type": "application/json"
}
```

## 数据格式

### 记录结构

```json
{
  "recordType": "Note",
  "recordName": "unique-id-123",
  "fields": {
    "title": {
      "value": "我的笔记"
    },
    "content": {
      "value": "笔记内容..."
    },
    "created": {
      "value": 1641024000000,
      "type": "TIMESTAMP"
    },
    "tags": {
      "value": ["工作", "重要"],
      "type": "STRING_LIST"
    }
  }
}
```

### 字段类型

| CloudKit 类型 | JSON 表示 | 说明 |
|--------------|----------|------|
| String | `{"value": "text"}` | 字符串 |
| Int64 | `{"value": 123}` | 整数 |
| Double | `{"value": 3.14}` | 浮点数 |
| Timestamp | `{"value": 1641024000000}` | 时间戳（毫秒） |
| Bytes | `{"value": "base64..."}` | 二进制数据 |
| String List | `{"value": ["a", "b"]}` | 字符串数组 |
| Asset | `{"value": {...}}` | 文件资源 |

## 完整实现示例

### CloudKit Web Services 客户端

```python
import requests
import json
from typing import Dict, List, Optional
from datetime import datetime

class CloudKitWebClient:
    """CloudKit Web Services 客户端"""
    
    def __init__(self, container_id: str, api_token: str, 
                 environment: str = "development"):
        """
        初始化客户端
        
        Args:
            container_id: CloudKit 容器 ID
            api_token: API Token（从 CloudKit Dashboard 获取）
            environment: 环境（development 或 production）
        """
        self.container_id = container_id
        self.api_token = api_token
        self.environment = environment
        self.base_url = (
            f"https://api.apple-cloudkit.com/database/1/"
            f"{container_id}/{environment}/private/"
        )
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def query_records(self, record_type: str, 
                     filters: Optional[List[Dict]] = None) -> Dict:
        """
        查询记录
        
        Args:
            record_type: 记录类型
            filters: 查询过滤条件
            
        Returns:
            查询结果
        """
        url = self.base_url + "records/query"
        
        query = {"recordType": record_type}
        if filters:
            query["filterBy"] = filters
        
        payload = {"query": query}
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def create_record(self, record_type: str, fields: Dict) -> Dict:
        """
        创建记录
        
        Args:
            record_type: 记录类型
            fields: 字段数据
            
        Returns:
            创建结果
        """
        url = self.base_url + "records/modify"
        
        # 转换字段格式
        cloudkit_fields = {}
        for key, value in fields.items():
            if isinstance(value, str):
                cloudkit_fields[key] = {"value": value}
            elif isinstance(value, int):
                cloudkit_fields[key] = {"value": value}
            elif isinstance(value, list):
                cloudkit_fields[key] = {"value": value}
            elif isinstance(value, datetime):
                cloudkit_fields[key] = {
                    "value": int(value.timestamp() * 1000),
                    "type": "TIMESTAMP"
                }
        
        payload = {
            "operations": [{
                "operationType": "create",
                "record": {
                    "recordType": record_type,
                    "fields": cloudkit_fields
                }
            }]
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def update_record(self, record_name: str, record_type: str, 
                     fields: Dict) -> Dict:
        """
        更新记录
        
        Args:
            record_name: 记录名称
            record_type: 记录类型
            fields: 要更新的字段
            
        Returns:
            更新结果
        """
        url = self.base_url + "records/modify"
        
        cloudkit_fields = {}
        for key, value in fields.items():
            if isinstance(value, str):
                cloudkit_fields[key] = {"value": value}
            elif isinstance(value, int):
                cloudkit_fields[key] = {"value": value}
        
        payload = {
            "operations": [{
                "operationType": "update",
                "record": {
                    "recordName": record_name,
                    "recordType": record_type,
                    "fields": cloudkit_fields
                }
            }]
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def delete_record(self, record_name: str) -> Dict:
        """
        删除记录
        
        Args:
            record_name: 记录名称
            
        Returns:
            删除结果
        """
        url = self.base_url + "records/modify"
        
        payload = {
            "operations": [{
                "operationType": "delete",
                "record": {
                    "recordName": record_name
                }
            }]
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

# 使用示例
if __name__ == "__main__":
    # 初始化客户端
    client = CloudKitWebClient(
        container_id="iCloud.com.encnotes.app",
        api_token="your_api_token_here",
        environment="development"
    )
    
    # 创建笔记
    result = client.create_record(
        record_type="Note",
        fields={
            "title": "测试笔记",
            "content": "这是通过 Web Services 创建的笔记",
            "created": datetime.now(),
            "tags": ["测试", "Web Services"]
        }
    )
    print("创建成功:", result)
    
    # 查询笔记
    notes = client.query_records(record_type="Note")
    print("查询结果:", notes)
```

## 优缺点分析

### ✅ 优点

1. **跨平台支持**
   - 可在任何操作系统上运行
   - 不依赖 macOS 特定框架

2. **语言无关**
   - 可用任何编程语言实现
   - 使用标准的 HTTP 和 JSON

3. **稳定可靠**
   - 不会出现 PyObjC 的崩溃问题
   - Apple 官方维护的 API

4. **易于调试**
   - 可以使用 curl、Postman 等工具测试
   - 请求和响应都是可读的 JSON

5. **服务器端友好**
   - 适合后端服务集成
   - 支持批量操作

### ❌ 缺点

1. **需要额外配置**
   - 需要在 CloudKit Dashboard 生成 API Token
   - 需要配置容器权限

2. **功能受限**
   - 不支持某些高级特性（如 CKShare）
   - 订阅功能有限

3. **网络延迟**
   - 每次操作都需要网络请求
   - 比原生 SDK 慢

4. **认证复杂**
   - User 认证需要实现签名算法
   - Token 管理需要额外工作

5. **成本考虑**
   - 每次请求都计入 API 配额
   - 大量操作可能产生费用

## 与其他方案对比

| 特性 | PyObjC CloudKit | CloudKit Web Services | Swift 桥接 |
|------|----------------|----------------------|-----------|
| 跨平台 | ❌ 仅 macOS | ✅ 全平台 | ❌ 仅 macOS |
| 稳定性 | ❌ 易崩溃 | ✅ 稳定 | ✅ 稳定 |
| 性能 | ⚠️ 中等 | ⚠️ 较慢 | ✅ 快 |
| 功能完整性 | ✅ 完整 | ⚠️ 部分 | ✅ 完整 |
| 实现难度 | ⚠️ 中等 | ✅ 简单 | ❌ 复杂 |
| 维护成本 | ⚠️ 中等 | ✅ 低 | ❌ 高 |

## 适用场景

### ✅ 适合使用 Web Services

1. **跨平台应用** - 需要在 Windows/Linux 上运行
2. **服务器端同步** - 后端服务需要访问 CloudKit
3. **简单的 CRUD 操作** - 基本的增删改查
4. **原型开发** - 快速验证想法

### ❌ 不适合使用 Web Services

1. **需要实时推送** - 需要 CKSubscription
2. **大量小请求** - 会产生较高延迟
3. **复杂的共享功能** - CKShare 支持有限
4. **离线优先应用** - 需要本地缓存和同步

## 实施建议

### 对于 encnotes 项目

**推荐使用 CloudKit Web Services**，原因：

1. ✅ 避免 PyObjC 崩溃问题
2. ✅ 实现简单，维护成本低
3. ✅ 功能足够满足笔记同步需求
4. ✅ 可以在未来迁移到其他平台

### 实施步骤

1. **获取 API Token**
   - 登录 CloudKit Dashboard
   - 生成 Server-to-Server Key

2. **实现客户端**
   - 创建 `cloudkit_web_client.py`
   - 实现基本的 CRUD 操作

3. **集成到现有代码**
   - 修改 `icloud_sync.py`
   - 使用 Web Services 替代原生 SDK

4. **测试验证**
   - 在开发环境测试
   - 验证跨设备同步

## 参考资料

- [CloudKit Web Services 官方文档](https://developer.apple.com/documentation/cloudkitjs/cloudkit/cloudkit_web_services)
- [CloudKit Dashboard](https://icloud.developer.apple.com/dashboard/)
- [CloudKit JS 参考](https://developer.apple.com/documentation/cloudkitjs)

## 总结

CloudKit Web Services 是一个**稳定、可靠、易于实现**的方案，特别适合 Python 应用。虽然在功能和性能上不如原生 SDK，但对于笔记同步这样的场景已经完全足够，而且可以避免 PyObjC 的各种问题。

**建议：将 CloudKit Web Services 作为 encnotes 的首选同步方案。**
