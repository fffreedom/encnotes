# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller 配置文件 - encnotes 应用
用于将 PyQt6 应用打包为独立的 macOS .app 文件
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 获取项目根目录
block_cipher = None

# 收集数据文件（matplotlib等库的数据）
datas = []

# 收集 matplotlib 的所有数据文件
try:
    mpl_datas = collect_data_files('matplotlib', include_py_files=False)
    datas.extend(mpl_datas)
except Exception:
    pass

# 收集 lxml 的数据文件
try:
    lxml_datas = collect_data_files('lxml', include_py_files=False)
    datas.extend(lxml_datas)
except Exception:
    pass

# 隐藏导入 - PyInstaller 可能无法自动检测到的模块
hiddenimports = [
    # PyQt6 相关
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
    
    # matplotlib 相关
    'matplotlib.backends.backend_agg',
    'matplotlib.backends.backend_pdf',
    'matplotlib.figure',
    'matplotlib.patches',
    'matplotlib.text',
    'matplotlib.path',
    'matplotlib.font_manager',
    'matplotlib._mathtext_data',
    'matplotlib._data',
    'matplotlib._cm',
    
    # lxml 相关
    'lxml._elementpath',
    'lxml.etree',
    'lxml._elementpath',
    
    # cryptography 相关
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.backends.openssl',
    
    # keyring 相关
    'keyring.backends',
    'keyring.backends.macOS',
    
    # 其他依赖
    'PIL._tkinter_finder',
    'docx',
    'bs4',
    'html2text',
]

# 排除不需要的模块以减小体积
excludes = [
    'tkinter',
    'unittest',
    'test',
    'pydoc',
    'distutils',
    'setuptools',
    'pip',
]

a = Analysis(
    ['../main.py'],  # 主入口文件
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤不需要的文件
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='encnotes',  # 可执行文件名称
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 启用 UPX 压缩以减小体积
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=os.environ.get('CODESIGN_IDENTITY'),  # 从环境变量读取签名身份
    entitlements_file='entitlements.plist',  # 权限配置文件
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='encnotes',  # 收集目录名称
)

# 创建 macOS 应用包
app = BUNDLE(
    coll,
    name='encnotes.app',  # 应用包名称
    icon='icon.icns',  # 应用图标
    bundle_identifier='com.encnotes.app',  # Bundle ID
    version='3.3.0',  # 应用版本
    info_plist={
        'CFBundleDisplayName': '加密笔记',  # 显示名称
        'CFBundleName': 'encnotes',
        'CFBundleShortVersionString': '3.3.0',
        'CFBundleVersion': '3.3.0',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',
        'CFBundleExecutable': 'encnotes',
        'CFBundleIconFile': 'AppIcon',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',  # 最低系统版本
        'NSRequiresAquaSystemAppearance': False,
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeExtensions': ['enc', 'encnotes'],
                'CFBundleTypeName': 'EncNotes Document',
                'CFBundleTypeRole': 'Editor',
                'LSHandlerRank': 'Owner',
                'LSTypeIsPackage': False,
            },
        ],
    },
)
