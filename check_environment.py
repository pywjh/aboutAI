#!/usr/bin/env python3
import sys
import subprocess
import pkg_resources
import os
from pathlib import Path
import platform

def check_python_version():
    print("\n检查 Python 版本...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 版本过低。需要 Python 3.8 或更高版本")
        print(f"当前版本: Python {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python 版本符合要求: {version.major}.{version.minor}.{version.micro}")
    return True

def check_ffmpeg():
    print("\n检查 FFmpeg...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("✅ FFmpeg 已安装")
            return True
        else:
            print("❌ FFmpeg 未安装或无法访问")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg 未安装或未添加到系统路径")
        if platform.system() == "Darwin":
            print("建议使用 Homebrew 安装: brew install ffmpeg")
        elif platform.system() == "Windows":
            print("请从 https://ffmpeg.org/download.html 下载并添加到系统环境变量")
        else:
            print("请使用包管理器安装，如: sudo apt install ffmpeg")
        return False

def check_dependencies():
    print("\n检查 Python 依赖...")
    required = {}
    try:
        with open('requirements.txt', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    # 处理包名和版本要求
                    parts = line.strip().split('>=')
                    if len(parts) == 2:
                        required[parts[0]] = parts[1]
                    else:
                        required[line.strip()] = None
    except FileNotFoundError:
        print("❌ 未找到 requirements.txt 文件")
        return False

    all_satisfied = True
    for package, version in required.items():
        try:
            dist = pkg_resources.get_distribution(package)
            if version and pkg_resources.parse_version(dist.version) < pkg_resources.parse_version(version):
                print(f"❌ {package} 版本过低 (当前: {dist.version}, 需要: >={version})")
                all_satisfied = False
            else:
                print(f"✅ {package} 已安装 (版本: {dist.version})")
        except pkg_resources.DistributionNotFound:
            print(f"❌ 缺少依赖: {package}")
            all_satisfied = False

    return all_satisfied

def check_env_file():
    print("\n检查环境变量配置...")
    env_example = Path('.env.example')
    env_file = Path('.env')
    
    if not env_example.exists():
        print("❌ 未找到 .env.example 文件")
        return False
    
    if not env_file.exists():
        print("❌ 未找到 .env 文件，请复制 .env.example 并配置")
        return False
    
    required_vars = [
        'OPENROUTER_API_KEY',
        'UNSPLASH_ACCESS_KEY',
    ]
    
    missing_vars = []
    try:
        with open(env_file, 'r', encoding='utf-8') as f:  # 添加 encoding='utf-8'
            env_content = f.read()
            for var in required_vars:
                if var not in env_content or f"{var}=your-" in env_content:
                    missing_vars.append(var)
    except UnicodeDecodeError:
        # 如果 UTF-8 读取失败，尝试其他编码
        try:
            with open(env_file, 'r', encoding='gbk') as f:
                env_content = f.read()
                for var in required_vars:
                    if var not in env_content or f"{var}=your-" in env_content:
                        missing_vars.append(var)
        except UnicodeDecodeError:
            print("❌ 无法读取 .env 文件，请确保文件编码正确")
            return False
    
    if missing_vars:
        print("❌ 以下环境变量未正确配置:")
        for var in missing_vars:
            print(f"  - {var}")
        return False
    
    print("✅ 环境变量文件存在并包含必要配置")
    return True

def main():
    print("=== 小红书笔记生成器环境检查 ===")
    
    checks = [
        ("Python 版本", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("Python 依赖", check_dependencies),
        ("环境变量", check_env_file)
    ]
    
    all_passed = True
    for name, check in checks:
        if not check():
            all_passed = False
    
    print("\n=== 检查结果 ===")
    if all_passed:
        print("✅ 所有检查通过！可以开始使用小红书笔记生成器了。")
    else:
        print("❌ 存在一些问题需要解决。请根据上述提示进行修复。")

if __name__ == '__main__':
    main()
