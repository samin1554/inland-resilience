# ADR-007: LLM provider for the agent

## Status
**Open.** Decision for the lead.

## Context
The spec uses LangGraph (§5, §14) but doesn't name a model provider. The LLM is an external dependency of the worker: it needs an allowlist entry, key management, timeouts, cost limits and a place in the trace.

## Options
| Option | Pros | Cons |
|---|---|---|
| Anthropic Claude (e.g. Sonnet 5 for planning/explaining, Haiku 4.5 for cheap classification) | Strong tool use and instruction following; LangChain/LangGraph integration exists | Paid API; needs budget limits |
| OpenAI | Mature LangGraph support | Paid API |
| Groq-hosted open models | Very fast, cheap | Weaker tool-use reliability; model churn |
| Self-hosted open model | No per-call cost, data stays local | GPU ops burden; weaker quality |

## Requirements whichever is chosen
- The model only plans and explains; it never calculates (§14). Tool calls are restricted to the approved list.
- Provider text reaching the model (alerts, descriptions) is treated as untrusted data (prompt-injection tests, §21).
- A model interface in `inland_worker/agent/llm.py` so the provider can change without touching the graph.
- Per-job token and cost ceiling; model name and version recorded in the trace.

## Decision
TBD.
