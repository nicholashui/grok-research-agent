# grok-research-agent

Python CLI that automates an 8-phase research workflow using Grok (xAI) via the OpenAI-compatible API.

## Install (editable)

```bash
python -m pip install -e .
```

## Configure

Create a `.env` in the project root:

```env
GROK_API_KEY=...
GROK_MODEL=grok-3
```

## Usage

```bash
grok-research-agent start --topic "What is Harness Engineering on AI?" --focus "definitions, key papers 2025-2026"
grok-research-agent resume --session-id harness-engineering-on-ai-20260326
grok-research-agent list-sessions
```

