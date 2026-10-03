"use client";

import { CheckCircle2, ChartNoAxesCombined } from "lucide-react";
import { useState } from "react";

import {
  evaluationDistribution,
  historyPoints,
} from "@/core/operations/evaluation-dashboard";
import {
  evaluationLabel,
  type AgentEvaluation,
  type AgentEvaluationSummary,
} from "@/core/operations/evaluations";

const card =
  "min-w-0 rounded-xl border border-[#dce5e6] bg-white p-5 shadow-sm";

export function EvaluationHistoryChart({
  batches,
  selectedId,
  onSelect,
}: {
  batches: AgentEvaluationSummary[];
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const points = historyPoints(batches);
  const hovered = points.find((item) => item.id === hoveredId);
  const maxCount = Math.max(1, ...points.map((item) => item.planned));
  const plot = { x: 42, y: 20, width: 628, height: 180 };
  const slot = plot.width / Math.max(points.length, 1);
  const x = (index: number) => plot.x + slot * (index + 0.5);
  const rateY = (rate: number) => plot.y + plot.height * (1 - rate / 100);
  let line = "";
  points.forEach((point, index) => {
    if (point.rate == null) return;
    line += `${index > 0 && points[index - 1]?.rate != null ? "L" : "M"}${x(index)},${rateY(point.rate)} `;
  });

  return (
    <section className={card} aria-label="历史批次图表">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">批次稳定性趋势</h3>
          <p className="mt-1 text-xs text-slate-500">
            当前历史页 · {batches.length} 个批次 · 点击图形切换批次
          </p>
        </div>
        <div className="flex gap-3 text-xs text-slate-500">
          <span>▰ 计划数</span>
          <span className="text-[#276f79]">▰ 通过数</span>
          <span className="text-emerald-700">● 通过率</span>
        </div>
      </div>
      {points.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 text-sm text-slate-500">
          <ChartNoAxesCombined className="size-8 text-slate-300" />
          暂无历史批次
        </div>
      ) : (
        <div className="relative mt-4">
          <svg
            viewBox="0 0 720 244"
            className="w-full"
            role="img"
            aria-label="左轴计划与通过数量，右轴规则通过率"
          >
            {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
              <g key={fraction}>
                <line
                  x1={plot.x}
                  x2={plot.x + plot.width}
                  y1={plot.y + plot.height * fraction}
                  y2={plot.y + plot.height * fraction}
                  stroke="#e8eef0"
                  strokeDasharray="3 4"
                />
                <text
                  x={32}
                  y={plot.y + plot.height * fraction + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="#64748b"
                >
                  {Number((maxCount * (1 - fraction)).toFixed(1))}
                </text>
                <text
                  x={682}
                  y={plot.y + plot.height * fraction + 4}
                  fontSize="10"
                  fill="#64748b"
                >
                  {100 * (1 - fraction)}%
                </text>
              </g>
            ))}
            {points.map((point, index) => {
              const width = Math.min(22, slot * 0.55);
              const base = plot.y + plot.height;
              return (
                <g key={point.id}>
                  <rect
                    x={x(index) - width / 2}
                    y={base - (point.planned / maxCount) * plot.height}
                    width={width}
                    height={(point.planned / maxCount) * plot.height}
                    rx="3"
                    fill="#e2e8f0"
                  />
                  <rect
                    x={x(index) - width / 2}
                    y={base - (point.passed / maxCount) * plot.height}
                    width={width}
                    height={(point.passed / maxCount) * plot.height}
                    rx="3"
                    fill="#276f79"
                  />
                  {index % Math.ceil(points.length / 7) === 0 && (
                    <text
                      x={x(index)}
                      y={223}
                      textAnchor="middle"
                      fontSize="10"
                      fill="#64748b"
                    >
                      {point.label}
                    </text>
                  )}
                </g>
              );
            })}
            <path d={line} fill="none" stroke="#059669" strokeWidth="2.5" />
            {points.map((point, index) => (
              <g key={point.id}>
                {point.rate != null && (
                  <circle
                    cx={x(index)}
                    cy={rateY(point.rate)}
                    r="4"
                    fill="#fff"
                    stroke="#059669"
                    strokeWidth="2"
                  />
                )}
                <rect
                  x={plot.x + slot * index + 1}
                  y={12}
                  width={Math.max(1, slot - 2)}
                  height={192}
                  rx="4"
                  fill="transparent"
                  stroke={point.id === selectedId ? "#276f79" : "transparent"}
                  strokeDasharray="3 3"
                  tabIndex={0}
                  role="button"
                  className="cursor-pointer outline-[#276f79]"
                  aria-label={`查看批次 ${point.id}`}
                  onMouseEnter={() => setHoveredId(point.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onFocus={() => setHoveredId(point.id)}
                  onBlur={() => setHoveredId(null)}
                  onClick={() => onSelect(point.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(point.id);
                    }
                  }}
                />
              </g>
            ))}
          </svg>
          {hovered && (
            <div
              role="tooltip"
              className="pointer-events-none absolute top-2 left-8 max-w-[85%] rounded-lg border bg-white/95 p-3 text-xs shadow-md"
            >
              <p className="truncate font-mono font-medium">{hovered.id}</p>
              <p className="mt-1 text-slate-500">
                {new Date(hovered.createdAt).toLocaleString()}
              </p>
              <p className="mt-2">
                计划 {hovered.planned} · 通过 {hovered.passed} ·{" "}
                {evaluationLabel(hovered.status)}
              </p>
              <p className="mt-1">
                规则通过率：
                {hovered.rate == null
                  ? "未完成 / 未采集"
                  : `${hovered.rate.toFixed(1)}%`}
              </p>
            </div>
          )}
        </div>
      )}
      <p className="text-xs leading-5 text-slate-500">
        {points.length === 1
          ? "仅有一个批次，暂无足够历史数据观察趋势。"
          : "各批次独立统计；用例和版本可能不同，未作同条件版本比较。"}
        进行中批次不绘制最终通过率。
      </p>
    </section>
  );
}

