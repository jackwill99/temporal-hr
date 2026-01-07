from datetime import timedelta
from typing import Dict, List

from temporalio import workflow


@workflow.defn
class NotifyFailedWorkflow:
    @workflow.run
    async def run(self) -> Dict:
        to_notify_resp = await workflow.execute_activity(
            "fetch_unnotified_failed",
            {},
            schedule_to_close_timeout=timedelta(minutes=2),
        )
        rows: List[Dict] = to_notify_resp.get("rows", [])
        sent_ids: List[str] = []
        results: List[Dict] = []

        for row in rows:
            res = await workflow.execute_activity(
                "send_failed_email",
                {
                    "email": row.get("email"),
                    "reason": row.get("analysis", {}).get("reason", ""),
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            results.append(res)
            if res.get("sent"):
                if row.get("id"):
                    sent_ids.append(row["id"])

        if sent_ids:
            await workflow.execute_activity(
                "mark_failed_as_notified",
                {"ids": sent_ids},
                schedule_to_close_timeout=timedelta(minutes=1),
            )

        return {"notified": sent_ids, "attempts": len(rows), "results": results}

