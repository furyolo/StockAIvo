# StockAIvo

智能美股数据与分析平台后端。


## 功能特性
- 实时美股行情与历史数据获取
- 股票基本面、财报、新闻等多维度数据整合
- 基于AI的智能分析与预测（如趋势判断、情感分析等）
- FastAPI 提供高性能 RESTful API
- 支持定时任务与数据自动更新
- Redis 缓存加速数据访问
- 支持多因子选股与策略回测
- 可扩展的插件式 AI Agent 架构

## 安装指南

### 1. 克隆仓库
```bash
git clone https://github.com/your-username/StockAIvo.git
cd StockAIvo
```

### 2. 创建并同步虚拟环境
本项目使用 [uv](https://github.com/astral-sh/uv) 作为包管理器。
```bash
# 创建虚拟环境并安装所有依赖
uv sync

# 如果需要进行开发，请安装开发依赖
uv sync --dev
```


### 3. 配置环境变量
复制 `.env.example` (如果提供) 或手动创建一个 `.env` 文件，并填入必要的环境变量。

**.env 文件示例:**
```
DATABASE_URL="postgresql://user:password@host:port/database"
REDIS_URL="redis://host:port"
GOOGLE_API_KEY="your_google_api_key"
# 可选：用于接入第三方AI服务
OPENAI_API_KEY="your_openai_api_key"
SERPER_API_KEY="your_serper_api_key"
```


## 如何运行

### 开发模式
此模式下，服务会以热重载方式启动。
```bash
uv run dev
```

### 生产模式
```bash
uv run start
```
服务将在 `http://127.0.0.1:8000` 上可用。

## 目录结构简介

```
stockaivo/
  ├─ ai/                # AI智能体与相关服务
  ├─ routers/           # FastAPI 路由
  ├─ scripts/           # 启动与运维脚本
  ├─ tests/             # 单元测试
  ├─ data_service.py    # 数据服务主模块
  ├─ database.py        # 数据库连接与操作
  └─ ...
memory-bank/            # 记忆库与上下文管理
README.md               # 项目说明
pyproject.toml          # 项目依赖与配置
uv.lock                 # 锁定依赖版本
```

## 测试

```bash
uv pip install --system -r requirements-dev.txt  # 如有开发依赖
pytest tests/
```

## 贡献指南

欢迎提交 issue 和 PR！请遵循项目代码规范，提交前请确保所有测试通过。

## License

MIT