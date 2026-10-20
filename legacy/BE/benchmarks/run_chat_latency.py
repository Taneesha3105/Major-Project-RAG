import argparse
import asyncio
import json
import statistics
import time
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "cases" / "sample_chat_cases.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
GROQ_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "groq-real-chat-latency"
FLASHRANK_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "flashrank-rerank-latency"
ASK_METRIC_NAMES = [
    "external_request_ms",
    "chat_total_ms",
    "retrieval_total_ms",
    "query_embedding_ms",
    "vector_search_ms",
    "prompt_build_ms",
    "rerank_ms",
    "llm_generation_ms",
]
STREAM_METRIC_NAMES = [
    "stream_first_chunk_ms",
    "stream_total_ms",
    "retrieval_total_ms",
    "query_embedding_ms",
    "vector_search_ms",
    "prompt_build_ms",
    "rerank_ms",
]


def build_payload(
    case: dict[str, Any],
    provider: str | None,
    include_debug: bool,
    rerank_strategy: str | None,
    retrieval_mode: str | None,
) -> dict[str, Any]:
    payload = {
        "question": case["question"],
        "top_k": case.get("top_k", 3),
        "include_debug": include_debug,
    }
    if case.get("document_id") is not None:
        payload["document_id"] = case["document_id"]
    if provider:
        payload["provider"] = provider
    if rerank_strategy:
        payload["rerank_strategy"] = rerank_strategy
    if retrieval_mode:
        payload["retrieval_mode"] = retrieval_mode
    return payload


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    sanitized = "".join(character if character.isalnum() else "-" for character in lowered)
    compacted = "-".join(part for part in sanitized.split("-") if part)
    return compacted or "default"


