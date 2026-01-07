#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成应用图标 (.icns) 文件
需要提供一个 1024x1024 的 PNG 图片作为源文件
"""

import os
import sys
import subprocess
from pathlib import Path


def create_iconset(source_png, output_icns):
    """
    从 PNG 图片创建 .icns 图标文件
    
    Args:
        source_png: 源 PNG 文件路径 (建议 1024x1024)
        output_icns: 输出 .icns 文件路径
    """
    if not os.path.exists(source_png):
        print(f"错误: 源文件不存在: {source_png}")
        return False
    
    # 创建临时 iconset 目录
    iconset_dir = "icon.iconset"
    os.makedirs(iconset_dir, exist_ok=True)
    
    # 需要生成的图标尺寸
    sizes = [
        (16, "16x16"),
        (32, "16x16@2x"),
        (32, "32x32"),
        (64, "32x32@2x"),
        (128, "128x128"),
        (256, "128x128@2x"),
        (256, "256x256"),
        (512, "256x256@2x"),
        (512, "512x512"),
        (1024, "512x512@2x"),
    ]
    
    print("生成各种尺寸的图标...")
    for size, name in sizes:
        output_file = os.path.join(iconset_dir, f"icon_{name}.png")
        cmd = [
            "sips",
            "-z", str(size), str(size),
            source_png,
            "--out", output_file
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  ✓ {name} ({size}x{size})")
    
    # 转换为 .icns
    print(f"\n生成 .icns 文件: {output_icns}")
    cmd = ["iconutil", "-c", "icns", iconset_dir, "-o", output_icns]
    subprocess.run(cmd, check=True)
    
    # 清理临时文件
    import shutil
    shutil.rmtree(iconset_dir)
    
    print(f"✓ 图标创建成功: {output_icns}")
    return True


def create_default_icon(output_icns):
    """
    创建一个默认的应用图标
    使用 Python PIL 库生成一个简单的图标
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("错误: 需要安装 Pillow 库")
        print("运行: pip install Pillow")
        return False
    
    # 创建 1024x1024 的图片
    size = 1024
    img = Image.new('RGB', (size, size), color='#4A90E2')
    draw = ImageDraw.Draw(img)
    
    # 绘制圆角矩形背景
    margin = 100
    draw.rounded_rectangle(
        [(margin, margin), (size-margin, size-margin)],
        radius=150,
        fill='#5BA3F5'
    )
    
    # 绘制数学符号
    try:
        # 尝试使用系统字体
        font_size = 400
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    # 绘制 Σ 符号
    text = "Σ"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 50
    
    draw.text((x, y), text, fill='white', font=font)
    
    # 保存为临时 PNG
    temp_png = "temp_icon.png"
    img.save(temp_png, 'PNG')
    
    # 转换为 .icns
    success = create_iconset(temp_png, output_icns)
    
    # 清理临时文件
    if os.path.exists(temp_png):
        os.remove(temp_png)
    
    return success


def main():
    """主函数"""
    script_dir = Path(__file__).parent
    
    print("=" * 50)
    print("  encnotes 图标生成工具")
    print("=" * 50)
    print()
    
    # 检查是否提供了源图片
    if len(sys.argv) > 1:
        source_png = sys.argv[1]
        if not os.path.exists(source_png):
            print(f"错误: 文件不存在: {source_png}")
            return 1
        
        output_icns = script_dir / "icon.icns"
        if create_iconset(source_png, str(output_icns)):
            return 0
        else:
            return 1
    else:
        # 创建默认图标
        print("未提供源图片，将创建默认图标")
        print("提示: 可以使用自定义图片: python create_icon.py your_icon.png")
        print()
        
        output_icns = script_dir / "icon.icns"
        if create_default_icon(str(output_icns)):
            return 0
        else:
            return 1


if __name__ == "__main__":
    sys.exit(main())
