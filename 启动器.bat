@echo off
chcp 65001 > nul
echo 正在启动小红书笔记生成器...
echo.

:: 检查Python是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保已安装Python并添加到系统环境变量中
    echo 请访问 https://www.python.org/downloads/ 下载并安装Python 3.8或更高版本
    echo.
    pause
    exit /b
)

:: 获取脚本所在目录
cd /d "%~dp0"

:: 启动程序
echo 正在启动程序，请稍候...
echo.
python gui.py

:: 如果程序启动失败，显示错误信息
if errorlevel 1 (
    echo.
    echo [错误] 程序启动失败，请检查以下几点：
    echo 1. 确保已安装所有必需的Python包
    echo 2. 确保Python版本在3.8-3.11之间
    echo 3. 检查是否有杀毒软件阻止程序运行
    echo.
    echo 如需安装依赖，请运行以下命令：
    echo pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    pause
)