def percentile(values: list[float], target_percentile: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)

    rank = (target_percentile / 100) * (len(ordered) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = rank - lower_index
    interpolated = ordered[lower_index] + ((ordered[upper_index] - ordered[lower_index]) * weight)
    return round(interpolated, 2)


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "avg_ms": round(statistics.fmean(values), 2),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


async def run_case(
    client: httpx.AsyncClient,
    url: str,
    case: dict[str, Any],
    *,
    runs: int,
    warmup_runs: int,
    provider: str | None,
    include_debug: bool,
    response_mode: str,
    delay_seconds: float,
    rerank_strategy: str | None,
    retrieval_mode: str | None,
) -> dict[str, Any]:
    metric_names = ASK_METRIC_NAMES if response_mode == "ask" else STREAM_METRIC_NAMES
    metrics: dict[str, list[float]] = {metric_name: [] for metric_name in metric_names}

    payload = build_payload(case, provider, include_debug, rerank_strategy, retrieval_mode)

    total_attempts = warmup_runs + runs
    for attempt_index in range(total_attempts):
        if response_mode == "ask":
            _, samples = await run_ask_once(client, url, payload, case["name"])
        else:
            _, samples = await run_stream_once(client, url, payload, case["name"])

        if attempt_index >= warmup_runs:
            for metric_name, metric_value in samples.items():
                metrics[metric_name].append(metric_value)

        if delay_seconds > 0 and attempt_index < (total_attempts - 1):
            await asyncio.sleep(delay_seconds)

    if len(metrics[metric_names[0]]) != runs:
        raise RuntimeError("Benchmark run count did not match the requested number of measured runs.")

    return {
        "case": case["name"],
        "question": case["question"],
        "document_id": case.get("document_id"),
        "top_k": payload["top_k"],
        "provider": provider or "default",
        "rerank_strategy": rerank_strategy or "default",
        "retrieval_mode": retrieval_mode or "default",
        "response_mode": response_mode,
        "runs": runs,
        "summary": {metric_name: summarize(samples) for metric_name, samples in metrics.items()},
        "_samples": metrics,
    }


async def run_global_warmup(
    client: httpx.AsyncClient,
    url: str,
    case: dict[str, Any],
    *,
    warmup_runs: int,
    provider: str | None,
    include_debug: bool,
    response_mode: str,
    delay_seconds: float,
    rerank_strategy: str | None,
    retrieval_mode: str | None,
) -> dict[str, Any]:
    payload = build_payload(case, provider, include_debug, rerank_strategy, retrieval_mode)

    for warmup_index in range(warmup_runs):
        if response_mode == "ask":
            await run_ask_once(client, url, payload, f"{case['name']}_global_warmup")
        else:
            await run_stream_once(client, url, payload, f"{case['name']}_global_warmup")

        if delay_seconds > 0 and warmup_index < (warmup_runs - 1):
            await asyncio.sleep(delay_seconds)

    return {
        "case": case["name"],
        "question": case["question"],
        "document_id": case.get("document_id"),
        "top_k": payload["top_k"],
        "provider": provider or "default",
        "rerank_strategy": rerank_strategy or "default",
        "retrieval_mode": retrieval_mode or "default",
        "response_mode": response_mode,
        "warmup_runs": warmup_runs,
    }


async def run_ask_once(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    case_name: str,
) -> tuple[dict[str, Any], dict[str, float]]:
    request_start = time.perf_counter()
    response = await client.post(url, json=payload)
    external_request_ms = round((time.perf_counter() - request_start) * 1000, 2)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response_body = response.text.strip()
        raise RuntimeError(
            f"Benchmark case '{case_name}' failed with status {response.status_code} "
            f"for payload {payload}. Response body: {response_body}"
        ) from exc

    body = response.json()
    latency = body["latency"]
    retrieval_latency = latency["retrieval"]
    return body, {
        "external_request_ms": external_request_ms,
        "chat_total_ms": latency["total_ms"],
        "retrieval_total_ms": retrieval_latency["total_ms"],
        "query_embedding_ms": retrieval_latency["query_embedding_ms"],
        "vector_search_ms": retrieval_latency["vector_search_ms"],
        "prompt_build_ms": latency["prompt_build_ms"],
        "rerank_ms": latency.get("rerank_ms", 0.0),
        "llm_generation_ms": latency["llm_generation_ms"],
    }


async def run_stream_once(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    case_name: str,
) -> tuple[dict[str, Any], dict[str, float]]:
    request_start = time.perf_counter()
    first_chunk_ms: float | None = None
    metadata_payload: dict[str, Any] | None = None

    async with client.stream("POST", url, json=payload) as response:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_body = (await response.aread()).decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Benchmark case '{case_name}' failed with status {response.status_code} "
                f"for payload {payload}. Response body: {response_body}"
            ) from exc

        async for event_name, event_payload in iter_sse_events(response):
            if event_name == "metadata":
                metadata_payload = event_payload
            elif event_name == "chunk" and first_chunk_ms is None:
                first_chunk_ms = round((time.perf_counter() - request_start) * 1000, 2)

    stream_total_ms = round((time.perf_counter() - request_start) * 1000, 2)

    if metadata_payload is None:
        raise RuntimeError(f"Streaming benchmark case '{case_name}' did not emit metadata.")

    if first_chunk_ms is None:
        first_chunk_ms = stream_total_ms

    latency = metadata_payload["latency"]
    retrieval_latency = latency["retrieval"]
    return metadata_payload, {
        "stream_first_chunk_ms": first_chunk_ms,
        "stream_total_ms": stream_total_ms,
        "retrieval_total_ms": retrieval_latency["total_ms"],
        "query_embedding_ms": retrieval_latency["query_embedding_ms"],
        "vector_search_ms": retrieval_latency["vector_search_ms"],
        "prompt_build_ms": latency["prompt_build_ms"],
        "rerank_ms": latency.get("rerank_ms", 0.0),
    }


