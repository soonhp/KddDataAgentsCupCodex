#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

import requests
from huggingface_hub import get_token


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Hugging Face Inference Providers chat completions for Qwen.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-35B-A3B")
    parser.add_argument("--url", default="https://router.huggingface.co/v1/chat/completions")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN") or get_token()
    if not token:
        print("ERROR: No HF_TOKEN env var or cached Hugging Face token found.", file=sys.stderr)
        return 2

    payload = {
        "model": args.model,
        "messages": [
            {"role": "user", "content": "Return exactly this JSON and nothing else: {\"ok\":true}"}
        ],
        "temperature": 0,
        "stream": False,
    }
    response = requests.post(
        args.url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=args.timeout,
    )
    print(json.dumps({"status_code": response.status_code, "model": args.model}, indent=2))
    try:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2)[:4000])
    except Exception:
        print(response.text[:4000])
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
