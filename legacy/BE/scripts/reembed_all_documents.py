import argparse
import json
from datetime import datetime

import httpx


def parse_document_ids(raw_value: str) -> list[int]:
    parts = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not parts:
        return []
    return [int(part) for part in parts]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-embed all or selected documents using the backend's current embedding provider.",
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
    parser.add_argument(
        "--api-prefix",
        default="",
        help="Optional API prefix. Leave empty for this project.",
    )
    parser.add_argument(
        "--document-ids",
        default="",
        help="Optional comma-separated document IDs to re-embed. If omitted, all documents are processed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even when chunks already have embeddings.",
    )
    args = parser.parse_args()

    api_prefix = args.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"

    base_url = f"{args.base_url.rstrip('/')}{api_prefix}"
    list_url = f"{base_url}/documents"
    requested_document_ids = parse_document_ids(args.document_ids)

    with httpx.Client(timeout=120.0) as client:
        list_response = client.get(list_url)
        list_response.raise_for_status()
        body = list_response.json()
        documents = body["documents"]

        if requested_document_ids:
            requested_id_set = set(requested_document_ids)
            documents = [document for document in documents if document["id"] in requested_id_set]

        results: list[dict[str, object]] = []
        total_documents = len(documents)

        for index, document in enumerate(documents, start=1):
            document_id = document["id"]
            filename = document["filename"]
            embed_url = f"{base_url}/documents/{document_id}/embeddings"
            if args.force:
                embed_url = f"{embed_url}?force=true"

            print(f"Re-embedding document {index}/{total_documents}: {filename} (id={document_id})")
            response = client.post(embed_url)
            response.raise_for_status()
            embed_result = response.json()
            results.append(
                {
                    "document_id": embed_result["document_id"],
                    "filename": embed_result["filename"],
                    "embedded_chunks": embed_result["embedded_chunks"],
                    "skipped_chunks": embed_result["skipped_chunks"],
                    "total_chunks": embed_result["total_chunks"],
                    "message": embed_result["message"],
                }
            )

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": base_url,
        "force": args.force,
        "requested_document_ids": requested_document_ids,
        "processed_count": len(results),
        "results": results,
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
