# GitHubIQ

GitHubIQ is an interactive project tutor that helps developers understand unfamiliar Git repositories. It turns repository analysis into a guided learning experience with architecture maps, data-flow walkthroughs, schema explanations, and hands-on sandbox exercises.

![GitHubIQ - Your Project Tutor](Idea/screenshots/00-cover.png)

## Overview

Understanding an existing codebase often requires reading outdated documentation, tracing requests across many files, and asking experienced teammates for help. GitHubIQ is designed to make that process clearer and more practical.

Users provide a Git repository and answer a short set of questions about their role, experience, and learning goals. The system analyzes the repository and organizes the results into a personalized guide based on the actual project.

## Features

- Guided tours of important application flows
- Architecture views showing how components interact
- Data-flow explanations showing how values change across a request
- Database schema and relationship explanations
- Language and framework concepts explained in context
- A safe sandbox for experimenting with core project flows
- Personalized learning content based on the user's goals
- Exportable learning material without vendor lock-in

## How It Works

1. Connect a public or private Git repository.
2. Provide your role, experience level, goals, and preferred learning depth.
3. Analyze the repository structure, architecture, schema, data flows, and coding patterns.
4. Combine the analysis into a project-specific learning guide.
5. Explore the guide through visual explanations, walkthroughs, and exercises.

## Analysis Pipeline

GitHubIQ uses a set of specialized analysis roles:

| Role | Responsibility |
| --- | --- |
| Explorer | Maps repository structure, entry points, and module boundaries. |
| Architect | Identifies services, layers, and relationships between components. |
| Schema Analyst | Finds database models and explains their relationships. |
| Data-Flow Analyst | Traces requests and explains how data changes. |
| Tutor | Explains unfamiliar languages, frameworks, and coding patterns. |
| Sandbox Builder | Creates safe exercises based on important project flows. |

The analysis results are combined by an orchestrator before the learning guide is generated.

![GitHubIQ system architecture](Idea/screenshots/09-system-architecture.png)

## MVP Implementation

This repository contains a working MVP that analyses **public** GitHub repositories
end to end.

- **Backend** — Python / FastAPI with a **LangGraph** multi-agent pipeline. Six
  specialist agents (Explorer, Architect, Schema, Data-Flow, Tutor, Sandbox) run
  with real fan-out/fan-in orchestration, and an orchestrator composes the guide.
- **Frontend** — React + Vite + TypeScript, with a GitHub **dark/light** theme
  switcher. Views: guided lessons, live architecture map, data-flow walkthrough,
  reverse-engineered schema, and a runnable in-browser sandbox.
- **LLM** — Azure OpenAI (provisioned via Azure AI Foundry). Agents degrade
  gracefully to heuristics when no LLM is configured, so the app always runs.
- **Database** — Azure Cosmos DB (serverless) stores the semi-structured guide
  documents; an in-memory store is used automatically for local dev.
- **Containers** — `Dockerfile` for each service plus `docker-compose.yml`.
- **Cloud** — `infra/main.bicep` + `azure.yaml` deploy Azure Container Apps,
  Azure OpenAI, Cosmos DB and Log Analytics.

### Project layout

```
backend/    FastAPI app + LangGraph agents (app/agents/*)
frontend/   Vite + React + TS single-page app
infra/      main.bicep (Container Apps, Azure OpenAI, Cosmos)
azure.yaml  azd service definitions
docker-compose.yml
```

### Run locally with Docker

```bash
cp .env.example .env       # optional: add Azure OpenAI + Cosmos creds
docker compose up --build
# frontend → http://localhost:8080 , backend → http://localhost:8000/docs
```

Without credentials the backend runs in heuristic mode (no LLM, in-memory store).
Add `AZURE_OPENAI_*` and `COSMOS_*` to `.env` for full LLM-powered, persisted output.

### Run locally without Docker

```bash
# Backend (Python 3.12)
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api → :8000)
```

### Deploy to Azure

```bash
azd up             # provisions Container Apps + Azure OpenAI + Cosmos and deploys
```

Or provision with Bicep directly:

```bash
az group create -n rg-githubiq -l eastus2
az deployment group create -g rg-githubiq -f infra/main.bicep
```

## Screenshots


### Repository Connection

![Repository connection](Idea/screenshots/01-hero.png)

### Repository Analysis

![Repository analysis](Idea/screenshots/02-analysis.png)

### Learning Preferences

![Learning preferences](Idea/screenshots/03-questionnaire.png)

### Interactive Guide

![Interactive guide](Idea/screenshots/04-guide.png)

### Architecture Map

![Architecture map](Idea/screenshots/05-architecture.png)

### Data-Flow Walkthrough

![Data-flow walkthrough](Idea/screenshots/06-dataflow.png)

### Database Schema

![Database schema](Idea/screenshots/07-schema.png)

### Sandbox

![Sandbox](Idea/screenshots/08-sandbox.png)

### Problem and Solution

![Problem and solution](Idea/screenshots/10-problem-solution.png)