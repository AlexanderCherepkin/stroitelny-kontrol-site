# Community 15

> 28 nodes

## Key Concepts

- **LLMEngine** (41 connections) — `runtime/engine/llm_engine.py`
- **LLMResponse** (26 connections) — `runtime/engine/llm_engine.py`
- **AgentSpec** (12 connections) — `runtime/contracts/agent_spec.py`
- **llm_engine.py** (10 connections) — `runtime/engine/llm_engine.py`
- **MockLLMEngine** (9 connections) — `runtime/engine/llm_engine.py`
- **._call_api()** (7 connections) — `runtime/engine/llm_engine.py`
- **.execute()** (6 connections) — `runtime/engine/llm_engine.py`
- **.__init__()** (6 connections) — `runtime/engine/llm_engine.py`
- **test_mock_llm_engine_returns_parsed_json()** (5 connections) — `tests/integration/test_e2e.py`
- **Any** (5 connections) — `runtime/engine/llm_engine.py`
- **._build_fallback_chain()** (4 connections) — `runtime/engine/llm_engine.py`
- **._execute_with_retries()** (4 connections) — `runtime/engine/llm_engine.py`
- **.execute()** (4 connections) — `runtime/engine/llm_engine.py`
- **AgentSpec** (4 connections) — `runtime/engine/llm_engine.py`
- **._call_anthropic()** (3 connections) — `runtime/engine/llm_engine.py`
- **._call_openai()** (3 connections) — `runtime/engine/llm_engine.py`
- **._extract_json()** (3 connections) — `runtime/engine/llm_engine.py`
- **.raw_chat_completion()** (3 connections) — `runtime/engine/llm_engine.py`
- **.to_input_message()** (2 connections) — `runtime/contracts/agent_spec.py`
- **._resolve_api_key()** (2 connections) — `runtime/engine/llm_engine.py`
- **.to_system_prompt()** (1 connections) — `runtime/contracts/agent_spec.py`
- **.raw_chat_completion()** (1 connections) — `runtime/engine/llm_engine.py`
- **LLM execution engine with circuit breaker and provider fallback.      Fallback c** (1 connections) — `runtime/engine/llm_engine.py`
- **Build ordered list of fallback providers based on available API keys.** (1 connections) — `runtime/engine/llm_engine.py`
- **Direct API call without AgentSpec wrapping. Returns raw text.** (1 connections) — `runtime/engine/llm_engine.py`
- *... and 3 more nodes in this community*

## Relationships

- [[Community 7]] (33 shared connections)
- [[Community 19]] (14 shared connections)
- [[Community 4]] (8 shared connections)
- [[Community 0]] (3 shared connections)
- [[Community 66]] (3 shared connections)
- [[Community 69]] (2 shared connections)
- [[Community 129]] (2 shared connections)
- [[Community 9]] (2 shared connections)
- [[Community 1]] (2 shared connections)

## Source Files

- `runtime/contracts/agent_spec.py`
- `runtime/engine/llm_engine.py`
- `tests/integration/test_e2e.py`

## Audit Trail

- EXTRACTED: 121 (72%)
- INFERRED: 46 (28%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*