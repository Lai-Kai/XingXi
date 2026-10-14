"""Portable, escaped reports generated only from persisted observations."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from pathlib import Path
from typing import Literal

ReportFormat = Literal["json", "csv", "markdown", "html"]


def _cell(value: object) -> str:
    value = str(value if value is not None else "未采集")
    return html.escape(value).replace("|", "\\|").replace("\n", "<br>")


def export_report(report: dict, format: ReportFormat) -> str:
    if format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["case_id", "title", "status", "verdict", "elapsed_ms", "answer", "error"])
        for result in report.get("results", []):
            row = [result.get("case_id"), result.get("case", {}).get("title"), result.get("status"), result.get("verdict"), result.get("elapsed_ms"), result.get("answer"), result.get("error")]
            writer.writerow([("'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value) for value in row])
        return buffer.getvalue()
    summary = [
        f"# 星羲 Agent 评测：{_cell(report.get('id'))}",
        "",
        "执行方式：固定模型回放；通过真实 Gateway 与星羲 Graph。仅使用合成测试资料。",
        "",
        f"状态：{_cell(report.get('status'))}；计划：{report.get('total', 0)}；通过：{report.get('passed', 0)}。",
        "",
        "| 用例 | 结果 | 耗时 ms | 错误 |",
        "| --- | --- | --- | --- |",
    ]
    for result in report.get("results", []):
        summary.append("| " + " | ".join(_cell(item) for item in [result.get("case", {}).get("title", result.get("case_id")), result.get("verdict") or result.get("status"), result.get("elapsed_ms"), result.get("error", "")]) + " |")
    summary.extend(["", "## 环境与版本", "", "```json", json.dumps(report.get("environment", {}), ensure_ascii=False, indent=2, default=str).replace("```", "\\`\\`\\`"), "```"])
    for result in report.get("results", []):
        summary.extend(
            [
                "",
                f"## {_cell(result.get('case_id'))}",
                "",
                f"问题：{_cell(result.get('case', {}).get('question', ''))}",
                "",
                f"回答：{_cell(result.get('answer', ''))}",
                "",
                f"运行 ID：{_cell(result.get('agent_run_id'))}",
                "",
                "| 检查 | 结果 | 期望 | 实际 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for check in result.get("checks", []):
            summary.append("| " + " | ".join(_cell(check.get(key)) for key in ("label", "status", "expected", "actual")) + " |")
        summary.extend(["", "### 引用证据", ""])
        for item in result.get("evidence", []):
            summary.append(
                f"- {_cell(item.get('document_title'))}，第 {_cell(item.get('page_start'))} 页；Evidence `{_cell(item.get('evidence_id'))}`；核对：{item.get('verified')}。原文：{_cell(item.get('stored_quote', item.get('quote')))}"
            )
        summary.extend(["", "### 执行时间线", ""])
        for event in result.get("events", []):
            summary.append(f"- {_cell(event.get('at'))} · {_cell(event.get('type'))} · {_cell(event.get('name', ''))}")
        for review in report.get("reviews", []):
            if review.get("case_id") == result.get("case_id"):
                summary.append(f"- 人工复核：{_cell(review.get('decision'))}；{_cell(review.get('note'))}；{_cell(review.get('actor_id'))}；{_cell(review.get('created_at'))}")
    if format == "markdown":
        return "\n".join(summary) + "\n"
    if format != "html":
        raise ValueError("Unknown report format")
    cards = []

    def escaped(value):
        return html.escape(str(value if value is not None else "未采集"))

    for result in report.get("results", []):
        state = result.get("verdict") or result.get("status", "error")
        case = result.get("case", {})
        checks = "".join("<tr>" + "".join(f"<td>{escaped(check.get(key))}</td>" for key in ("label", "status", "expected", "actual")) + "</tr>" for check in result.get("checks", []))
        evidence = "".join(
            f"<blockquote><b>{escaped(item.get('document_title'))} · 第 {escaped(item.get('page_start'))} 页 · 核对 {escaped(item.get('verified'))}</b>"
            f"<p>{escaped(item.get('stored_quote', item.get('quote')))}</p><small>Evidence {escaped(item.get('evidence_id'))}<br>Release {escaped(item.get('release_id'))}</small></blockquote>"
            for item in result.get("evidence", [])
        )
        events = "".join(
            f"<li><details><summary>{escaped(event.get('at'))} · {escaped(event.get('type'))} {escaped(event.get('name', ''))}</summary><pre>{escaped(json.dumps(event, ensure_ascii=False, indent=2))}</pre></details></li>"
            for event in result.get("events", [])
        )
        reviews = "".join(
            f"<p>{escaped(review.get('decision'))} · {escaped(review.get('note'))} · {escaped(review.get('actor_id'))} · {escaped(review.get('created_at'))}</p>"
            for review in report.get("reviews", [])
            if review.get("case_id") == result.get("case_id")
        )
        color = "#147d50" if state == "passed" else "#a33131"
        cards.append(
            f"<details><summary><b style='color:{color}'>{escaped(state)}</b> · {escaped(case.get('title', result.get('case_id')))} · {escaped(case.get('mode'))} · {escaped(result.get('elapsed_ms'))} ms</summary>"
            f"<h3>问题</h3><p>{escaped(case.get('question'))}</p><h3>实际回答</h3><pre>{escaped(result.get('answer'))}</pre>"
            f"<p>Run：{escaped(result.get('agent_run_id'))}</p><p>错误：{escaped(result.get('error', '无'))}</p>"
            f"<div class='table'><table><thead><tr><th>检查</th><th>结果</th><th>期望</th><th>实际</th></tr></thead><tbody>{checks}</tbody></table></div>"
            f"<h3>引用证据</h3>{evidence or '<p>无证据记录</p>'}<h3>执行时间线</h3><ol>{events}</ol><h3>人工复核</h3>{reviews or '<p>尚无复核记录</p>'}</details>"
        )
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>星羲 Agent 测试报告</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;"
        "color:#203438;background:#f7fafb}details{background:white;border:1px solid #ccdadd;border-radius:8px;padding:16px;margin:12px 0}"
        "summary{cursor:pointer}pre,td,small{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccdadd;padding:8px;text-align:left}.table{overflow-x:auto}blockquote{border-left:3px solid #147d50;padding-left:16px}"
        "</style><h1>星羲 Agent 测试报告</h1><p>固定模型回放 · 真实 Gateway · 合成测试资料</p><p>验证软件流程，不代表真实模型回答质量。展开用例查看实际记录。</p><p>"
        + html.escape(f"批次 {report.get('id')} · 状态 {report.get('status')} · 通过 {report.get('passed', 0)}/{report.get('total', 0)}")
        + "</p>"
        + "".join(cards)
        + "<details><summary>执行环境与版本</summary><pre>"
        + escaped(json.dumps(report.get("environment", {}), ensure_ascii=False, indent=2))
        + "</pre></details>"
        + "</html>"
    )


def write_report(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for name, format in [("summary.md", "markdown"), ("results.json", "json"), ("results.csv", "csv"), ("index.html", "html")]:
        payload = export_report(report, format).encode("utf-8")
        (directory / name).write_bytes(payload)
        files.append({"path": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    (directory / "manifest.json").write_text(json.dumps({"batch_id": report["id"], "environment": report.get("environment", {}), "files": files}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return directory
