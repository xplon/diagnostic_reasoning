from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_RECONSTRUCTION = ROOT.parent / "data_private" / "diagnostic_reasoning" / "reviewed_v0" / "doctor_reasoning_reconstructions.json"


def _read_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return f"[missing: {path}]"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n[truncated]\n"
    return text


def _pytest_summary() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return f"exit_code={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def _reconstruction_summary(path: Path) -> str:
    if not path.exists():
        return f"[missing reconstruction file: {path}]"
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    sample = data.get("reconstructions", [])[:2]
    return json.dumps({"summary": summary, "sample_reconstructions": sample}, ensure_ascii=False, indent=2)


def build_prompt(reconstruction_path: Path, include_pytest: bool) -> str:
    sections = {
        "roadmap.md": _read_text(ROOT / "docs" / "roadmap.md"),
        "feishu_task_claims.md": _read_text(ROOT / "docs" / "feishu_task_claims.md"),
        "doctor_reasoning_reconstruction.md": _read_text(ROOT / "docs" / "doctor_reasoning_reconstruction.md"),
        "schema_spec.md": _read_text(ROOT / "docs" / "schema_spec.md"),
        "pyproject.toml": _read_text(ROOT / "pyproject.toml"),
        "reconstruction_summary": _reconstruction_summary(reconstruction_path),
    }
    if include_pytest:
        sections["pytest"] = _pytest_summary()

    context = "\n\n".join(f"## {name}\n{content}" for name, content in sections.items())
    return (
        "请作为严格的医学检验单推理项目技术评审，只基于下面给出的项目材料做真实评价。\n"
        "请用中文输出：1. 当前完成度百分比；2. 已实现功能；3. 主要缺口；"
        "4. owner/wy、lbc、未认领任务的进展；5. 是否可以上传 GitHub；"
        "6. 下一步最高优先级。\n"
        "不要假装看过未提供的代码或数据；不要给患者端医疗建议。\n\n"
        f"{context}"
    )


def extract_text(response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text") or content.get("output_text")
            if text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    if response.get("output_text"):
        return str(response["output_text"])
    return ""


def call_responses_api(base_url: str, api_key: str, model: str, prompt: str, timeout: int) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/responses"
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "你是一个严谨的项目评审和医学检验单推理系统评估助手。",
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 2200,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real OpenAI-compatible project review call.")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.5"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--reconstruction", default=str(DEFAULT_PRIVATE_RECONSTRUCTION))
    parser.add_argument("--output", default=str(ROOT / "outputs" / "live_llm_project_review.json"))
    parser.add_argument("--include-pytest", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set. Refusing to read API keys from source files or command-line arguments.", file=sys.stderr)
        return 2

    prompt = build_prompt(Path(args.reconstruction), include_pytest=args.include_pytest)
    try:
        response = call_responses_api(args.base_url, api_key, args.model, prompt, args.timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    output = {
        "request": {
            "base_url": args.base_url,
            "model": args.model,
            "prompt_chars": len(prompt),
        },
        "extracted_text": extract_text(response),
        "raw_response": response,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output["extracted_text"])
    print(f"\nSaved raw response to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
