def run_workflow(input_data=None):
    return {"ok": True}

# Applied by AWO Sandbox Executor
PARALLEL_GROUPS = [['a1', 'a2']]

from concurrent.futures import ThreadPoolExecutor as _AWOThreadPoolExecutor

def run_parallel_group(tasks_map):
    """Execute independent agent callables concurrently and synchronize outputs."""
    with _AWOThreadPoolExecutor(max_workers=max(1, len(tasks_map))) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks_map.items()}
        return {name: fut.result() for name, fut in futures.items()}
