@echo off
echo 正在启动 Outlook Email Plus 项目...

:: 切换到项目目录
cd /d D:\outlookEmailPlus-main\outlookEmailPlus-main

:: 启动 Flask 应用
start cmd /k "python web_outlook_app.py"

:: 等待2秒确保服务启动
timeout /t 2 /nobreak >nul

:: 打开默认Chrome浏览器（使用配置0）
start chrome --profile-directory="Default" http://127.0.0.1:5000/