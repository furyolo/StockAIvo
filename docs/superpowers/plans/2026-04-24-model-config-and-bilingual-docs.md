# Model Config And Bilingual Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the default AI model configuration, make the Docker env example clearer for cross-platform host access, and switch the repository's main docs to English with a Chinese toggle.

**Architecture:** Keep runtime behavior simple: change only the service fallback default for `AI_DEFAULT_MODEL`, keep agent-specific overrides environment-driven, and synchronize examples/docs around that behavior. Preserve the existing Chinese docs by moving them to `*.zh-CN.md`, then add new English-first root docs with language switch links.

**Tech Stack:** Python, Pytest, Markdown, Docker Compose env files

---

### Task 1: Lock In Runtime Expectations With A Failing Test

**Files:**
- Create: `backend/tests/test_llm_model_config.py`
- Modify: `backend/stockaivo/ai/llm_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_llm_service_uses_new_default_and_agent_override_models(monkeypatch):
    monkeypatch.setenv("OPENAI_API_BASE", "http://example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("AI_TECHNICAL_ANALYSIS_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("AI_SYNTHESIS_MODEL", "gemini-3.1-pro-preview")

    service = LLMService()

    assert service.get_model_name_for_agent() == "gemini-3-flash-preview"
    assert service.get_model_name_for_agent("technical_analysis_agent") == "gemini-3.1-pro-preview"
    assert service.get_model_name_for_agent("synthesis_agent") == "gemini-3.1-pro-preview"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_llm_model_config.py -v`
Expected: FAIL because `LLMService` still falls back to `gemini-2.5-flash`

- [ ] **Step 3: Write minimal implementation**

```python
self.ai_default_model = os.getenv("AI_DEFAULT_MODEL", "gemini-3-flash-preview")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_llm_model_config.py -v`
Expected: PASS

### Task 2: Sync Env Templates And Docker Defaults

**Files:**
- Modify: `.env.example`
- Modify: `.env.docker`

- [ ] **Step 1: Update example env values**

```dotenv
AI_DEFAULT_MODEL="gemini-3-flash-preview"
AI_TECHNICAL_ANALYSIS_MODEL="gemini-3.1-pro-preview"
AI_SYNTHESIS_MODEL="gemini-3.1-pro-preview"
```

- [ ] **Step 2: Update Docker env defaults and host-access notes**

```dotenv
# Docker Compose maps host.docker.internal to the host gateway for Linux/Windows/macOS.
OPENAI_API_BASE="http://host.docker.internal:3222/v1"
AI_DEFAULT_MODEL="gemini-3-flash-preview"
AI_TECHNICAL_ANALYSIS_MODEL="gemini-3.1-pro-preview"
AI_SYNTHESIS_MODEL="gemini-3.1-pro-preview"
```

### Task 3: Flip Main Docs To English And Keep Chinese Toggle

**Files:**
- Move: `README.md` -> `README.zh-CN.md`
- Move: `STARTUP.md` -> `STARTUP.zh-CN.md`
- Create: `README.md`
- Create: `STARTUP.md`
- Modify: `README.zh-CN.md`
- Modify: `STARTUP.zh-CN.md`

- [ ] **Step 1: Preserve current Chinese docs under explicit locale filenames**

```text
README.md      -> README.zh-CN.md
STARTUP.md     -> STARTUP.zh-CN.md
```

- [ ] **Step 2: Add new English-first root docs with language switch links**

```md
[English](./README.md) | [简体中文](./README.zh-CN.md)
```

- [ ] **Step 3: Add matching language switch links to the Chinese docs**

```md
[English](./README.md) | [简体中文](./README.zh-CN.md)
```

### Task 4: Verify The Final State

**Files:**
- Verify: `backend/tests/test_llm_model_config.py`
- Verify: `backend/stockaivo/ai/llm_service.py`
- Verify: `.env.example`
- Verify: `.env.docker`
- Verify: `README.md`
- Verify: `README.zh-CN.md`
- Verify: `STARTUP.md`
- Verify: `STARTUP.zh-CN.md`

- [ ] **Step 1: Re-run the focused backend test**

Run: `cd backend && uv run pytest tests/test_llm_model_config.py -v`
Expected: PASS

- [ ] **Step 2: Sanity-check the changed files**

Run: `git diff -- backend/stockaivo/ai/llm_service.py backend/tests/test_llm_model_config.py .env.example .env.docker README.md README.zh-CN.md STARTUP.md STARTUP.zh-CN.md`
Expected: Only the intended model-config and bilingual-doc changes appear
