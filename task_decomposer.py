"""ThumbTack Task Decomposer — Automatic task breakdown via local LLM.

Uses Ollama native `/api/generate` endpoint (more reliable than
`/v1/chat/completions` for some models).
"""
import json
import urllib.request
import urllib.error
import asyncio
from typing import List, Dict, Any, Optional

from database import add_agent_log, get_task, get_project

# ── Config ───────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "kimi-k2.6:cloud"
TEMPERATURE = 0.3
TIMEOUT = 300.0

# System prompt for the planner agent
PLANNER_SYSTEM_PROMPT = """You are a senior software architect and project planner.
Your job is to take a large development task and break it into small, specific, actionable subtasks.

RULES:
- Each subtask must be completable by a single agent in one session (15-60 min).
- Be specific: include file names, function names, or data structures where relevant.
- Estimate effort in minutes (5, 15, 30, 60, 120).
- Suggest the best agent type: claude, codex, aider, or custom.
- If a subtask needs a specific tool (e.g. "run migration", "commit code"), mention it.

Output ONLY valid JSON in this exact schema:
{
  "reasoning": "Brief explanation of the decomposition strategy",
  "subtasks": [
    {
      "title": "Short imperative title",
      "description": "Detailed instructions for the agent",
      "priority": 1-5,
      "estimated_minutes": number,
      "agent_type": "claude|codex|aider|custom",
      "depends_on": [],
      "needs_approval": true for complex/irreversible subtasks, false otherwise
    }
  ]
}
No markdown, no commentary outside the JSON.
"""


def _build_user_prompt(task_title: str, task_description: str, project_context: Optional[str] = None) -> str:
    """Build the user prompt for the planner LLM."""
    ctx = f"\nProject context:\n{project_context}\n" if project_context else ""
    return (
        f"Decompose the following task into bite-size subtasks.{ctx}\n\n"
        f"TASK TITLE: {task_title}\n"
        f"TASK DESCRIPTION:\n{task_description or '(none provided)'}\n\n"
        "Return ONLY a JSON object conforming to the schema. No markdown, no commentary outside the JSON."
    )


def _call_ollama_sync(
    prompt: str,
    url: str = OLLAMA_URL,
    model: str = MODEL,
    temperature: float = TEMPERATURE,
    timeout: float = TIMEOUT,
) -> str:
    """Synchronous call to Ollama /api/generate using urllib.
    Returns the raw response text.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "system": PLANNER_SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ThumbTack-Decomposer/1.0",
        },
        method="POST",
    )

    resp = urllib.request.urlopen(req, timeout=timeout)
    result = json.loads(resp.read().decode("utf-8"))
    return result.get("response", "")


def _extract_json(text: str) -> List[Dict]:
    """Extract the first JSON object from text, stripping fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    # Try direct parse
    try:
        obj = json.loads(text)
        return [obj] if isinstance(obj, dict) else []
    except json.JSONDecodeError:
        pass

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return [json.loads(text[start : end + 1])]
        except json.JSONDecodeError:
            pass

    return []


def _validate_subtasks(raw_subtasks: list) -> List[Dict[str, Any]]:
    """Normalize and validate subtask objects from LLM output."""
    validated = []
    for i, st in enumerate(raw_subtasks):
        validated.append({
            "title": (st.get("title") or f"Subtask #{i + 1}").strip(),
            "description": (st.get("description") or "").strip(),
            "priority": max(1, min(5, int(st.get("priority", 3)))),
            "estimated_minutes": max(5, int(st.get("estimated_minutes", 30))),
            "agent_type": st.get("agent_type", "claude").strip().lower(),
            "depends_on": st.get("depends_on", []) or [],
            "needs_approval": bool(st.get("needs_approval", False)),
        })
    return validated


async def decompose_task(
    task_id: int,
    *,
    custom_prompt: Optional[str] = None,
    model: str = MODEL,
    url: str = OLLAMA_URL,
) -> Dict[str, Any]:
    """Fetch the task, call the LLM planner, return structured plan.

    Returns {"ok": True, "plan": {...}, "subtasks": [...]} on success,
            {"ok": False, "error": str, "raw": str} on failure.
    """
    task = get_task(task_id)
    if not task:
        return {"ok": False, "error": f"Task #{task_id} not found"}

    project = get_project(task["project_id"])
    project_ctx = None
    if project:
        project_ctx = (
            f"Name: {project['name']}\n"
            f"Path: {project['path']}\n"
            f"Description: {project.get('description', '')}"
        )

    user_prompt = custom_prompt or _build_user_prompt(
        task["title"], task.get("description", ""), project_ctx
    )

    raw_text = ""
    try:
        # Run blocking urllib call in a thread pool so we don't freeze the event loop
        loop = asyncio.get_event_loop()
        raw_text = await loop.run_in_executor(
            None, _call_ollama_sync, user_prompt, url, model, TEMPERATURE, TIMEOUT
        )
    except urllib.error.URLError as e:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} LLM connection failed: {e}",
            task_id=task_id,
        )
        return {"ok": False, "error": f"LLM connection failed: {e}"}
    except Exception as e:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} LLM call error: {e}",
            task_id=task_id,
        )
        return {"ok": False, "error": str(e)}

    # ── Parse JSON ────────────────────────────────────────────────────────
    candidates = _extract_json(raw_text)
    if not candidates:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} no JSON found. Raw:\n{raw_text[:600]}",
            task_id=task_id,
        )
        return {
            "ok": False,
            "error": f"LLM did not return valid JSON. Got:\n{raw_text[:500]}",
            "raw": raw_text[:2000],
        }

    plan = candidates[0]
    subtasks = plan.get("subtasks", [])
    if not subtasks:
        return {
            "ok": False,
            "error": "LLM returned empty subtasks list",
            "raw": raw_text[:2000],
        }

    validated = _validate_subtasks(subtasks)

    add_agent_log(
        "TASK_PLANNED",
        f"Task #{task_id} auto-decomposed into {len(validated)} subtasks",
        task_id=task_id,
        project_id=task["project_id"],
    )
    return {"ok": True, "plan": plan, "subtasks": validated}