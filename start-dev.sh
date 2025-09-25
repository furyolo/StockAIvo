#!/bin/bash

# StockAIvo 开发环境一键启动脚本 (Linux/Mac)
set -e

# 颜色设置
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BLUE='\033[94m'
RESET='\033[0m'

echo -e "${BLUE}🚀 StockAIvo 开发环境启动中...${RESET}"
echo

# 检查依赖
echo -e "${BLUE}检查依赖...${RESET}"

# 检查pnpm
if ! command -v pnpm &> /dev/null; then
    echo -e "${RED}错误: 未找到 pnpm，请先安装 pnpm${RESET}"
    echo "安装命令: npm install -g pnpm"
    exit 1
fi

# 检查uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}错误: 未找到 uv，请先安装 uv${RESET}"
    echo "下载地址: https://github.com/astral-sh/uv/releases"
    exit 1
fi

# 检查Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误: 未找到 Node.js，请先安装 Node.js${RESET}"
    echo "下载地址: https://nodejs.org/"
    exit 1
fi

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python，请先安装 Python 3.12+${RESET}"
    echo "下载地址: https://python.org/"
    exit 1
fi

# 检查Python版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${BLUE}Python版本: $PYTHON_VERSION${RESET}"

echo -e "${GREEN}✓ 依赖检查完成${RESET}"
echo

# 创建临时目录
TEMP_DIR="/tmp/stockaivo"
mkdir -p "$TEMP_DIR"

# 清理旧进程文件
rm -f "$TEMP_DIR/frontend.pid" "$TEMP_DIR/backend.pid"

# 启动前端服务
echo -e "${YELLOW}启动前端服务 (React + Vite)...${RESET}"
cd frontend

if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}安装前端依赖...${RESET}"
    pnpm install
fi

# 启动前端开发服务器（后台运行）
echo -e "${BLUE}启动前端服务器...${RESET}"
pnpm dev > "$TEMP_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$TEMP_DIR/frontend.pid"

cd ..

# 等待前端服务启动
echo -e "${BLUE}等待前端服务启动...${RESET}"
sleep 3

# 启动后端服务
echo -e "${YELLOW}启动后端服务 (FastAPI)...${RESET}"

if [ ! -d ".venv" ]; then
    echo -e "${BLUE}创建虚拟环境...${RESET}"
    uv venv
fi

# 激活虚拟环境并安装依赖
echo -e "${BLUE}检查后端依赖...${RESET}"
source .venv/bin/activate
uv sync --extra dev

# 启动后端开发服务器（后台运行）
echo -e "${BLUE}启动后端服务器...${RESET}"
uv run dev > "$TEMP_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$TEMP_DIR/backend.pid"

echo
echo -e "${GREEN}🎉 开发环境启动完成！${RESET}"
echo
echo -e "${BLUE}服务信息:${RESET}"
echo "   🔗 前端服务: http://localhost:3223"
echo "   🔗 后端API:  http://127.0.0.1:8000"
echo "   📖 API文档:  http://127.0.0.1:8000/docs"
echo
echo -e "${YELLOW}提示: 两个服务都在后台运行中${RESET}"
echo
echo -e "${BLUE}日志文件:${RESET}"
echo "   前端日志: $TEMP_DIR/frontend.log"
echo "   后端日志: $TEMP_DIR/backend.log"
echo
echo -e "${BLUE}快捷命令:${RESET}"
echo "  - 查看进程状态: ./start-dev.sh status"
echo "  - 停止所有服务: ./start-dev.sh stop"
echo "  - 查看前端日志: tail -f $TEMP_DIR/frontend.log"
echo "  - 查看后端日志: tail -f $TEMP_DIR/backend.log"
echo

# 处理命令行参数
case "${1:-}" in
    "status")
        echo -e "${BLUE}进程状态:${RESET}"
        if [ -f "$TEMP_DIR/frontend.pid" ] && kill -0 $(cat "$TEMP_DIR/frontend.pid") 2>/dev/null; then
            echo "  前端服务: 运行中 (PID: $(cat "$TEMP_DIR/frontend.pid"))"
        else
            echo "  前端服务: 已停止"
        fi
        
        if [ -f "$TEMP_DIR/backend.pid" ] && kill -0 $(cat "$TEMP_DIR/backend.pid") 2>/dev/null; then
            echo "  后端服务: 运行中 (PID: $(cat "$TEMP_DIR/backend.pid"))"
        else
            echo "  后端服务: 已停止"
        fi
        exit 0
        ;;
    "stop")
        echo -e "${YELLOW}停止所有服务...${RESET}"
        
        if [ -f "$TEMP_DIR/frontend.pid" ]; then
            FRONTEND_PID=$(cat "$TEMP_DIR/frontend.pid")
            if kill -0 $FRONTEND_PID 2>/dev/null; then
                kill $FRONTEND_PID
                echo -e "${GREEN}前端服务已停止${RESET}"
            fi
            rm -f "$TEMP_DIR/frontend.pid"
        fi
        
        if [ -f "$TEMP_DIR/backend.pid" ]; then
            BACKEND_PID=$(cat "$TEMP_DIR/backend.pid")
            if kill -0 $BACKEND_PID 2>/dev/null; then
                kill $BACKEND_PID
                echo -e "${GREEN}后端服务已停止${RESET}"
            fi
            rm -f "$TEMP_DIR/backend.pid"
        fi
        
        exit 0
        ;;
    "logs")
        echo -e "${BLUE}查看日志:${RESET}"
        echo "前端日志 (Ctrl+C 退出):"
        tail -f "$TEMP_DIR/frontend.log"
        ;;
    *)
        # 默认打开浏览器
        echo -e "${BLUE}按任意键打开浏览器访问前端...${RESET}"
        read -n 1 -s
        
        # 尝试打开浏览器
        if command -v open &> /dev/null; then
            open http://localhost:3223
        elif command -v xdg-open &> /dev/null; then
            xdg-open http://localhost:3223
        fi
        
        echo -e "${GREEN}🚀 StockAIvo 开发环境运行中！${RESET}"
        echo
        echo -e "${BLUE}使用 ./start-dev.sh stop 停止所有服务${RESET}"
        ;;
esac