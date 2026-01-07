from datetime import timedelta
from typing import Dict

from temporalio import workflow


@workflow.defn
class ApplicationWorkflow:
    @workflow.run
    async def run(self, payload: Dict) -> Dict:
        analysis = await workflow.execute_activity(
            "evaluate_application",
            payload,
            schedule_to_close_timeout=timedelta(minutes=5),
        )
        email_result = None
        if analysis.get("qualifies"):
            email_payload = {
                "email": payload["email"],
                "subject": "Thanks for applying — you passed the initial screen",
                "body": (
                    "Hi,\n\n"
                    "Your application appears to meet our senior full-stack criteria. "
                    "We'll be in touch with next steps.\n\n"
                    f"Reason: {analysis.get('reason','')}\n"
                ),
            }
            email_result = await workflow.execute_activity(
                "send_applicant_email",
                email_payload,
                schedule_to_close_timeout=timedelta(minutes=2),
            )
        return {"analysis": analysis, "email": email_result}
