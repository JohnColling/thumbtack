"""ThumbTack Task Decomposer — Automatic task breakdown via local LLM + rule fallback.

Strategy:
1. Try local LLM (Ollama) with streaming + timeout.
2. If LLM times out, errors, or isn't available → instant template-based fallback.
3. Fast path can be forced with FAST_MODE=True (no LLM at all).
"""
import json
import re
import urllib.request
import urllib.error
import asyncio
from typing import List, Dict, Any, Optional

from database import add_agent_log, get_task, get_project, add_token_usage

# ── Config ───────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "kimi-k2.6:cloud"
TEMPERATURE = 0.3
TIMEOUT = 120.0           # 2 minutes — CPU-only should not hold connections longer
FAST_MODE = True          # default to template; set False to try LLM always

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


# ── Template / rule decomposer  ────────────────────────────────────────────

KEYWORD_RULES = [
    ("api",       ["Design API contract (OpenAPI/JSON)", "Implement endpoint", "Write unit tests", "Add integration tests", "Document endpoint"]),
    ("endpoint",  ["Define request/response schema", "Implement handler", "Wire up routing", "Write tests"]),
    ("webhook",   ["Design webhook payload schema", "Implement receiver endpoint", "Add signature verification", "Write integration tests"]),
    ("database",  ["Design schema / migration", "Implement models", "Add seed data / fixtures", "Write DB tests"]),
    ("migration", ["Review existing schema", "Write forward migration", "Write rollback migration", "Test migration on staging data"]),
    ("schema",    ["Draft schema design", "Create migration scripts", "Update ORM models", "Validate with sample queries"]),
    ("ui",        ["Sketch layout / wireframe", "Implement component markup", "Add styling (CSS/Tailwind)", "Bind events / state", "Write component tests"]),
    ("frontend",  ["Set up route / page", "Build layout components", "Add styling and responsiveness", "Wire API calls", "Add error states"]),
    ("page",      ["Create route scaffolding", "Build core layout", "Add dynamic data fetching", "Polish UX / loading states"]),
    ("component", ["Define props / interface", "Implement markup + logic", "Add Storybook / visual test", "Usage examples in docs"]),
    ("test",      ["Identify edge cases", "Write failing test (red)", "Implement minimal fix (green)", "Refactor / add coverage"]),
    ("deploy",    ["Verify environment variables", "Build production bundle", "Run smoke tests in staging", "Execute deployment", "Validate health checks"]),
    ("fix",       ["Reproduce bug in isolated test", "Identify root cause", "Implement minimal fix", "Verify with regression test", "Update docs if needed"]),
    ("refactor",  ["Audit current code for smells", "Write characterization tests", "Apply refactor in small steps", "Verify all tests pass", "Update docs"]),
]


def _template_decompose(title: str, description: str) -> List[Dict[str, Any]]:
    """Instant keyword-based decomposition. Always returns something usable."""
    combined = f"{title} {description or ''}".lower()
    matched = {}
    for keyword, steps in KEYWORD_RULES:
        if keyword in combined:
            matched.setdefault(keyword, steps)
    # flatten while preserving order of first appearance
    seen = set()
    flat = []
    for keyword, steps in KEYWORD_RULES:
        if keyword not in matched or keyword in seen:
            continue
        seen.add(keyword)
        flat.extend(steps)

    flat = flat[:6]   # cap subtask count
    if not flat:
        # generic fallback
        flat = [
            "Clarify requirements and acceptance criteria",
            "Research existing code / dependencies",
            "Implement core functionality",
            "Write tests and verify coverage",
            "Review and document changes",
        ]

    subtasks = []
    for i, step in enumerate(flat, start=1):
        subtasks.append({
            "title": step,
            "description": f"{step} as part of '{title}'.\nUse the project's conventions and existing patterns.",
            "priority": min(i, 5),
            "estimated_minutes": [30, 45, 60, 30, 15][i % 5],
            "agent_type": "claude",
            "depends_on": [],
            "needs_approval": i == 1,
        })
    return subtasks


# ── LLM layer ────────────────────────────────────────────────────────────────

