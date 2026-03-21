#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from browser_runtime import BrowserHarness, BrowserObservation, FixtureServer  # noqa: E402


FIXTURE_ROOT = PROJECT_ROOT / "fixtures" / "browser"
RUN_ROOT = PROJECT_ROOT / ".miniclaw" / "browser_runs"


@dataclass(frozen=True)
class TaskSpec:
    id: str
    fixture: str
    goal: str
    steps: list[dict[str, Any]]


TASKS: list[TaskSpec] = [
    TaskSpec(
        id="browser_task_001_read_simple_page",
        fixture="simple_page.html",
        goal="Open the page and report its title and visible text.",
        steps=[
            {"kind": "navigate", "path": "/simple_page.html"},
            {"kind": "extract", "extract_kind": "text"},
        ],
    ),
    TaskSpec(
        id="browser_task_002_click_button",
        fixture="click_page.html",
        goal="Click the reveal button and extract the now-visible message.",
        steps=[
            {"kind": "navigate", "path": "/click_page.html"},
            {"kind": "snapshot"},
            {"kind": "act", "action": "click", "target": "[data-testid='reveal-button']"},
            {"kind": "extract", "extract_kind": "text"},
        ],
    ),
    TaskSpec(
        id="browser_task_003_search_flow",
        fixture="search_page.html",
        goal="Search for apple and extract the top three result labels.",
        steps=[
            {"kind": "navigate", "path": "/search_page.html"},
            {"kind": "act", "action": "type", "target": "[data-testid='query']", "value": "apple"},
            {"kind": "act", "action": "click", "target": "[data-testid='submit']"},
            {"kind": "extract", "extract_kind": "list"},
        ],
    ),
    TaskSpec(
        id="browser_task_004_submit_form",
        fixture="form_page.html",
        goal="Fill the form, submit it, and confirm the echoed values.",
        steps=[
            {"kind": "navigate", "path": "/form_page.html"},
            {"kind": "act", "action": "type", "target": "[data-testid='name']", "value": "Welf"},
            {"kind": "act", "action": "type", "target": "[data-testid='email']", "value": "welf@example.com"},
            {"kind": "act", "action": "click", "target": "[data-testid='submit']"},
            {"kind": "extract", "extract_kind": "text"},
        ],
    ),
    TaskSpec(
        id="browser_task_005_wait_for_dynamic_content",
        fixture="dynamic_page.html",
        goal="Trigger the delayed content update, wait for it, and extract the loaded text.",
        steps=[
            {"kind": "navigate", "path": "/dynamic_page.html"},
            {"kind": "act", "action": "click", "target": "[data-testid='load-button']"},
            {"kind": "act", "action": "wait", "target": "[data-testid='loaded-state']", "value": "Data loaded successfully"},
            {"kind": "extract", "extract_kind": "text"},
        ],
    ),
]


def _task_map() -> dict[str, TaskSpec]:
    return {task.id: task for task in TASKS}


