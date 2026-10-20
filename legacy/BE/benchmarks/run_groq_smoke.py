import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from run_chat_latency import run_ask_once, run_stream_once


DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parent / "output" / "groq-real-chat-latency"
)
DEFAULT_QUESTION = "How are embeddings generated and stored in this project?"


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.fmean(values), 2)


def build_markdown_report(report: dict[str, Any]) -> str:
    ask_summary = report["ask"]["summary"]
    lines = [
        "# Groq Smoke Benchmark",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Base URL: `{report['base_url']}`",
        f"- Provider: `{report['provider']}`",
        f"- Question: {report['question']}",
        f"- Ask warmup runs: `{report['ask']['warmup_runs']}`",
        f"- Ask measured runs: `{report['ask']['measured_runs']}`",
        f"- Stream measured runs: `{report['stream']['measured_runs']}`",
        f"- Delay between ask requests: `{report['delay_seconds']}s`",
        "",
        "## Ask Summary",
        "",
    ]

    for key, value in ask_summary.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Stream Summary", ""])

    for key, value in report["stream"]["summary"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This script is intentionally low-volume for real-provider latency checks.",
            "- It spaces ask calls to reduce Groq rate-limit pressure.",
            "- Retrieval timings come from backend latency metadata; request/stream timings come from the client.",
            "",
        ]
    )
    return "\n".join(lines)


async def run_ask_series(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    warmup_runs: int,
    measured_runs: int,
    delay_seconds: float,
) -> dict[str, Any]:
    warmups: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []

    for _ in range(warmup_runs):
        body, samples = await run_ask_once(client, url, payload, "groq_smoke_warmup")
        warmups.append({"provider": body["provider"], "latency": body["latency"], "samples": samples})
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    for run_index in range(measured_runs):
        body, samples = await run_ask_once(client, url, payload, f"groq_smoke_ask_{run_index + 1}")
        runs.append(
            {
                "provider": body["provider"],
                "context_count": body["context_count"],
                "latency": body["latency"],
                "answer_preview": body["answer"][:300],
                "samples": samples,
            }
        )
        if delay_seconds > 0 and run_index < measured_runs - 1:
            await asyncio.sleep(delay_seconds)

    return {
        "warmup_runs": warmup_runs,
        "measured_runs": measured_runs,
        "warmups": warmups,
        "runs": runs,
        "summary": {
            "external_request_ms_avg": average([run["samples"]["external_request_ms"] for run in runs]),
            "retrieval_total_ms_avg": average(
                [run["latency"]["retrieval"]["total_ms"] for run in runs]
            ),
            "query_embedding_ms_avg": average(
                [run["latency"]["retrieval"]["query_embedding_ms"] for run in runs]
            ),
            "vector_search_ms_avg": average(
                [run["latency"]["retrieval"]["vector_search_ms"] for run in runs]
            ),
            "llm_generation_ms_avg": average([run["latency"]["llm_generation_ms"] for run in runs]),
            "total_ms_avg": average([run["latency"]["total_ms"] for run in runs]),
        },
    }


async def run_stream_series(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    *,
    measured_runs: int,
    delay_seconds: float,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []

    for run_index in range(measured_runs):
        metadata, samples = await run_stream_once(
            client,
            url,
            payload,
            f"groq_smoke_stream_{run_index + 1}",
        )
        runs.append({"metadata": metadata, "samples": samples})
        if delay_seconds > 0 and run_index < measured_runs - 1:
            await asyncio.sleep(delay_seconds)

    return {
        "measured_runs": measured_runs,
        "runs": runs,
        "summary": {
            "stream_first_chunk_ms_avg": average(
                [run["samples"]["stream_first_chunk_ms"] for run in runs]
            ),
            "stream_total_ms_avg": average([run["samples"]["stream_total_ms"] for run in runs]),
            "retrieval_total_ms_avg": average(
                [run["metadata"]["latency"]["retrieval"]["total_ms"] for run in runs]
            ),
            "query_embedding_ms_avg": average(
                [run["metadata"]["latency"]["retrieval"]["query_embedding_ms"] for run in runs]
            ),
            "vector_search_ms_avg": average(
                [run["metadata"]["latency"]["retrieval"]["vector_search_ms"] for run in runs]
            ),
            "prompt_build_ms_avg": average(
                [run["metadata"]["latency"]["prompt_build_ms"] for run in runs]
            ),
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a low-volume Groq smoke benchmark.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument("--provider", default="groq", help="Chat provider override.")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Question to ask.")
    parser.add_argument("--top-k", type=int, default=3, help="Top K retrieval value.")
    parser.add_argument("--document-id", type=int, default=None, help="Optional document scope.")
    parser.add_argument("--ask-warmup-runs", type=int, default=1, help="Warmup ask runs.")
    parser.add_argument("--ask-runs", type=int, default=3, help="Measured ask runs.")
    parser.add_argument("--stream-runs", type=int, default=1, help="Measured stream runs.")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Delay between provider calls to reduce rate-limit pressure.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
        help="HTTP timeout for each request.",
    )
    parser.add_argument(
        "--include-debug",
        action="store_true",
        help="Request debug payloads from the backend.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for JSON/Markdown outputs.",
    )
    parser.add_argument(
        "--output-stem",
        default="",
        help="Optional output filename stem without extension. Defaults to a timestamped groq smoke name.",
    )
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "question": args.question,
        "top_k": args.top_k,
        "provider": args.provider,
        "include_debug": args.include_debug,
    }
    if args.document_id is not None:
        payload["document_id"] = args.document_id

    ask_url = f"{args.base_url.rstrip('/')}/chat/ask"
    stream_url = f"{args.base_url.rstrip('/')}/chat/stream"

    async with httpx.AsyncClient(timeout=args.timeout_seconds) as client:
        ask_report = await run_ask_series(
            client,
            ask_url,
            payload,
            warmup_runs=args.ask_warmup_runs,
            measured_runs=args.ask_runs,
            delay_seconds=args.delay_seconds,
        )

        if args.delay_seconds > 0:
            await asyncio.sleep(args.delay_seconds)

        stream_report = await run_stream_series(
            client,
            stream_url,
            payload,
            measured_runs=args.stream_runs,
            delay_seconds=args.delay_seconds,
        )

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "provider": args.provider,
        "question": args.question,
        "top_k": args.top_k,
        "document_id": args.document_id,
        "delay_seconds": args.delay_seconds,
        "ask": ask_report,
        "stream": stream_report,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_stem = args.output_stem.strip() or f"groq-smoke_{timestamp}"
    json_path = output_dir / f"{output_stem}.json"
    markdown_path = output_dir / f"{output_stem}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(build_markdown_report(report), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Saved JSON results to: {json_path}")
    print(f"Saved Markdown report to: {markdown_path}")


if __name__ == "__main__":
    asyncio.run(main())