def _call_ollama_sync(
    prompt: str,
    url: str = OLLAMA_URL,
    model: str = MODEL,
    temperature: float = TEMPERATURE,
    timeout: float = TIMEOUT,
) -> tuple[str, dict]:
    """Synchronous call to Ollama /api/generate using urllib.
    Returns (raw_response_text, usage_dict).
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

    usage = {
        "input_tokens": result.get("prompt_eval_count", 0),
        "output_tokens": result.get("eval_count", 0),
        "total_tokens": result.get("eval_count", 0) + result.get("prompt_eval_count", 0),
        "model": model,
    }
    return result.get("response", ""), usage


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


# ── Public API ───────────────────────────────────────────────────────────────

async def decompose_task(
    task_id: int,
    *,
    custom_prompt: Optional[str] = None,
    model: str = MODEL,
    url: str = OLLAMA_URL,
    force_llm: bool = False,
) -> Dict[str, Any]:
    """Fetch the task, call the LLM planner (or template fallback), return structured plan.

    Returns {"ok": True, "plan": {...}, "subtasks": [...], "source": "llm|template"} on success,
            {"ok": False, "error": str, "raw": str} on failure.
    """
    task = get_task(task_id)
    if not task:
        return {"ok": False, "error": f"Task #{task_id} not found"}

    title = task["title"]
    description = task.get("description", "")

    # ── Fast / template path ──────────────────────────────────────────
    if FAST_MODE and not force_llm:
        subtasks = _template_decompose(title, description)
        plan = {
            "reasoning": "Keyword-based template decomposition (fast mode — no LLM).",
            "subtasks": subtasks,
        }
        add_agent_log(
            "TASK_PLANNED",
            f"Task #{task_id} template-decomposed into {len(subtasks)} subtasks",
            task_id=task_id,
            project_id=task["project_id"],
        )
        return {"ok": True, "plan": plan, "subtasks": subtasks, "source": "template"}

    # ── LLM path ─────────────────────────────────────────────────────
    project = get_project(task["project_id"])
    project_ctx = None
    if project:
        project_ctx = (
            f"Name: {project['name']}\n"
            f"Path: {project['path']}\n"
            f"Description: {project.get('description', '')}"
        )

    user_prompt = custom_prompt or _build_user_prompt(title, description, project_ctx)

    raw_text, usage = "", {}
    try:
        loop = asyncio.get_event_loop()
        raw_text, usage = await loop.run_in_executor(
            None, _call_ollama_sync, user_prompt, url, model, TEMPERATURE, TIMEOUT
        )
        # log token usage for decomposition
        if usage and usage.get("total_tokens", 0) > 0:
            from usage_tracker import calculate_cost
            total_t = usage.get("total_tokens", 0)
            cost = calculate_cost(
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                model
            )
            add_agent_log(
                "USAGE_DECOMPOSE",
                f"Task #{task_id} LLM usage: {total_t} tokens (${cost:.6f})",
                task_id=task_id, project_id=task["project_id"]
            )
    except urllib.error.URLError as e:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} LLM connection failed: {e}",
            task_id=task_id,
        )
        # fallback to template
        subtasks = _template_decompose(title, description)
        plan = {
            "reasoning": f"LLM unreachable ({e}) — fell back to template decomposition.",
            "subtasks": subtasks,
        }
        return {"ok": True, "plan": plan, "subtasks": subtasks, "source": "template"}
    except Exception as e:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} LLM call error: {e}",
            task_id=task_id,
        )
        return {"ok": False, "error": str(e)}

    # ── Parse JSON ────────────────────────────────────────────────────
    candidates = _extract_json(raw_text)
    if not candidates:
        add_agent_log(
            "DECOMPOSE_ERROR",
            f"Task #{task_id} no JSON found. Raw:\n{raw_text[:600]}",
            task_id=task_id,
        )
        # fallback to template
        subtasks = _template_decompose(title, description)
        plan = {
            "reasoning": "LLM did not return valid JSON — fell back to template decomposition.",
            "subtasks": subtasks,
        }
        return {"ok": True, "plan": plan, "subtasks": subtasks, "source": "template"}

    plan = candidates[0]
    subtasks = plan.get("subtasks", [])
    if not subtasks:
        subtasks = _template_decompose(title, description)
        plan = {
            "reasoning": "LLM returned empty subtasks — fell back to template decomposition.",
            "subtasks": subtasks,
        }
        return {"ok": True, "plan": plan, "subtasks": subtasks, "source": "template"}

    validated = _validate_subtasks(subtasks)

    add_agent_log(
        "TASK_PLANNED",
        f"Task #{task_id} LLM-decomposed into {len(validated)} subtasks",
        task_id=task_id,
        project_id=task["project_id"],
    )
    return {"ok": True, "plan": plan, "subtasks": validated, "source": "llm"}
