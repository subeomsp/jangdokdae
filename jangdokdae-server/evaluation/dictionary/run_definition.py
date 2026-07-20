"""승인 definition 골드셋에 실제 생성·검증 파이프라인을 실행하는 CLI."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from evaluation.dictionary.definition_report import render_definition_run_markdown
from evaluation.dictionary.definition_runner import run_definition_trials
from evaluation.dictionary.definition_schemas import load_definition_tasks

SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = Path(__file__).with_name("tasks") / "definition_gold.jsonl"
DEFAULT_RESULTS_DIR = SERVER_ROOT / "docs" / "evaluation" / "results"


async def _run(args: argparse.Namespace) -> tuple[Path, Path]:
    tasks = load_definition_tasks(args.tasks)
    result = await run_definition_trials(tasks, repeats=args.repeats)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S")
    stem = f"dictionary-definition-eval-{timestamp}"
    json_path = args.output_dir / f"{stem}.json"
    markdown_path = args.output_dir / f"{stem}.md"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_definition_run_markdown(result),
        encoding="utf-8",
    )
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description="한국은행 쉬운 설명 반복 평가")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args()
    json_path, markdown_path = asyncio.run(_run(args))
    print(f"JSON transcript: {json_path}")
    print(f"Markdown report: {markdown_path}")


if __name__ == "__main__":
    main()
