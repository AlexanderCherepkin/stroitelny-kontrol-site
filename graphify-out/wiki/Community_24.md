# Community 24

> 25 nodes

## Key Concepts

- **WorkerPool** (29 connections) — `runtime/workers/worker_pool.py`
- **WorkerResult** (16 connections) — `runtime/workers/worker_pool.py`
- **WorkerJob** (15 connections) — `runtime/workers/worker_pool.py`
- **._dispatcher_loop()** (6 connections) — `runtime/workers/worker_pool.py`
- **._execute_in_worker()** (6 connections) — `runtime/workers/worker_pool.py`
- **.dispatch()** (5 connections) — `runtime/workers/worker_pool.py`
- **._estimate_saved_tokens()** (4 connections) — `runtime/workers/worker_pool.py`
- **._spawn_worker()** (3 connections) — `runtime/workers/worker_pool.py`
- **._store_result()** (3 connections) — `runtime/workers/worker_pool.py`
- **.test_priority_sorting()** (2 connections) — `runtime/test_resilience.py`
- **._find_free_worker()** (2 connections) — `runtime/workers/worker_pool.py`
- **.start()** (2 connections) — `runtime/workers/worker_pool.py`
- **Dispatch a job to a worker. Returns summary when done.          Backpressure: if** (1 connections) — `runtime/workers/worker_pool.py`
- **Main loop: pick jobs from queue, assign to free workers or spawn new ones.** (1 connections) — `runtime/workers/worker_pool.py`
- **Run a job in a specific worker process.** (1 connections) — `runtime/workers/worker_pool.py`
- **A job dispatched to an isolated worker.** (1 connections) — `runtime/workers/worker_pool.py`
- **Spawn a new worker slot.** (1 connections) — `runtime/workers/worker_pool.py`
- **Estimate how many tokens were kept OUT of the parent context.** (1 connections) — `runtime/workers/worker_pool.py`
- **Summary returned by worker — parent sees ONLY this, not raw data.** (1 connections) — `runtime/workers/worker_pool.py`
- **Pool of isolated worker processes for agent execution.      Each worker runs in** (1 connections) — `runtime/workers/worker_pool.py`
- **.__lt__()** (1 connections) — `runtime/workers/worker_pool.py`
- **.busy_workers()** (1 connections) — `runtime/workers/worker_pool.py`
- **.idle_workers()** (1 connections) — `runtime/workers/worker_pool.py`
- **.stop()** (1 connections) — `runtime/workers/worker_pool.py`
- **.is_success()** (1 connections) — `runtime/workers/worker_pool.py`

## Relationships

- [[Community 19]] (14 shared connections)
- [[Community 13]] (9 shared connections)
- [[Community 0]] (6 shared connections)
- [[Community 7]] (5 shared connections)
- [[Community 4]] (1 shared connections)
- [[Community 30]] (1 shared connections)
- [[Community 26]] (1 shared connections)
- [[Community 45]] (1 shared connections)

## Source Files

- `runtime/test_resilience.py`
- `runtime/workers/worker_pool.py`

## Audit Trail

- EXTRACTED: 84 (79%)
- INFERRED: 22 (21%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*