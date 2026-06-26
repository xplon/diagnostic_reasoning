from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECONSTRUCTION = ROOT.parent / "data_private" / "diagnostic_reasoning" / "reviewed_v0" / "doctor_reasoning_reconstructions.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "outputs" / "live_llm_doctor_reasoning_report.md"
DEFAULT_JSON_OUTPUT = ROOT / "outputs" / "live_llm_doctor_reasoning_report.json"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def redact_secrets(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_\-\*]{4,}", "sk-***REDACTED***", text)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _short_fact(fact: dict[str, Any]) -> str:
    analyte = fact.get("analyte")
    value = fact.get("value")
    unit = fact.get("unit") or ""
    flag = fact.get("flag") or fact.get("vs_ref")
    role = fact.get("role")
    grade = fact.get("grade")
    parts = [str(analyte), f"{value} {unit}".strip(), f"flag={flag}"]
    if grade:
        parts.append(f"grade={grade}")
    if role:
        parts.append(f"role={role}")
    return ", ".join(parts)


def _short_trend(trend: dict[str, Any]) -> str:
    analyte = trend.get("analyte")
    prev = trend.get("previous_value") or trend.get("from")
    current = trend.get("current_value") or trend.get("to")
    direction = trend.get("direction")
    verdict = trend.get("verdict")
    delta_pct = trend.get("delta_pct")
    return f"{analyte}: {prev} -> {current}, {direction}, {verdict}, delta_pct={delta_pct}"


def _short_text_items(items: list[dict[str, Any]], key: str = "text") -> list[str]:
    output = []
    for item in items:
        text = item.get(key) or item.get("why_it_matters") or item.get("missing") or str(item)
        output.append(str(text))
    return output


def compact_reconstruction(data: dict[str, Any], limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    reconstructions = _as_list(data.get("reconstructions"))
    if offset:
        reconstructions = reconstructions[offset:]
    if limit is not None:
        reconstructions = reconstructions[:limit]

    cases = []
    for item in reconstructions:
        cases.append(
            {
                "case_id": item.get("case_id"),
                "report_scope": item.get("report_scope"),
                "report_domain": item.get("report_domain"),
                "evaluation_eligible": item.get("evaluation_eligible"),
                "doctor_statement": item.get("doctor_statement"),
                "gold_actions": item.get("gold_actions", []),
                "supporting_facts": [_short_fact(fact) for fact in _as_list(item.get("supporting_facts"))],
                "supporting_trends": [_short_trend(trend) for trend in _as_list(item.get("supporting_trends"))],
                "doctor_stated_unverified_trends": _short_text_items(_as_list(item.get("doctor_stated_unverified_trends"))),
                "exclusions": _short_text_items(_as_list(item.get("exclusions"))),
                "safety_gaps": [
                    f"{gap.get('missing')}: {gap.get('why_it_matters')}"
                    for gap in _as_list(item.get("safety_gaps"))
                ],
                "baseline_alignment": item.get("agreement_with_baseline"),
                "scope_notes": item.get("scope_notes"),
            }
        )
    return {"summary": data.get("summary", {}), "cases": cases}


def build_prompt(compact_data: dict[str, Any]) -> str:
    payload = json.dumps(compact_data, ensure_ascii=False, indent=2)
    return f"""你现在是给肿瘤科医生做病例推理复核的医学检验单推理助手。

下面是一个项目对每条医生判定结果生成的结构化证据。请只基于这些证据，输出一份可以给老师和医生看的中文 Markdown 报告。

重要约束：
1. 这不是患者端建议，不要写“患者应该自行用药/打针/停药”等指令。
2. 不要新增检验单里没有的事实，不要假装知道治疗方案、发热、出血等缺失上下文。
3. 医生原话里的药物、针剂、剂量只能作为“医生原话证据”保留，不能总结成通用处方规则。
4. 对每个 case 只关注“医生这个判定为什么可能成立”的推理逻辑链。
5. 如果链条证据不足，要明确写“需要医生复核”，不要硬凑结论。

报告格式必须包含：

# 真实 LLM 医生判定推理链报告

## 总览
- 本次覆盖多少条医生判定
- CBC 范围内多少条，非 CBC/当前域外多少条
- baseline 与医生 gold 的一致情况
- 最需要医生复核的共性问题

## 逐条判定推理链
对每个 case 使用下面格式：

### case_id
- 医生判定：
- gold action：
- 推理逻辑链：
  1. 检验事实：
  2. 趋势/上下文：
  3. 为什么支持医生判定：
  4. 为什么没有推出其它动作或需要排除：
  5. 安全缺口/需要追问：
- 链条质量：强 / 中 / 弱
- 给医生复核的问题：

## 总体评价
- 哪些推理链已经比较清楚
- 哪些推理链目前最弱
- 下一轮数据或规则最应该补什么

结构化证据如下：

```json
{payload}
```
"""


def extract_text(response: dict[str, Any]) -> str:
    if "choices" in response:
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(part.get("text") or part) for part in content)

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


