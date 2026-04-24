[English](./STARTUP.md) | [简体中文](./STARTUP.zh-CN.md)

# StockAIvo Startup Guide

## 🚀 Quick Start

### Development Environment

#### Windows
```bash
# Start the local development environment
./start-dev.bat
```

#### Linux / macOS
```bash
# Start the local development environment
./start-dev.sh

# Show service status
./start-dev.sh status

# Stop all services
./start-dev.sh stop

# View logs
./start-dev.sh logs
```

> 💡 Note: the FastAPI backend code and dependencies now live under `backend/`.
> If you want to run `uv ...` or `python database_migrations/...` manually,
> switch into that directory first.

### Production Environment

#### Cross-Platform (Recommended)
```bash
# Start the production environment
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Restart services
docker-compose restart

# Remove persisted containers and volumes (use with caution)
docker-compose down -v
```

## 🐳 Docker Deployment Notes

### Development Workflow (Local Script - Recommended)
```bash
# Windows
./start-dev.bat

# Linux / macOS
./start-dev.sh
```

### Production Workflow (Docker - Recommended)
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Remove persisted volumes (use with caution)
docker-compose down -v
```

### Why This Architecture?

- **Development environment**: local scripts provide fast hot reload and easier iteration
- **Production environment**: Docker provides consistency, portability, and production-grade deployment behavior

## 📋 Service Information

### Development
- **Frontend**: http://localhost:3223
- **Backend API**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health

### Production
- **Frontend**: http://localhost:3223
- **Backend API**: http://127.0.0.1:3224
- **API Docs**: http://127.0.0.1:3224/docs
- **Health Check**: http://127.0.0.1:3224/health

## 🔧 Environment Configuration

### Required Environment Variables
```bash
# Database connection
DATABASE_URL=postgresql://user:password@localhost/dbname

# Redis connection
REDIS_URL=redis://localhost:6379/0

# AI service configuration
OPENAI_API_BASE=http://host.docker.internal:3222/v1
OPENAI_API_KEY=your_ai_api_key
```

### Optional Environment Variables
```bash
# AI model configuration
AI_DEFAULT_MODEL=gemini-3-flash-preview
AI_TECHNICAL_ANALYSIS_MODEL=gemini-3.1-pro-preview
AI_SYNTHESIS_MODEL=gemini-3.1-pro-preview

# Service configuration
API_BASE_URL=http://127.0.0.1:3224
FRONTEND_URL=http://localhost:3223
```

### Docker Host Access

- **Host mapping**: `docker-compose.yml` maps `host.docker.internal` to `host-gateway`
- **Supported environments**: Windows, macOS, and modern Linux Docker engines
- **Fallback option**: if your Docker engine does not support `host-gateway`, replace `OPENAI_API_BASE` with a reachable host IP

## 🛠️ Database Management

### Initialize The Database
```bash
# Start the application and let SQLAlchemy create the schema
cd backend && uv run dev

# Docker environment initialization (includes automatic migration)
docker-compose up -d
```

### Automatic Database Migration
**Docker and production environments automatically run performance-oriented migrations**

- ✅ **Search index creation**: creates GIN and B-tree indexes for `us_stocks_name`
- ✅ **`stock_symbols` index creation**: adds an index on the `symbol` field
- ❌ **No legacy table cleanup**: deprecated tables such as `stock_prices_minute` and `stock_prices_hourly` are not dropped automatically

**Migration control variables**
```bash
# Enable automatic migration (default)
RUN_DATABASE_MIGRATIONS=true

# Disable automatic migration
RUN_DATABASE_MIGRATIONS=false
```

### Manual Data Migration
If you need to run migrations manually or clean up legacy tables:

```bash
# Create search indexes
cd backend && python database_migrations/create_search_indexes.py

# Create stock_symbols index
cd backend && python database_migrations/create_stock_symbols_index.py

# Drop deprecated tables only when needed
cd backend && python database_migrations/drop_minute_table.py
cd backend && python database_migrations/drop_hourly_table.py

# Read the full migration guide
cd backend && cat database_migrations/MIGRATIONS.md
```

### Health Checks
```bash
# Check backend health
curl http://127.0.0.1:8000/health

# Check cache statistics
curl http://127.0.0.1:8000/cache-stats
```

## 📊 Monitoring And Logs

### Log Locations
- **Frontend logs**: `logs/frontend/`
- **Backend logs**: `logs/backend/`
- **Nginx logs**: `logs/nginx/`

### Real-Time Monitoring
```bash
# View frontend logs
tail -f logs/frontend/production.log

# View backend logs
tail -f logs/backend/production.log

# Docker logs
docker-compose logs -f backend
docker-compose logs -f frontend
```

### System Status
```bash
# Cache statistics
curl http://127.0.0.1:3224/cache-stats

# Database connectivity test
python -c "import sqlalchemy; print('Database OK')"
```

## 🔄 Development Workflow

### Daily Development
1. **Start the development environment**: `./start-dev.sh` or `./start-dev.bat`
2. **Modify code**: hot reload is enabled
3. **Run tests**: `uv run pytest tests/ -v`
4. **Run type checks**: `uv run mypy stockaivo/`
5. **Stop services**: close the terminal window or use the stop command

### Deployment Flow
1. **Pull the latest code**: `git pull origin main`
2. **Refresh dependencies**
   - Backend: `uv sync`
   - Frontend: `pnpm install`
3. **Build the application**: `pnpm build`
4. **Start production services**: `docker-compose up -d`
5. **Verify health endpoints**: `curl http://127.0.0.1:3224/health`

## 🚨 Troubleshooting

### Common Problems

#### Port Conflict
```bash
# Check port usage
netstat -tulpn | grep :3223
netstat -tulpn | grep :3224
netstat -tulpn | grep :8000

# Update the relevant port config in your environment files
```

#### Database Connection Failure
```bash
# Check database service
systemctl status postgresql

# Test connectivity
psql -h localhost -U username -d dbname

# Review logs
tail -f /var/log/postgresql/postgresql-*.log
```

#### Redis Connection Failure
```bash
# Check Redis service
systemctl status redis

# Test connectivity
redis-cli ping

# Review logs
tail -f /var/log/redis/redis-server.log
```

#### Dependency Issues
```bash
# Rebuild backend environment
rm -rf .venv
uv venv
uv sync --extra dev

# Reinstall frontend dependencies
rm -rf frontend/node_modules
cd frontend && pnpm install
```

### Performance Optimization

#### Cache Optimization
```bash
# Clear Redis cache
redis-cli FLUSHDB

# View Redis memory statistics
redis-cli INFO memory
```

#### Database Optimization
```bash
# Example placeholder for DB tuning helpers
python -c "
from stockaivo.models import *
# Add your index-tuning logic here
"
```

## 📞 Support

If you run into problems:
1. Check logs for the detailed error context
2. Run health checks to narrow down the failing layer
3. Verify environment variable values
4. Review the project docs and `CLAUDE.md`

---

**Tip**: use the local startup scripts during development and Docker for
production-style deployment to get the best balance of productivity and
stability.

---

## 📝 Update Log

### v3.0.5 (2025-09-22)
- automatic database migration flow for Docker and production
- new `stockaivo/migration_manager.py` module
- automatic search index creation during startup
- `RUN_DATABASE_MIGRATIONS` environment variable added
- improved out-of-the-box database initialization

### v3.0.4 (2025-09-22)
- removed redundant `start-prod.bat` and `start-prod.sh`
- standardized production startup around `docker-compose.yml`
- removed unnecessary development-only compose and Dockerfile variants
- simplified the deployment surface for easier maintenance