async def iter_sse_events(response: httpx.Response) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    current_event_name = "message"
    current_data_lines: list[str] = []

    async for raw_line in response.aiter_lines():
        line = raw_line.strip()

        if not line:
            if current_data_lines:
                payload = "\n".join(current_data_lines).strip()
                if payload:
                    yield current_event_name, json.loads(payload)
                current_event_name = "message"
                current_data_lines = []
            continue

        if line.startswith("event:"):
            current_event_name = line[6:].strip() or "message"
        elif line.startswith("data:"):
            current_data_lines.append(line[5:].strip())

    if current_data_lines:
        payload = "\n".join(current_data_lines).strip()
        if payload:
            yield current_event_name, json.loads(payload)


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)

    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases file must contain a non-empty JSON list.")

    for case in cases:
        if "name" not in case or "question" not in case:
            raise ValueError("Each benchmark case must include 'name' and 'question'.")

    return cases


def build_overall_summary(results: list[dict[str, Any]], metric_names: list[str]) -> dict[str, dict[str, float]]:
    aggregate_samples: dict[str, list[float]] = {metric_name: [] for metric_name in metric_names}

    for result in results:
        for metric_name in metric_names:
            aggregate_samples[metric_name].extend(result["_samples"][metric_name])

    return {metric_name: summarize(samples) for metric_name, samples in aggregate_samples.items()}


