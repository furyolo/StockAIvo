# 构建阶段
FROM node:25.7.0-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制依赖文件
COPY frontend/package.json frontend/pnpm-lock.yaml ./

# 安装 pnpm
RUN npm install -g pnpm

# 清理可能存在的缓存
RUN rm -rf node_modules

# 安装所有依赖
RUN pnpm install --frozen-lockfile

# 复制源代码
COPY frontend/ ./

# 构建应用（使用生产模式）
RUN pnpm run build

# 生产阶段
FROM nginx:stable-alpine AS frontend-production

# 复制构建产物
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY docker/nginx.conf /etc/nginx/nginx.conf

# 暴露端口
EXPOSE 80

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]
