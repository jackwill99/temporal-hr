import asyncio
from datetime import timedelta

from temporalio.client import (Client, Schedule, ScheduleActionStartWorkflow,
                               ScheduleSpec)

from .config import TEMPORAL_TARGET, TEMPORAL_TASK_QUEUE
from .notification_workflow import NotifyFailedWorkflow


async def create_schedule() -> None:
    client = await Client.connect(TEMPORAL_TARGET)

    spec = ScheduleSpec(
        cron_expressions=["*/1 * * * *"],  
    )
    action = ScheduleActionStartWorkflow(
        workflow=NotifyFailedWorkflow,
        args=[],
        id="notify-failed-workflow",
        task_queue=TEMPORAL_TASK_QUEUE,
        execution_timeout=timedelta(minutes=5),
    )
    sch = Schedule(spec=spec, action=action)
    try:
        await client.create_schedule("notify-failed-schedule", sch)
        print("Created schedule 'notify-failed-schedule' (every minute).")
    except Exception as exc:  # noqa: BLE001 - best effort
        print(f"Could not create schedule (maybe already exists): {exc}")


if __name__ == "__main__":
    asyncio.run(create_schedule())