export function EvaluationDistributionChart({
  batch,
}: {
  batch?: AgentEvaluation;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const distribution = evaluationDistribution(batch);
  const total = distribution.reduce((sum, item) => sum + item.value, 0);
  const circumference = 2 * Math.PI * 70;
  let consumed = 0;
  const segments = distribution.map((item) => {
    const offset = consumed;
    consumed += (item.value / total) * circumference;
    return { ...item, offset, length: (item.value / total) * circumference };
  });
  const tooltip = segments.find((item) => item.key === hovered);
  return (
    <section className={card} aria-label="未通过项分布">
      <h3 className="font-semibold">未通过项与未完成项</h3>
      <p className="mt-1 text-xs text-slate-500">
        当前批次 · 按执行状态或规则判定分类
      </p>
      {total === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 text-sm text-slate-500">
          {batch && batch.total > 0 ? (
            <>
              <CheckCircle2 className="size-9 text-emerald-500" />
              本批次没有未通过项
            </>
          ) : (
            "暂无可统计记录"
          )}
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-3">
          <div className="relative w-48 shrink-0">
            <svg
              viewBox="0 0 200 200"
              className="w-full"
              role="img"
              aria-label={`未通过或未完成共 ${total} 项`}
            >
              {segments.map((item) => (
                <circle
                  key={item.key}
                  cx="100"
                  cy="100"
                  r="70"
                  fill="none"
                  stroke={item.color}
                  strokeWidth={hovered === item.key ? 25 : 21}
                  strokeDasharray={`${item.length} ${circumference - item.length}`}
                  strokeDashoffset={-item.offset}
                  transform="rotate(-90 100 100)"
                  tabIndex={0}
                  onMouseEnter={() => setHovered(item.key)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(item.key)}
                  onBlur={() => setHovered(null)}
                >
                  <title>
                    {item.label}：{item.value} 项（
                    {((item.value / total) * 100).toFixed(1)}%）
                  </title>
                </circle>
              ))}
              <text
                x="100"
                y="100"
                textAnchor="middle"
                fontSize="30"
                fontWeight="600"
                fill="#202b2e"
              >
                {total}
              </text>
              <text
                x="100"
                y="122"
                textAnchor="middle"
                fontSize="11"
                fill="#64748b"
              >
                未通过 / 未完成
              </text>
            </svg>
            {tooltip && (
              <div
                role="tooltip"
                className="pointer-events-none absolute inset-x-0 bottom-0 rounded-md border bg-white px-2 py-1 text-center text-xs shadow-sm"
              >
                {tooltip.label} · {tooltip.value} 项 ·{" "}
                {((tooltip.value / total) * 100).toFixed(1)}%
              </div>
            )}
          </div>
          <ul className="min-w-36 flex-1 space-y-3 text-xs">
            {distribution.map((item) => (
              <li
                key={item.key}
                className="flex items-center justify-between gap-2"
              >
                <span className="flex items-center gap-2">
                  <span
                    className="size-2 rounded-full"
                    style={{ backgroundColor: item.color }}
                  />
                  {item.label}
                </span>
                <span className="font-mono">
                  {item.value} · {((item.value / total) * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs leading-5 text-slate-500">
        分布用于定位待处理记录，不推断失败根因。预期内的超时或取消按规则判定统计。
      </p>
    </section>
  );
}
