"""승인 골드셋에 실제 분리 제안기를 실행하는 CLI.

실행:
    uv run python -m evaluation.dictionary.run_segmentation --repeats 3
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from evaluation.dictionary.report import render_run_markdown
from evaluation.dictionary.runner import run_segmentation_trials
from evaluation.dictionary.schemas import load_segmentation_tasks

SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = Path(__file__).with_name("tasks") / "segmentation_gold.jsonl"
DEFAULT_RESULTS_DIR = SERVER_ROOT / "docs" / "evaluation" / "results"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="한국은행 용어 분리 에이전트 평가")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser


async def _run(args: argparse.Namespace) -> tuple[Path, Path]:
    tasks = load_segmentation_tasks(args.tasks)
    result = await run_segmentation_trials(tasks, repeats=args.repeats)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S")
    stem = f"dictionary-segmentation-eval-{timestamp}"
    json_path = args.output_dir / f"{stem}.json"
    markdown_path = args.output_dir / f"{stem}.md"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_run_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    args = _parser().parse_args()
    json_path, markdown_path = asyncio.run(_run(args))
    print(f"JSON transcript: {json_path}")
    print(f"Markdown report: {markdown_path}")


if __name__ == "__main__":
    main()
