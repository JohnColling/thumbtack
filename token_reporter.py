"""ThumbTack Token Reporter — Lightweight client for external agents to report usage.

Usage from inside an external agent:
    from token_reporter import report_tokens
    report_tokens(total_tokens=1234, input_tokens=900, output_tokens=334, model="claude-3-5-sonnet")

Or from shell:
    python token_reporter.py --tokens 1234 --input 900 --output 334 --model claude-3-5-sonnet
"""
import os
import json
import urllib.request
import urllib.error
from typing import Optional

# Default to localhost:3456 (ThumbTack)
THUMBTACK_URL = os.environ.get("THUMBTACK_URL", "http://127.0.0.1:3456")

def report_tokens(
    total_tokens: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    model: str = "unknown",
    cost: float = 0.0,
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    session_id: str = "default",
) -> bool:
    """Report token usage back to ThumbTack. Returns True on success."""
    payload = {
        "session_id": session_id,
        "project_id": project_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "model": model,
        "request_count": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens or (input_tokens + output_tokens),
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cost": cost,
    }
    data = json.dumps(payload).encode("utf-8")
    url = f"{THUMBTACK_URL}/api/token-usage"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Report token usage to ThumbTack")
    parser.add_argument("--tokens", type=int, default=0)
    parser.add_argument("--input", type=int, dest="input_tokens", default=0)
    parser.add_argument("--output", type=int, dest="output_tokens", default=0)
    parser.add_argument("--cached", type=int, default=0)
    parser.add_argument("--model", type=str, default="unknown")
    parser.add_argument("--cost", type=float, default=0.0)
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--session-id", type=str, default="default")
    args = parser.parse_args()
    
    ok = report_tokens(
        total_tokens=args.tokens,
        input_tokens=args.input_tokens,
        output_tokens=args.output_tokens,
        cached_tokens=args.cached,
        model=args.model,
        cost=args.cost,
        project_id=args.project_id,
        task_id=args.task_id,
        session_id=args.session_id,
    )
    print("Reported" if ok else "Failed")
