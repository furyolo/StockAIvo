# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-06-20 20:55:22 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Goal

*   **[2025-06-21 21:54:43]** 构建一个面向美股的智能数据与分析后端服务，提供稳定、高效的数据接口，并通过一个多 Agent 协同的 AI 系统，提供深度的投资决策辅助。

## Key Features

*   **[2025-06-21 21:54:43]** **智能数据管道:** 实现一个高效的数据获取、缓存（Redis）和持久化（PostgreSQL）流程，优化数据访问效率。
*   **[2025-06-21 21:54:43]** **RESTful 数据 API:** 提供稳定、多时间粒度（日、周、小时）的股票数据查询接口。
*   **[2025-06-21 21:54:43]** **AI 投资决策辅助系统:** 构建一个由 LangGraph 驱动的多 Agent（包括多空研究、辩论、综合分析等角色）协同工作流，提供全面的市场解读和投资建议。

## Overall Architecture

*   **[2025-06-21 21:54:43]** 系统采用模块化、服务导向的架构，主要包括 API 层 (FastAPI), 核心逻辑层 (Data Service, AI Orchestrator), 和数据存储层 (PostgreSQL, Redis)。