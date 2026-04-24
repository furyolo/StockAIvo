# Docker Image Version Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh only the Docker images currently used by the project to the requested versions without adding a PostgreSQL service.

**Architecture:** Update image tags where they are actually consumed: Redis in `docker-compose.yml`, Python in the backend multi-stage Dockerfile, and Node in the frontend build stage. Keep `nginx:stable-alpine` unchanged because it already matches the requested target, and synchronize the main docs so the published runtime description matches the container base images.

**Tech Stack:** Docker Compose, Alpine-based Dockerfiles, Markdown docs

---

### Task 1: Update Compose And Dockerfile Image Tags

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`

- [ ] **Step 1: Refresh the Redis image tag**

```yaml
services:
  redis:
    image: redis:8.6.1-alpine
```

- [ ] **Step 2: Refresh the backend Python base images**

```dockerfile
FROM python:3.14.3-alpine AS builder
...
UV_PYTHON=python3.14.3
...
FROM python:3.14.3-alpine AS runtime
```

- [ ] **Step 3: Refresh the frontend Node build image**

```dockerfile
FROM node:25.7.0-alpine AS frontend-builder
FROM nginx:stable-alpine AS frontend-production
```

### Task 2: Sync User-Facing Version Notes

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Update the backend runtime version text**

```md
- Backend: FastAPI, Python 3.14, SQLAlchemy, LangGraph
```

- [ ] **Step 2: Update the Chinese technical stack and requirements lines**

```md
| **后端**   | Python + FastAPI + SQLAlchemy  | 3.14 + 0.115.13 + 2.0.41 | 高性能异步API |
Python 3.14+  •  Node.js 18+  •  PostgreSQL 17+  •  Redis 8+
```

### Task 3: Verify Container Configuration

**Files:**
- Verify: `docker-compose.yml`
- Verify: `backend/Dockerfile`
- Verify: `frontend/Dockerfile`
- Verify: `README.md`
- Verify: `README.zh-CN.md`

- [ ] **Step 1: Validate compose rendering**

Run: `docker compose config`
Expected: configuration renders successfully with `redis:8.6.1-alpine`

- [ ] **Step 2: Spot-check the target tags**

Run: `rg -n "redis:8.6.1-alpine|python:3.14.3-alpine|python3.14.3|node:25.7.0-alpine|nginx:stable-alpine|Python 3.14" docker-compose.yml backend/Dockerfile frontend/Dockerfile README.md README.zh-CN.md`
Expected: all requested versions appear in the intended files, with no new PostgreSQL service added