def _request_json(url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 diagnostic-reasoning-local-test",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def call_responses_api(base_url: str, api_key: str, model: str, prompt: str, max_output_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "你是严谨的医学检验单推理链评审助手，只输出医生审核用途的中文报告。",
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": max_output_tokens,
    }
    return _request_json(base_url.rstrip("/") + "/responses", api_key, payload, timeout)


def call_chat_api(base_url: str, api_key: str, model: str, prompt: str, max_output_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是严谨的医学检验单推理链评审助手，只输出医生审核用途的中文报告。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_output_tokens,
    }
    return _request_json(base_url.rstrip("/") + "/chat/completions", api_key, payload, timeout)


def call_llm(
    api_mode: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    mode = api_mode.lower()
    if mode == "responses":
        return "responses", call_responses_api(base_url, api_key, model, prompt, max_output_tokens, timeout)
    if mode == "chat":
        return "chat", call_chat_api(base_url, api_key, model, prompt, max_output_tokens, timeout)
    if mode != "auto":
        raise ValueError(f"Unsupported OPENAI_API_MODE: {api_mode}")

    try:
        return "responses", call_responses_api(base_url, api_key, model, prompt, max_output_tokens, timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code not in {400, 404, 405}:
            raise RuntimeError(f"Responses API failed with HTTP {exc.code}: {redact_secrets(body)}") from exc
        try:
            return "chat", call_chat_api(base_url, api_key, model, prompt, max_output_tokens, timeout)
        except urllib.error.HTTPError as chat_exc:
            chat_body = chat_exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Responses API failed with HTTP {exc.code}: {redact_secrets(body)}\n"
                f"Chat Completions API failed with HTTP {chat_exc.code}: {redact_secrets(chat_body)}"
            ) from chat_exc


def main(argv: list[str] | None = None) -> int:
    load_env_file(ROOT / ".env.local")

    parser = argparse.ArgumentParser(description="Generate a real LLM doctor-facing reasoning-chain report.")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.5"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-mode", default=os.getenv("OPENAI_API_MODE", "auto"), choices=["auto", "responses", "chat"])
    parser.add_argument("--reconstruction", default=str(DEFAULT_RECONSTRUCTION))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN_OUTPUT))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=9000)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(
            "OPENAI_API_KEY is missing. Copy .env.local.example to .env.local and fill OPENAI_API_KEY, "
            "or set it as an environment variable.",
            file=sys.stderr,
        )
        return 2

    reconstruction_path = Path(args.reconstruction)
    if not reconstruction_path.exists():
        print(f"Reconstruction file not found: {reconstruction_path}", file=sys.stderr)
        return 2

    data = json.loads(reconstruction_path.read_text(encoding="utf-8"))
    compact_data = compact_reconstruction(data, limit=args.case_limit, offset=args.case_offset)
    prompt = build_prompt(compact_data)

    try:
        used_mode, response = call_llm(
            args.api_mode,
            args.base_url,
            api_key,
            args.model,
            prompt,
            args.max_output_tokens,
            args.timeout,
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Real LLM call failed with HTTP {exc.code}: {redact_secrets(body)}", file=sys.stderr)
        return 1
    except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"Real LLM call failed: {redact_secrets(str(exc))}", file=sys.stderr)
        return 1

    report_text = extract_text(response)
    if not report_text:
        print("Real LLM call returned no extractable text. Raw response will still be saved.", file=sys.stderr)

    markdown_path = Path(args.markdown_output)
    json_path = Path(args.json_output)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(report_text, encoding="utf-8", newline="\n")
    json_path.write_text(
        json.dumps(
            {
                "request": {
                    "base_url": args.base_url,
                    "model": args.model,
                    "api_mode_requested": args.api_mode,
                    "api_mode_used": used_mode,
                    "case_count": len(compact_data.get("cases", [])),
                    "prompt_chars": len(prompt),
                    "max_output_tokens": args.max_output_tokens,
                },
                "report_text": report_text,
                "raw_response": response,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(report_text)
    print(f"\nSaved Markdown report to {markdown_path}")
    print(f"Saved raw JSON response to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
