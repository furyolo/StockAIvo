# System Patterns *Optional*

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-06-20 20:55:52 - Log of updates made.

*

## Coding Patterns

*   

## Architectural Patterns

*   

## Testing Patterns

*
* [2025-06-20 21:01:08] - ORM模型设计模式
  * 使用SQLAlchemy 2.0+的现代化语法和declarative_base
  * 主键设计：Stock使用ticker作为主键，价格表使用自增ID+复合唯一约束
  * 外键关系：所有价格表通过ticker字段关联到Stock表
  * 数据类型：价格使用Numeric(10,4)保证精度，交易量使用BigInteger
  * 索引策略：为常用查询字段（ticker、date、timestamp）创建索引
  * 关系映射：使用relationship和back_populates建立双向关系
---
### Architectural Patterns
[2025-06-21 21:54:19] - **Overall System Architecture: Modular & Service-Oriented**

**Rationale:**
The architecture is designed to be modular and service-oriented to ensure separation of concerns, scalability, and maintainability. Key components like data acquisition, AI analysis, and data persistence are isolated into distinct services, communicating through well-defined APIs.

**Implementation Details:**
- **API Gateway (FastAPI Router):** A single entry point that routes requests to the appropriate downstream service.
- **Data Service (`data_service.py`):** Implements a tiered data fetching strategy (DB -> Cache -> External API) to optimize for speed and cost.
- **AI Orchestrator (`orchestrator.py`):** Utilizes LangGraph to manage a complex, state-driven, parallel multi-agent workflow for deep analysis.
- **Asynchronous Persistence (`database_writer.py`):** A dedicated service for writing data from a temporary cache (Redis) to the main database (PostgreSQL), decoupled from the user-facing read path.
- **Clear Separation:** The `stockaivo/` directory clearly separates concerns: `ai/`, `routers/`, `data_provider.py`, `cache_manager.py`, `database_writer.py`.

---
### Architectural Patterns
[2025-06-20 21:40:48] - State-Driven Agentic Workflow

**Rationale:**
To manage the complexity of multi-step AI analysis and ensure resilience, a state-driven workflow is adopted. This pattern allows the system to track the progress of an analysis task, save intermediate results, and recover from failures. It separates the agent's logic from the state management, making the system more modular and robust.

**Implementation Details:**
- **State Representation (`state.py`):** A dedicated module to define the data structures that hold the state of the analysis, including inputs, intermediate findings from different agents, and final results.
- **Agent Tools (`tools.py`):** A collection of functions that agents can use to perform specific actions, such as fetching data or performing calculations. This promotes reusability and separates tools from the agents themselves.
- **Orchestrator (`orchestrator.py`):** The orchestrator is responsible for managing the state transitions. It calls agents in sequence, updates the state object with the results, and handles the overall flow of the analysis.
- **Persistence:** The state can be serialized and saved at each step, allowing for long-running, asynchronous analysis and recovery.