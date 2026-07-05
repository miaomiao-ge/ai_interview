import argparse
import threading

from core.config import TASK_POLL_INTERVAL_SECONDS, WORKER_CONCURRENCY
from core.database import init_db
from core.interview_job_service import process_pending_jobs, run_worker_forever


def run_worker_threads(worker_count: int, poll_interval_seconds: float) -> None:
    threads = []
    for index in range(max(1, worker_count)):
        thread = threading.Thread(
            target=run_worker_forever,
            args=(poll_interval_seconds,),
            name=f"interview-worker-{index + 1}",
            daemon=False,
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run interview background workers.")
    parser.add_argument("--workers", type=int, default=WORKER_CONCURRENCY, help="Worker threads in this process.")
    parser.add_argument("--poll-interval", type=float, default=TASK_POLL_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true", help="Process a bounded number of jobs and exit.")
    parser.add_argument("--max-jobs", type=int, default=1, help="Maximum jobs for --once mode.")
    args = parser.parse_args()

    init_db()
    if args.once:
        result = process_pending_jobs(max_jobs=args.max_jobs, poll_interval_seconds=args.poll_interval)
        print(result, flush=True)
        return
    run_worker_threads(args.workers, args.poll_interval)


if __name__ == "__main__":
    main()
