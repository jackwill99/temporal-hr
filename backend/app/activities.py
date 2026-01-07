from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from temporalio import activity

from .adk_client import analyze_application
from .emailer import send_notification_email
from .storage import (append_application_record, append_failed_record,
                      get_unnotified_failed, mark_failed_notified)


@activity.defn
async def evaluate_application(payload: Dict) -> Dict:
    file_path_raw: Optional[str] = payload.get("file_path")
    file_path = Path(file_path_raw) if file_path_raw else None
    analysis = await analyze_application(
        email=payload["email"],
        title=payload["title"],
        description=payload["description"],
        file_path=file_path,
    )

    if analysis.get("qualifies"):
        append_application_record(
            {
                "email": payload["email"],
                "title": payload["title"],
                "description": payload["description"],
                "file_path": str(file_path) if file_path else "",
                "evaluated_at": datetime.utcnow().isoformat() + "Z",
                "analysis": analysis,
            }
        )

    else:
        append_failed_record(
            {
                "id": uuid4().hex,
                "email": payload["email"],
                "title": payload["title"],
                "description": payload["description"],
                "file_path": str(file_path) if file_path else "",
                "evaluated_at": datetime.utcnow().isoformat() + "Z",
                "analysis": analysis,
                "notified_at": None,
            }
        )

    return analysis


@activity.defn
async def send_applicant_email(payload: Dict) -> Dict:
   
    error = send_notification_email(
        to_email=payload["email"],
        subject=payload.get("subject", "Thanks for applying — you passed the initial screen"),
        body=payload.get(
            "body",
            (
                "Hi,\n\n"
                "Your application appears to meet our senior full-stack criteria. "
                "We'll be in touch with next steps.\n\n"
            ),
        ),
    )
    return {"sent": error is None, "error": error}


@activity.defn
async def send_failed_email(payload: Dict) -> Dict:
    
    reason = payload.get("reason", "")
    body = payload.get(
        "body",
        (
            "Hi,\n\n"
            "Thank you for applying. For this role we’re prioritizing senior full-stack profiles "
            "that explicitly mention React, Node.js. "
            f"Reason: {reason}\n\n"
            "We appreciate your interest and encourage you to reapply when it’s a closer fit.\n"
        ),
    )
    error = send_notification_email(
        to_email=payload["email"],
        subject=payload.get("subject", "Thanks for applying — quick update"),
        body=body,
    )
    return {"sent": error is None, "error": error}


@activity.defn
async def fetch_unnotified_failed(_: Optional[Dict] = None) -> Dict:
    
    rows = get_unnotified_failed()
    return {"rows": rows}


@activity.defn
async def mark_failed_as_notified(payload: Dict) -> Dict:
    
    ids = payload.get("ids", [])
    mark_failed_notified(ids)
    return {"updated": len(ids)}
