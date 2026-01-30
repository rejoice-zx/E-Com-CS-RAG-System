@echo off
chcp 65001 >nul
echo ================================================================================
echo 智能电商客服RAG系统 - 自动安装脚本 (Windows)
echo 版本: v2.1.0
echo ================================================================================
echo.

echo [1/4] 检查 Python 版本...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo ✅ Python 已安装
echo.

echo [2/4] 安装依赖包...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)
echo ✅ 依赖安装完成
echo.

echo [3/4] 可选：运行迁移脚本...
if exist migrate_to_v2.1.py (
    python migrate_to_v2.1.py
    if errorlevel 1 (
        echo ⚠️  迁移脚本执行失败，但可以继续
    )
) else (
    echo (跳过) 未找到 migrate_to_v2.1.py
)
echo.

echo [4/4] 可选：运行测试验证...
if exist test_critical_fixes.py (
    python test_critical_fixes.py
    if errorlevel 1 (
        echo ⚠️  部分测试失败，请检查错误信息
    )
) else (
    echo (跳过) 未找到 test_critical_fixes.py
)
echo.

echo ================================================================================
echo 🎉 安装完成！
echo ================================================================================
echo.
echo 启动应用:
echo   客户端:     python main.py
echo   管理后台:   python run_admin.py
echo.
echo 默认账号: admin / admin123 (首次登录后请修改密码)
echo.
echo ================================================================================
pause