def build_report_markdown(report: dict[str, Any]) -> str:
    results = report["results"]
    metric_names = report["metric_names"]
    is_stream_mode = report["response_mode"] == "stream"
    lines = [
        "# Chat Latency Benchmark Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Request URL: `{report['request_url']}`",
        f"- Chat provider override: `{report['provider']}`",
        f"- Response mode: `{report['response_mode']}`",
        f"- Rerank strategy: `{report['rerank_strategy']}`",
        f"- Retrieval mode: `{report['retrieval_mode']}`",
        f"- Include debug payloads: `{report['include_debug']}`",
        f"- Warmup runs per case: `{report['warmup_runs_per_case']}`",
        f"- Warmup scope: `{report['warmup_scope']}`",
        f"- Total warmup requests: `{report['total_warmup_requests']}`",
        f"- Measured runs per case: `{report['runs_per_case']}`",
        f"- Total measured requests: `{report['total_measured_requests']}`",
        "",
        "## Key Findings",
        "",
    ]

    if report.get("global_warmup_case"):
        lines.extend(
            [
                f"- Global warmup case: `{report['global_warmup_case']['case']}`",
                "",
            ]
        )

    for case in results:
        summary = case["summary"]
        retrieval_avg = summary["retrieval_total_ms"]["avg_ms"]
        query_embedding_avg = summary["query_embedding_ms"]["avg_ms"]
        vector_search_avg = summary["vector_search_ms"]["avg_ms"]
        embedding_share = round((query_embedding_avg / retrieval_avg) * 100, 2) if retrieval_avg else 0.0

        if is_stream_mode:
            first_chunk_avg = summary["stream_first_chunk_ms"]["avg_ms"]
            stream_total_avg = summary["stream_total_ms"]["avg_ms"]
            lines.append(
                f"- `{case['case']}`: first streamed chunk averages `{first_chunk_avg} ms`, "
                f"full stream averages `{stream_total_avg} ms`, and query embedding averages "
                f"`{query_embedding_avg} ms` which is `{embedding_share}%` of retrieval time. "
                f"Vector search averages `{vector_search_avg} ms`."
            )
        else:
            llm_avg = summary["llm_generation_ms"]["avg_ms"]
            lines.append(
                f"- `{case['case']}`: query embedding averages `{query_embedding_avg} ms`, "
                f"which is `{embedding_share}%` of retrieval time. Vector search averages "
                f"`{vector_search_avg} ms` and chat generation averages `{llm_avg} ms`."
            )

    overall_summary = report["overall_summary"]
    overall_retrieval_avg = overall_summary["retrieval_total_ms"]["avg_ms"]
    overall_query_embedding_avg = overall_summary["query_embedding_ms"]["avg_ms"]
    overall_embedding_share = (
        round((overall_query_embedding_avg / overall_retrieval_avg) * 100, 2)
        if overall_retrieval_avg
        else 0.0
    )

    lines.extend(
        [
            "",
            "## Overall Summary",
            "",
            f"- All measured requests: `{report['total_measured_requests']}`",
            f"- Query embedding average: `{overall_query_embedding_avg} ms`",
            f"- Retrieval average: `{overall_retrieval_avg} ms`",
            f"- Query embedding share of retrieval time: `{overall_embedding_share}%`",
            "",
            "| Metric | Avg (ms) | P50 (ms) | P95 (ms) | Min (ms) | Max (ms) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for metric_name in metric_names:
        metric = overall_summary[metric_name]
        lines.append(
            f"| `{metric_name}` | {metric['avg_ms']} | {metric['p50_ms']} | "
            f"{metric['p95_ms']} | {metric['min_ms']} | {metric['max_ms']} |"
        )

    lines.extend(
        [
            "",
            "## Per-Case Summary",
            "",
        ]
    )

    for case in results:
        lines.extend(
            [
                f"### {case['case']}",
                "",
                f"- Question: {case['question']}",
                f"- Top K: `{case['top_k']}`",
                f"- Document Scope: `{case['document_id']}`",
                f"- Response Mode: `{case['response_mode']}`",
                "",
                "| Metric | Avg (ms) | P50 (ms) | P95 (ms) | Min (ms) | Max (ms) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for metric_name in metric_names:
            metric = case["summary"][metric_name]
            lines.append(
                f"| `{metric_name}` | {metric['avg_ms']} | {metric['p50_ms']} | "
                f"{metric['p95_ms']} | {metric['min_ms']} | {metric['max_ms']} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- If `query_embedding_ms` stays close to total retrieval time, the embedding provider is the bottleneck.",
            "- If `vector_search_ms` rises sharply later, investigate pgvector indexing, data volume, and `top_k` settings.",
            (
                "- In `stream` mode, `stream_first_chunk_ms` is the TTFT-style metric and "
                "`stream_total_ms` captures the full streamed response duration."
                if is_stream_mode
                else "- With `provider=mock`, `llm_generation_ms` should stay near zero, which helps isolate RAG retrieval cost."
            ),
        ]
    )

    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark chat latency for the RAG chatbot API.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument(
        "--api-prefix",
        default="",
        help="FastAPI prefix used by the backend.",
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Path to a JSON file containing benchmark cases.",
    )
    parser.add_argument("--runs", type=int, default=10, help="Measured runs per case.")
    parser.add_argument("--warmup-runs", type=int, default=2, help="Warmup runs. Scope depends on --warmup-scope.")
    parser.add_argument(
        "--warmup-scope",
        choices=("global", "per_case"),
        default="global",
        help="Whether warmup runs happen once using the first case or separately for every case.",
    )
    parser.add_argument(
        "--provider",
        default="mock",
        help="Chat provider override. Use 'mock' to isolate retrieval from real LLM latency.",
    )
    parser.add_argument(
        "--rerank-strategy",
        choices=("fast", "hybrid", "neural"),
        default="",
        help="Optional chat rerank strategy override.",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("exact", "ann_rerank"),
        default="",
        help="Optional retrieval mode override.",
    )
    parser.add_argument(
        "--response-mode",
        choices=("ask", "stream"),
        default="ask",
        help="Whether to benchmark the non-streaming /chat/ask route or the streaming /chat/stream route.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP timeout for each benchmark request.",
    )
    parser.add_argument(
        "--include-debug",
        action="store_true",
        help="Include prompt and full context payloads in benchmarked chat responses.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay between requests and between cases. Useful for low-volume real-provider benchmarks like Groq.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to save the benchmark result JSON.",
    )
    parser.add_argument(
        "--report-output",
        default="",
        help="Optional path to save the Markdown benchmark report.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for timestamped benchmark outputs when explicit file paths are not provided.",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    api_prefix = args.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"

    route_name = "ask" if args.response_mode == "ask" else "stream"
    request_url = f"{args.base_url.rstrip('/')}{api_prefix}/chat/{route_name}"

    async with httpx.AsyncClient(timeout=args.timeout_seconds) as client:
        raw_results = []
        total_cases = len(cases)
        global_warmup_case = None

        if args.warmup_scope == "global" and args.warmup_runs > 0:
            global_warmup_case = await run_global_warmup(
                client,
                request_url,
                cases[0],
                warmup_runs=args.warmup_runs,
                provider=args.provider.strip() or None,
                include_debug=args.include_debug,
                response_mode=args.response_mode,
                delay_seconds=args.delay_seconds,
                rerank_strategy=args.rerank_strategy.strip() or None,
                retrieval_mode=args.retrieval_mode.strip() or None,
            )
            if args.delay_seconds > 0 and total_cases > 0:
                await asyncio.sleep(args.delay_seconds)

        for index, case in enumerate(cases, start=1):
            effective_warmup_runs = args.warmup_runs if args.warmup_scope == "per_case" else 0
            print(
                f"Running case {index}/{total_cases}: {case['name']} "
                f"(mode={args.response_mode}, warmup_scope={args.warmup_scope}, "
                f"warmup={effective_warmup_runs}, measured={args.runs})"
            )
            result = await run_case(
                client,
                request_url,
                case,
                runs=args.runs,
                warmup_runs=args.warmup_runs if args.warmup_scope == "per_case" else 0,
                provider=args.provider.strip() or None,
                include_debug=args.include_debug,
                response_mode=args.response_mode,
                delay_seconds=args.delay_seconds,
                rerank_strategy=args.rerank_strategy.strip() or None,
                retrieval_mode=args.retrieval_mode.strip() or None,
            )
            raw_results.append(result)
            print(f"Completed case {index}/{total_cases}: {case['name']}")
            if args.delay_seconds > 0 and index < total_cases:
                await asyncio.sleep(args.delay_seconds)

    metric_names = ASK_METRIC_NAMES if args.response_mode == "ask" else STREAM_METRIC_NAMES
    overall_summary = build_overall_summary(raw_results, metric_names)
    results = [{key: value for key, value in result.items() if key != "_samples"} for result in raw_results]

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "request_url": request_url,
        "runs_per_case": args.runs,
        "warmup_runs_per_case": args.warmup_runs,
        "warmup_scope": args.warmup_scope,
        "global_warmup_case": global_warmup_case,
        "total_warmup_requests": args.warmup_runs if args.warmup_scope == "global" else len(cases) * args.warmup_runs,
        "total_measured_requests": len(cases) * args.runs,
        "provider": args.provider,
        "rerank_strategy": args.rerank_strategy or "default",
        "retrieval_mode": args.retrieval_mode or "default",
        "response_mode": args.response_mode,
        "include_debug": args.include_debug,
        "metric_names": metric_names,
        "overall_summary": overall_summary,
        "results": results,
    }

    print(json.dumps(report, indent=2))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    provider_slug = slugify(args.provider or "default")
    rerank_strategy_slug = slugify(args.rerank_strategy or "default")
    retrieval_mode_slug = slugify(args.retrieval_mode or "default")
    if args.output_dir == str(DEFAULT_OUTPUT_DIR) and args.rerank_strategy:
        output_dir = FLASHRANK_OUTPUT_DIR
    elif args.output_dir == str(DEFAULT_OUTPUT_DIR) and provider_slug == "groq":
        output_dir = GROQ_OUTPUT_DIR
    else:
        output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.output.strip():
        output_path = Path(args.output)
    else:
        mode_slug = "" if args.response_mode == "ask" else f"_{slugify(args.response_mode)}"
        rerank_slug = "" if not args.rerank_strategy else f"_{rerank_strategy_slug}"
        retrieval_slug = "" if not args.retrieval_mode else f"_{retrieval_mode_slug}"
        output_path = (
            output_dir
            / f"chat-latency_{slugify(args.provider)}{rerank_slug}{retrieval_slug}{mode_slug}_{timestamp}.json"
        )

    if args.report_output.strip():
        report_output_path = Path(args.report_output)
    else:
        report_output_path = output_path.with_suffix(".md")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report_output_path.write_text(build_report_markdown(report), encoding="utf-8")

    print(f"Saved JSON results to: {output_path}")
    print(f"Saved Markdown report to: {report_output_path}")


if __name__ == "__main__":
    asyncio.run(main())
