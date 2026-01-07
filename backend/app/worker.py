import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    evaluate_application,
    fetch_unnotified_failed,
    mark_failed_as_notified,
    send_applicant_email,
    send_failed_email,
)
from .config import TEMPORAL_TARGET, TEMPORAL_TASK_QUEUE
from .notification_workflow import NotifyFailedWorkflow
from .workflows import ApplicationWorkflow


async def main() -> None:
    client = await Client.connect(TEMPORAL_TARGET)
    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[ApplicationWorkflow, NotifyFailedWorkflow],
        activities=[
            evaluate_application,
            send_applicant_email,
            send_failed_email,
            fetch_unnotified_failed,
            mark_failed_as_notified,
        ],
    )
    print(f"Worker listening on task queue '{TEMPORAL_TASK_QUEUE}' against {TEMPORAL_TARGET}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
