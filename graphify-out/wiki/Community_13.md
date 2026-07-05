# Community 13

> 29 nodes

## Key Concepts

- **ContextIsolator** (23 connections) — `runtime/workers/context_isolator.py`
- **ContextBudget** (18 connections) — `runtime/workers/context_isolator.py`
- **Any** (4 connections) — `runtime/workers/worker_pool.py`
- **IsolatedContext** (4 connections) — `runtime/workers/context_isolator.py`
- **ContextIsolator** (3 connections) — `runtime/workers/worker_pool.py`
- **Path** (3 connections) — `runtime/workers/worker_pool.py`
- **.create_context()** (3 connections) — `runtime/workers/context_isolator.py`
- **.__init__()** (3 connections) — `runtime/workers/worker_pool.py`
- **.estimate_tokens()** (2 connections) — `runtime/workers/context_isolator.py`
- **.get_budget_for_complexity()** (2 connections) — `runtime/workers/context_isolator.py`
- **.stats()** (2 connections) — `runtime/workers/worker_pool.py`
- **.to_dict()** (2 connections) — `runtime/workers/worker_pool.py`
- **.consume_input()** (1 connections) — `runtime/workers/context_isolator.py`
- **.consume_output()** (1 connections) — `runtime/workers/context_isolator.py`
- **.is_exhausted()** (1 connections) — `runtime/workers/context_isolator.py`
- **.remaining_input()** (1 connections) — `runtime/workers/context_isolator.py`
- **.remaining_output()** (1 connections) — `runtime/workers/context_isolator.py`
- **.reset()** (1 connections) — `runtime/workers/context_isolator.py`
- **.active_workers()** (1 connections) — `runtime/workers/context_isolator.py`
- **.destroy_context()** (1 connections) — `runtime/workers/context_isolator.py`
- **.get_model_for_task()** (1 connections) — `runtime/workers/context_isolator.py`
- **.global_usage_pct()** (1 connections) — `runtime/workers/context_isolator.py`
- **.__init__()** (1 connections) — `runtime/workers/context_isolator.py`
- **.is_within_global_budget()** (1 connections) — `runtime/workers/context_isolator.py`
- **.can_accept()** (1 connections) — `runtime/workers/context_isolator.py`
- *... and 4 more nodes in this community*

## Relationships

- [[Community 24]] (9 shared connections)
- [[Community 0]] (7 shared connections)
- [[Community 7]] (2 shared connections)
- [[Community 26]] (2 shared connections)

## Source Files

- `runtime/workers/context_isolator.py`
- `runtime/workers/worker_pool.py`

## Audit Trail

- EXTRACTED: 65 (76%)
- INFERRED: 21 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*