#!/bin/bash

echo "================================================================================"
echo "智能电商客服RAG系统 - 自动安装脚本 (Linux/Mac)"
echo "版本: v2.1.0"
echo "================================================================================"
echo ""

# 检查 Python
echo "[1/4] 检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到 Python3，请先安装 Python 3.8+"
    exit 1
fi
python3 --version
echo "✅ Python 已安装"
echo ""

# 安装依赖
echo "[2/4] 安装依赖包..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败"
    exit 1
fi
echo "✅ 依赖安装完成"
echo ""

# 运行迁移（可选）
echo "[3/4] 可选：运行迁移脚本..."
if [ -f "migrate_to_v2.1.py" ]; then
    python3 migrate_to_v2.1.py
    if [ $? -ne 0 ]; then
        echo "⚠️  迁移脚本执行失败，但可以继续"
    fi
else
    echo "(跳过) 未找到 migrate_to_v2.1.py"
fi
echo ""

# 运行测试（可选）
echo "[4/4] 可选：运行测试验证..."
if [ -f "test_critical_fixes.py" ]; then
    python3 test_critical_fixes.py
    if [ $? -ne 0 ]; then
        echo "⚠️  部分测试失败，请检查错误信息"
    fi
else
    echo "(跳过) 未找到 test_critical_fixes.py"
fi
echo ""

echo "================================================================================"
echo "🎉 安装完成！"
echo "================================================================================"
echo ""
echo "启动应用:"
echo "  客户端:     python3 main.py"
echo "  管理后台:   python3 run_admin.py"
echo ""
echo "默认账号: admin / admin123 (首次登录后请修改密码)"
echo ""
echo "================================================================================"
