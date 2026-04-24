# English Doc Style Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the English `README.md` and `STARTUP.md` so they visually match the Chinese docs while preserving the already-corrected runtime facts.

**Architecture:** Use `README.zh-CN.md` and `STARTUP.zh-CN.md` as structural references, then rebuild the English docs section-by-section with the same visual rhythm, emoji markers, and major headings. Keep the latest model configuration, Docker host guidance, and Python 3.14 runtime notes from the current English docs.

**Tech Stack:** Markdown documentation

---

### Task 1: Rebuild The English README

**Files:**
- Modify: `README.md`
- Reference: `README.zh-CN.md`

- [ ] **Step 1: Align section structure and visual style**

```md
## ✨ Three Core Capabilities
## 🏗️ System Architecture
## 🛠️ Tech Stack
## 🚀 Quick Start
## 📚 API Reference
```

- [ ] **Step 2: Preserve corrected runtime facts**

```md
AI_DEFAULT_MODEL="gemini-3-flash-preview"
AI_TECHNICAL_ANALYSIS_MODEL="gemini-3.1-pro-preview"
AI_SYNTHESIS_MODEL="gemini-3.1-pro-preview"
Python 3.14+  •  Node.js 18+  •  PostgreSQL 17+  •  Redis 8+
```

### Task 2: Rebuild The English Startup Guide

**Files:**
- Modify: `STARTUP.md`
- Reference: `STARTUP.zh-CN.md`

- [ ] **Step 1: Mirror the Chinese visual hierarchy**

```md
## 🚀 Quick Start
## 🐳 Docker Deployment Notes
## 📋 Service Information
## 🔧 Environment Configuration
## 🛠️ Database Management
```

- [ ] **Step 2: Keep corrected Docker host guidance and model values**

```md
OPENAI_API_BASE=http://host.docker.internal:3222/v1
AI_DEFAULT_MODEL=gemini-3-flash-preview
AI_TECHNICAL_ANALYSIS_MODEL=gemini-3.1-pro-preview
AI_SYNTHESIS_MODEL=gemini-3.1-pro-preview
```

### Task 3: Verify The Result

**Files:**
- Verify: `README.md`
- Verify: `STARTUP.md`

- [ ] **Step 1: Spot-check heading and emoji coverage**

Run: `rg -n "^## |^### |✨|🚀|🐳|📚|📋|🔧|🛠️" README.md STARTUP.md`
Expected: English docs contain the same style markers and major sections as the Chinese docs
