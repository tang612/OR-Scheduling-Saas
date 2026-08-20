"""RQ worker 启动 wrapper：显式控制 sys.path，确保 import worker/app 正确。

RQ console script 的 --path 默认 '.'（相对路径）在 fork 子进程里解析不可靠，
故用本脚本显式 insert 项目根 + backend 到 sys.path 最前面后调用 rq main。
用法：python3 worker/run_worker.py worker quick alns300 alns900
"""
import os
import sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)
sys.path.insert(0, os.path.join(PROJ, "backend"))

from rq.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