def verify_task(task: TaskSpec, observations: list[BrowserObservation]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not observations:
        return False, ["no observations recorded"]
    if len(observations) > 20:
        reasons.append("step budget exceeded")
    final = observations[-1]
    if any(not observation.ok for observation in observations):
        reasons.append("one or more steps failed")

    extracted = (final.extracted or {}).get("value")
    if task.id == "browser_task_001_read_simple_page":
        if final.title != "Simple Page":
            reasons.append(f"unexpected title: {final.title!r}")
        text = str(extracted or "")
        if "Simple Page Heading" not in text or "deterministic body text" not in text:
            reasons.append("expected simple-page text missing")
    elif task.id == "browser_task_002_click_button":
        text = str(extracted or "")
        if "hidden panel is now visible" not in text:
            reasons.append("revealed message missing after click")
        if len(observations) > 6:
            reasons.append("step count exceeded 6")
    elif task.id == "browser_task_003_search_flow":
        expected = ["Apple Pie", "Apple Cider", "Apple Jam"]
        if extracted != expected:
            reasons.append(f"unexpected result list: {extracted!r}")
    elif task.id == "browser_task_004_submit_form":
        text = str(extracted or "")
        for snippet in ("Submission complete.", "Welf", "welf@example.com"):
            if snippet not in text:
                reasons.append(f"missing form result snippet: {snippet}")
    elif task.id == "browser_task_005_wait_for_dynamic_content":
        text = str(extracted or "")
        if "Data loaded successfully" not in text:
            reasons.append("dynamic loaded text missing")
    else:
        reasons.append(f"unknown task verifier: {task.id}")

    for observation in observations:
        if not observation.screenshot_path:
            reasons.append(f"missing screenshot for step {observation.step_index}")
            break
    return not reasons, reasons


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_task(task: TaskSpec, *, headless: bool, timeout_ms: int, port: int) -> dict[str, Any]:
    run_id = f"{task.id}-{uuid.uuid4().hex[:8]}"
    run_dir = RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "task_id": task.id,
            "fixture": task.fixture,
            "goal": task.goal,
            "headless": headless,
            "timeout_ms": timeout_ms,
            "created_at": int(time.time()),
        },
    )

    with FixtureServer(FIXTURE_ROOT, port=port) as server:
        observations: list[BrowserObservation] = []
        with BrowserHarness(run_dir, headless=headless, timeout_ms=timeout_ms) as harness:
            for index, step in enumerate(task.steps, start=1):
                observation = harness.execute_step(index, step, base_url=server.base_url)
                observations.append(observation)

    passed, reasons = verify_task(task, observations)
    result = {
        "ok": passed,
        "task_id": task.id,
        "run_dir": str(run_dir),
        "step_count": len(observations),
        "reasons": reasons,
    }
    _write_json(run_dir / "result.json", result)
    return result


def check_fixtures(port: int) -> dict[str, Any]:
    missing = [task.fixture for task in TASKS if not (FIXTURE_ROOT / task.fixture).exists()]
    results: list[dict[str, Any]] = []
    if missing:
        return {"ok": False, "missing": missing, "results": results}

    with FixtureServer(FIXTURE_ROOT, port=port) as server:
        for task in TASKS:
            url = f"{server.base_url}/{task.fixture}"
            with urllib_request.urlopen(url, timeout=5) as response:
                body = response.read(512).decode("utf-8", errors="replace")
                results.append(
                    {
                        "task_id": task.id,
                        "url": url,
                        "status": response.status,
                        "sample": body[:120],
                    }
                )
    return {"ok": True, "results": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone browser acceptance harness for miniclaw.")
    parser.add_argument("--task", choices=sorted(_task_map().keys()), help="Run one acceptance task.")
    parser.add_argument("--all", action="store_true", help="Run all acceptance tasks.")
    parser.add_argument("--list-tasks", action="store_true", help="Print the known task IDs and goals.")
    parser.add_argument("--check-fixtures", action="store_true", help="Serve local fixtures and verify they are reachable.")
    parser.add_argument("--headed", action="store_true", help="Run the browser with a visible window.")
    parser.add_argument("--timeout-ms", type=int, default=10_000, help="Per-action timeout in milliseconds.")
    parser.add_argument("--port", type=int, default=0, help="Fixture server port; 0 picks a random free port.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_tasks:
        print(json.dumps([asdict(task) for task in TASKS], ensure_ascii=False, indent=2))
        return 0

    if args.check_fixtures:
        result = check_fixtures(port=args.port)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if not args.task and not args.all:
        parser.error("choose one of --task, --all, --list-tasks, or --check-fixtures")

    task_map = _task_map()
    selected = TASKS if args.all else [task_map[args.task]]
    batch_results: list[dict[str, Any]] = []
    for task in selected:
        batch_results.append(
            run_task(task, headless=not args.headed, timeout_ms=args.timeout_ms, port=args.port)
        )
    summary = {
        "ok": all(item["ok"] for item in batch_results),
        "results": batch_results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
