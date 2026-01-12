# encnotes 代码签名配置说明

## 概述

本文档说明如何为 encnotes 应用配置代码签名和 iCloud 同步功能，以便在 macOS 上正常分发和运行。

## Apple Developer 配置步骤

### 前提条件

- 拥有 Apple Developer 账户（个人或组织账户，99 美元/年）
- 已登录 [Apple Developer](https://developer.apple.com/account/)

### 步骤 1: 创建 App ID

1. 登录 [Apple Developer](https://developer.apple.com/account/)
2. 进入 **Certificates, Identifiers & Profiles**
3. 点击左侧 **Identifiers**
4. 点击 **+** 按钮创建新的 Identifier
5. 选择 **App IDs**，点击 **Continue**
6. 选择 **App**，点击 **Continue**
7. 填写信息：
   - **Description**: `encnotes` (描述名称)
   - **Bundle ID**: 选择 **Explicit**，填写 `com.encnotes.app`
8. 在 **Capabilities** 中勾选：
   - ✅ **iCloud** (必选，用于笔记同步)
   - ✅ **Push Notifications** (可选，如需推送通知)
9. 点击 **Continue**，然后点击 **Register**

### 步骤 2: 配置 iCloud 容器

1. 在 **Identifiers** 页面，点击刚创建的 `com.encnotes.app`
2. 找到 **iCloud** 选项，点击 **Configure**
3. 点击 **+** 创建新容器，或选择 **Use existing container**
4. 如果创建新容器：
   - **Description**: `encnotes iCloud Container`
   - **Identifier**: `iCloud.com.encnotes.app` (必须以 `iCloud.` 开头)
5. 勾选刚创建的容器 `iCloud.com.encnotes.app`
6. 点击 **Continue**，然后点击 **Save**

### 步骤 3: 创建开发者证书

#### 3.1 创建证书签名请求 (CSR)

1. 打开 **钥匙串访问** (Keychain Access)
2. 菜单栏选择 **钥匙串访问 > 证书助理 > 从证书颁发机构请求证书**
3. 填写信息：
   - **用户电子邮件地址**: 你的 Apple ID 邮箱
   - **常用名称**: 你的名字或公司名
   - **CA 电子邮件地址**: 留空
   - 选择 **存储到磁盘**
4. 点击 **继续**，保存 CSR 文件到本地

#### 3.2 在 Apple Developer 创建证书

1. 在 Apple Developer 页面，点击左侧 **Certificates**
2. 点击 **+** 按钮
3. 选择 **Developer ID Application** (用于在 Mac App Store 外分发)
4. 点击 **Continue**
5. 上传刚才创建的 CSR 文件
6. 点击 **Continue**
7. 下载生成的证书文件 (`.cer`)

#### 3.3 安装证书

1. 双击下载的 `.cer` 文件
2. 证书会自动安装到 **钥匙串访问** 的 **登录** 钥匙串中
3. 在钥匙串中找到证书，确认名称类似：
   ```
   Developer ID Application: Your Name (TEAM_ID)
   ```

### 步骤 4: 获取 Team ID

1. 在 Apple Developer 页面，点击右上角账户名
2. 查看 **Membership** 信息
3. 记录 **Team ID** (10 位字符，如 `ABCDE12345`)

### 步骤 5: 验证配置

在终端运行以下命令，确认证书已正确安装：

```bash
security find-identity -v -p codesigning
```

应该看到类似输出：
```
1) ABCDEF1234567890ABCDEF1234567890ABCDEF12 "Developer ID Application: Your Name (TEAM_ID)"
   1 valid identities found
```

### 配置完成 ✅

现在你已经完成了 Apple Developer 的所有配置，可以继续进行代码签名和打包了。

---

## 文件说明

### 1. entitlements.plist
权限配置文件，定义应用所需的系统权限：

- **网络访问**: 允许应用进行网络通信
- **文件访问**: 允许读写用户选择的文件
- **钥匙串访问**: 允许访问 macOS 钥匙串存储密码
- **运行时权限**: 允许 JIT 编译和动态库加载（Python 应用必需）

### 2. encnotes.spec
PyInstaller 配置文件，已更新为：
- 从环境变量读取签名身份 (`CODESIGN_IDENTITY`)
- 指定 entitlements 文件路径

### 3. build_dmg.sh
构建脚本，已添加代码签名步骤：
- 签名所有动态库和框架
- 使用 hardened runtime 签名应用包
- 验证签名有效性

## 使用方法

### 开发环境（不签名）

直接运行构建脚本，会跳过代码签名：

```bash
cd build_scripts
./build_dmg.sh
```

### 生产环境（签名）

#### 1. 获取开发者证书

从 Apple Developer 账户获取 "Developer ID Application" 证书，并安装到钥匙串。

#### 2. 查看可用的签名身份

```bash
security find-identity -v -p codesigning
```

输出示例：
```
1) ABCDEF1234567890 "Developer ID Application: Your Name (TEAM_ID)"
```

#### 3. 设置环境变量

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"
```

或者添加到 `~/.zshrc` 或 `~/.bash_profile`：

```bash
echo 'export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"' >> ~/.zshrc
source ~/.zshrc
```

#### 4. 运行构建脚本

```bash
cd build_scripts
./build_dmg.sh
```

脚本会自动：
1. 打包应用
2. 对所有库和框架进行签名
3. 对应用包进行签名（使用 entitlements）
4. 验证签名
5. 创建 DMG 安装包

## 签名验证

### 验证应用签名

```bash
codesign --verify --deep --strict --verbose=2 dist/encnotes.app
```

### 查看签名信息

```bash
codesign -dv --verbose=4 dist/encnotes.app
```

### 查看 entitlements

```bash
codesign -d --entitlements - dist/encnotes.app
```

## 公证（Notarization）

如果需要在其他 Mac 上分发应用，还需要进行公证：

### 1. 创建应用专用密码

访问 https://appleid.apple.com/account/manage 创建应用专用密码。

### 2. 存储凭证

```bash
xcrun notarytool store-credentials "encnotes-notary" \
  --apple-id "your-email@example.com" \
  --team-id "TEAM_ID" \
  --password "app-specific-password"
```

### 3. 提交公证

```bash
xcrun notarytool submit dist/encnotes-3.4.0.dmg \
  --keychain-profile "encnotes-notary" \
  --wait
```

### 4. 装订公证票据

```bash
xcrun stapler staple dist/encnotes-3.4.0.dmg
```

### 5. 验证公证

```bash
spctl -a -vv -t install dist/encnotes-3.4.0.dmg
```

## 常见问题

### Q: 签名失败，提示找不到证书

**A**: 确保已安装 "Developer ID Application" 证书到钥匙串，并且证书有效。

### Q: 应用在其他 Mac 上无法打开

**A**: 需要进行公证（Notarization），或者用户需要在"系统偏好设置 > 安全性与隐私"中允许运行。

### Q: 签名后应用无法启动

**A**: 检查 entitlements.plist 配置，确保包含必要的运行时权限：
- `com.apple.security.cs.allow-jit`
- `com.apple.security.cs.allow-unsigned-executable-memory`

### Q: 如何测试签名是否有效

**A**: 使用以下命令：
```bash
# 验证签名
codesign --verify --deep --strict dist/encnotes.app

# 测试 Gatekeeper
spctl -a -vv dist/encnotes.app
```

## 参考资料

- [Apple Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/)
- [Notarizing macOS Software](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [Hardened Runtime](https://developer.apple.com/documentation/security/hardened_runtime)
- [Entitlements](https://developer.apple.com/documentation/bundleresources/entitlements)

## 环境变量总结

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `CODESIGN_IDENTITY` | 代码签名身份 | `"Developer ID Application: Your Name (TEAM_ID)"` |

## 文件清单

```
build_scripts/
├── entitlements.plist      # 权限配置文件（新增）
├── encnotes.spec           # PyInstaller 配置（已更新）
├── build_dmg.sh            # 构建脚本（已更新）
└── CODESIGN.md             # 本文档（新增）
```
