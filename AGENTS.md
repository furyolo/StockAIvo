# Repository Guidelines

## 项目结构与模块组织
- `backend/`：FastAPI 后端子项目，内含 `stockaivo/` 业务模块、`database_migrations/` 迁移脚本、`tests/` PyTest 用例，以及 `main.py`、`pyproject.toml`、`Dockerfile` 等运行入口与构建文件。
- `frontend/`：React 19 + Vite 前端界面，整合 Mantine 组件与 TradingView 图表；静态资源统一存放于 `frontend/src/assets/`。
- `docker/`：Docker Compose 与 Nginx 配置，支撑多容器部署。
- `docs/`：运维手册、历史任务与实施方案。
- `logs/`：本地调试日志目录，可根据需要挂载或清理。
- `.env` / `.env.example`：运行所需密钥模板；`start-dev.sh(.bat)` 提供一键开发脚本。

## 构建、测试与开发命令
- 后端依赖：在 `backend/` 下运行 `uv sync --extra dev`；启动开发服务：`cd backend && uv run dev`；生产模式请使用 `cd backend && uv run start`。
- 前端：进入 `frontend` 执行 `pnpm install` 安装依赖，`pnpm dev` 启动本地调试，`pnpm build` 生成产物，`pnpm preview` 验证打包结果。
- 容器一键体验：`docker-compose up --build` 会启动 FastAPI、Redis、PostgreSQL、前端与 Nginx 反向代理。

## 容器化与运维注意事项
- 后端镜像采用多阶段构建并复用 `.venv`，体积稳定在 ~1.3GB；如需再次精简请优先排查大体积依赖。
- `HEALTHCHECK` 仅在容器首次就绪时执行一次（通过 `/tmp/.healthcheck_done` 标记），不要恢复到 30 秒轮询以免截断 SSE。
- 前端与容器生产环境统一通过 `/api/` 访问后端；Nginx 已关闭请求/响应缓冲、gzip 与 `proxy_request_buffering`，保证流式输出完整。
- `.env` 中的 `OPENAI_API_BASE` 在容器内需指向 `http://host.docker.internal:<port>/v1` 或同网段域名，避免使用 `localhost`。
- 通过 `docker logs -f stockaivo-backend-1` 可观察 SSE 输出、健康检查与定时任务日志。

## 代码风格与命名约定
- Python 统一使用 4 空格缩进、`snake_case` 函数名、`PascalCase` 类名，并保持关键路径添加类型注解；提交前运行 `uv run mypy stockaivo`。
- TypeScript 采用 ESLint + TypeScript-ESLint 默认规则，React 组件使用 `PascalCase`，hooks 保持 `useXxx` 命名；样式或主题配置集中放在 `frontend/src/styles/`。
- 推荐在保存前执行 `pnpm lint` 与 `pnpm test --run`，确保前端格式与断言同步通过。

## 测试指南
- 后端单元测试：`uv run pytest`；长耗时测试可加 `-k` 或 `-m slow` 控制范围，并关注缓存与数据库交互覆盖率不低于核心路径 80%。
- 前端测试：`pnpm test` 默认运行 Vitest + React Testing Library；交互场景可使用 `pnpm test:ui` 实时调试。
- 新增功能必须补充关键路径断言；涉及外部 API 时优先使用内置 fixtures 或本地 mock，避免真实调用。

## 提交与 Pull Request 指南
- Git 历史遵循 `type: summary` 风格，如 `feat: v3.0.3 - 动态导航栏与前端交互优化`；`type` 常见取值含 `feat`、`fix`、`chore`、`docs`。
- 提交前请确保通过所有 lint 与测试，并在 PR 描述中列出变更要点、测试结果、相关 Issue；UI 改动需附带截图或录屏。
- 若更改数据库或配置文件，请在 PR 中显式标注迁移步骤与回滚方案，方便审阅与发布。

## 安全与配置提示
- `.env` 内含 API Key 与数据库密码，请使用 `.env.example` 作为模板，避免直接提交敏感字段。
- 数据服务依赖 Redis 与 PostgreSQL，首次部署前执行 `backend/database_migrations/` 内的脚本或运行 `cd backend && uv run main` 自动迁移。
- 日志默认输出到控制台与 `logs/` 下特定文件，生成环境需结合 Dockerfile 与 `docker-compose.yml` 自定义挂载与留存策略。

## 后台任务与监控
- APScheduler 每 8 分钟触发一次数据持久化任务，配置 `coalesce=True`、`misfire_grace_time=300`、`max_instances=1`；调整间隔时务必评估对 Redis 待处理队列的影响。
- 任务日志会在结束时输出 UTC 计划时间（精确到秒）、耗时和处理摘要，可作为监控指标写入外部系统。
- 若需手动触发或排查，可在应用上下文中调用 `scheduled_persist_job()`，操作完成后请确保关闭临时会话。
