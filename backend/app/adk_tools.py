import json
import re
from typing import Any, Dict, List, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .config import GEMINI_MODEL

KEYWORDS = ["react", "node"]


def _adk_model_name() -> str:
    if GEMINI_MODEL.startswith("models/"):
        return GEMINI_MODEL.split("models/", 1)[1]
    return GEMINI_MODEL



async def run_agent_once(
    *,
    agent: Any,
    app_name: str,
    user_id: str,
    session_id: str,
    message_text: str,
) -> str:
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    content = types.Content(role="user", parts=[types.Part(text=message_text)])

    final_text: Optional[str] = None
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            text_parts = [part.text for part in event.content.parts if getattr(part, "text", None)]
            if text_parts:
                final_text = "\n".join(text_parts).strip()

    if final_text is None:
        raise RuntimeError("ADK agent produced no final response text")
    return final_text


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    return cleaned


def must_json(text: str) -> dict:
    try:
        cleaned = _clean_json_text(text)
        return json.loads(cleaned)
    except Exception as exc:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        raise ValueError(f"Agent did not return valid JSON. Raw output:\n{text}\n\nError: {exc}")




def tool_extract_resume_text(pdf_path: str) -> Dict[str, Any]:
   
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return {"status": "success", "text": "\n".join(pages)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}




class CandidateProfileSchema(BaseModel):
    name: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    years_experience: Optional[float] = Field(default=None)
    skills: List[str] = Field(default_factory=list)
    employment_summary: str = Field(default="")
    education_summary: str = Field(default="")
    red_flags: List[str] = Field(default_factory=list)
    raw_resume_excerpt: str = Field(default="")


class EvaluationResultSchema(BaseModel):
    score_0_to_100: int = Field(ge=0, le=100)
    decision: str = Field(description="strong_reject | reject | borderline | interview | strong_hire")
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    interview_questions: List[str] = Field(default_factory=list)
    suggested_next_step: str = Field(default="")




def build_intake_agent() -> LlmAgent:
    return LlmAgent(
        name="intake_agent",
        model=_adk_model_name(),
        description="Parses applicant form, resume and extracts structured candidate profile.",
        # Generated instructions
        instruction=f"""
You are IntakeAgent for hiring.

You will receive JSON with fields:
- application_id
- email
- title
- description
- resume_path

MUST DO:
1) Call the tool `tool_extract_resume_text` with the resume_path to get resume text.
2) Extract a candidate profile for a Full Stack Developer application.
3) Return ONLY valid JSON matching this schema:
{json.dumps(CandidateProfileSchema.model_json_schema(), indent=2)}

Rules:
- If a field is unknown, use null (not empty string) for optional fields.
- skills should be normalized (e.g., "Node.js" not "node").
- Include up to ~1200 chars in raw_resume_excerpt (a helpful excerpt).
""".strip(),
        tools=[tool_extract_resume_text],
        output_key="candidate_profile_json",
    )


def build_evaluator_agent() -> LlmAgent:
    return LlmAgent(
        name="evaluator_agent",
        model=_adk_model_name(),
        description="Evaluates candidate fit for the role and produces a hiring recommendation.",
        # Generated instructions
        instruction=f"""
You are EvaluatorAgent for hiring.

You will receive JSON with:
- title
- description
- candidate_profile (object)

Evaluate for a Full Stack Developer role and produce:
- score_0_to_100
- decision: strong_reject | reject | borderline | interview | strong_hire
- strengths, concerns (bullet-like strings)
- 5-8 interview_questions tailored to the candidate + role
- suggested_next_step (concise)

Return ONLY valid JSON matching this schema:
{json.dumps(EvaluationResultSchema.model_json_schema(), indent=2)}
""".strip(),
        output_schema=EvaluationResultSchema,
        output_key="evaluation_result_json",
    )


async def run_adk_pipeline(
    *,
    application_id: str,
    email: str,
    title: str,
    description: str,
    resume_path: Optional[str],
) -> Dict[str, Any]:
    intake_agent = build_intake_agent()
    evaluator_agent = build_evaluator_agent()

    intake_prompt = json.dumps(
        {
            "application_id": application_id,
            "email": email,
            "title": title,
            "description": description,
            "resume_path": resume_path or "",
        }
    )
    intake_text = await run_agent_once(
        agent=intake_agent,
        app_name="application-screening",
        user_id=email,
        session_id=f"{application_id}-intake",
        message_text=intake_prompt,
    )
    candidate_profile = must_json(intake_text)

    evaluator_prompt = json.dumps(
        {
            "title": title,
            "description": description,
            "candidate_profile": candidate_profile,
        }
    )
    eval_text = await run_agent_once(
        agent=evaluator_agent,
        app_name="application-screening",
        user_id=email,
        session_id=f"{application_id}-eval",
        message_text=evaluator_prompt,
    )
    evaluation = must_json(eval_text)

    lowered = (description + " " + json.dumps(candidate_profile)).lower()
    missing_keywords = [kw for kw in KEYWORDS if kw not in lowered]
    decision = evaluation.get("decision", "").lower()
    qualifies = decision in {"interview", "strong_hire"}

    return {
        "used_gemini": True,
        "qualifies": qualifies,
        "reason": evaluation.get("suggested_next_step") or evaluation.get("decision") or "",
        "missing_keywords": missing_keywords,
        "candidate_profile": candidate_profile,
        "evaluation": evaluation,
    }
