# 多阶段构建，统一使用 Python 3.13 Alpine Linux 精简镜像
FROM python:3.13.7-alpine AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_PYTHON=python3.13.7

# 构建阶段仅安装编译所需依赖
RUN apk update \
    && apk add --no-cache \
    build-base \
    postgresql-dev

# 安装 uv，负责创建虚拟环境并锁定依赖
RUN pip install --no-cache-dir uv

# 先复制依赖文件，充分利用构建缓存
COPY pyproject.toml uv.lock ./

# 创建虚拟环境并安装锁定依赖
RUN uv venv \
    && uv sync --frozen

# 清理虚拟环境中的缓存与编译产物，减小体积
RUN find .venv -name "__pycache__" -type d -prune -exec rm -rf {} + \
    && find .venv -name "*.pyc" -delete


FROM python:3.13.7-alpine AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:${PATH}"

# 运行阶段仅安装最小化运行时依赖
RUN apk update \
    && apk add --no-cache \
    postgresql-libs \
    curl \
    tzdata

# 安装 uv CLI，保证启动命令可用
RUN pip install --no-cache-dir uv

# 复制虚拟环境到运行层
COPY --from=builder /app/.venv /app/.venv

# 复制应用源代码（.dockerignore 已排除无关文件）
COPY . .

# 创建应用用户并授予目录权限
RUN adduser -D -s /bin/sh app \
    && mkdir -p logs/frontend logs/backend \
    && chown -R app:app /app

USER app

EXPOSE 3224

HEALTHCHECK --interval=24h --timeout=10s --start-period=5s --retries=1 \
    CMD /bin/sh -c 'if [ ! -f /tmp/.healthcheck_done ]; then curl -f http://localhost:3224/health && touch /tmp/.healthcheck_done; else exit 0; fi'

CMD ["uv", "run", "start"]
