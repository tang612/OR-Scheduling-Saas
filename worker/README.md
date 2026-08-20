# worker

异步求解任务层。M2 阶段填充：

- `tasks.py` — RQ job 定义（run_solve）
- `engines/` — SolverEngine 抽象 + CpsatEngine / AlnsEngine / RouterEngine / registry
- `progress.py` — 进度回调 → Redis pub/sub

M0 阶段占位。
