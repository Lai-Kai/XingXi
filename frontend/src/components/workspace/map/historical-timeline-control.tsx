import { ChevronLeft, ChevronRight } from "lucide-react";

import { BusinessButton } from "../business-controls";

export function HistoricalTimelineControl({
  min,
  max,
  year,
  onChange,
  onClear,
  onPrevious,
  onNext,
}: {
  min: number;
  max: number;
  year: number | null;
  onChange: (year: number) => void;
  onClear: () => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="border-t px-3 py-2 sm:px-4">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <label
          htmlFor="historical-year-range"
          className="text-muted-foreground"
        >
          按纪年查阅
        </label>
        <output
          htmlFor="historical-year-range"
          className="text-primary font-medium tabular-nums"
        >
          {year === null ? "全部年代" : `${year} 年`}
        </output>
      </div>
      <div className="flex items-center gap-2">
        <BusinessButton
          variant="ghost"
          size="icon"
          className="size-10 shrink-0"
          aria-label="上一个历史事件"
          onClick={onPrevious}
        >
          <ChevronLeft className="size-4" />
        </BusinessButton>
        <input
          id="historical-year-range"
          type="range"
          min={min}
          max={max}
          step={1}
          value={year ?? min}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label="历史纪年"
          aria-valuetext={year === null ? "全部年代" : `${year}年`}
          className="research-year-range accent-primary h-11 min-w-0 flex-1 cursor-pointer"
        />
        <BusinessButton
          variant="ghost"
          size="icon"
          className="size-10 shrink-0"
          aria-label="下一个历史事件"
          onClick={onNext}
        >
          <ChevronRight className="size-4" />
        </BusinessButton>
        <BusinessButton variant="outline" size="sm" onClick={onClear}>
          全部年代
        </BusinessButton>
      </div>
      <div className="text-muted-foreground flex justify-between px-12 text-[10px] tabular-nums">
        <span>{min} 年</span>
        <span>{max} 年</span>
      </div>
    </div>
  );
}
