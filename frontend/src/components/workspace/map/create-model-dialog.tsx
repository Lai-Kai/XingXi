"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ReconstructionPanel } from "@/components/workspace/map/reconstruction-panel";
import { uploadMapModel } from "@/core/map/registered-models";
import { type MapPoint } from "@/core/map/types";

export function CreateModelDialog({
  open,
  onOpenChange,
  points,
  defaultPointId,
  onCreated,
  onCreatePoint,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  points: MapPoint[];
  defaultPointId?: string;
  onCreated: (pointId: string, mode: "import" | "rebuild") => void;
  onCreatePoint: () => void;
}) {
  const [mode, setMode] = useState<"import" | "rebuild">("rebuild");
  const [pointId, setPointId] = useState(defaultPointId ?? "");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const requestId = useRef("");
  const point = points.find((item) => item.id === pointId);
  useEffect(() => {
    if (open) {
      setPointId(defaultPointId ?? "");
      setError("");
      setFile(null);
      setTitle("");
      requestId.current = "";
    } else controller.current?.abort();
  }, [open, defaultPointId]);
  useEffect(() => () => controller.current?.abort(), []);
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!point || !file || !title.trim() || progress !== null) return;
    const request = new AbortController();
    controller.current = request;
    requestId.current ||= crypto.randomUUID();
    const form = new FormData();
    form.set("title", title.trim());
    form.set("point_id", point.id);
    form.set("request_id", requestId.current);
    form.set("file", file);
    setError("");
    setProgress(0);
    try {
      await uploadMapModel(form, request.signal, setProgress);
      if (!request.signal.aborted) {
        requestId.current = "";
        onCreated(point.id, "import");
      }
    } catch (failure) {
      if (!request.signal.aborted)
        setError(failure instanceof Error ? failure.message : "模型接入失败");
    } finally {
      setProgress(null);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (progress === null) onOpenChange(value);
      }}
    >
      <DialogContent className="flex max-h-[90dvh] w-[94vw] flex-col gap-3 p-4 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>创建模型</DialogTitle>
          <DialogDescription>
            为地图点位上传影像重建，或接入已有三维模型。
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 space-y-4 overflow-y-auto px-1 pb-1">
          <label className="block space-y-2 text-sm">
            <span>关联地图点位</span>
            <select
              aria-label="关联地图点位"
              value={pointId}
              disabled={progress !== null}
              className="bg-background min-h-11 w-full rounded-md border px-3"
              onChange={(event) => {
                setPointId(event.target.value);
                requestId.current = "";
              }}
            >
              <option value="">请选择点位</option>
              {points.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={progress !== null}
            onClick={onCreatePoint}
          >
            创建点位
          </Button>
          <div
            role="group"
            aria-label="创建方式"
            className="grid grid-cols-2 gap-2"
          >
            <Button
              variant={mode === "rebuild" ? "default" : "outline"}
              className="min-h-11"
              aria-pressed={mode === "rebuild"}
              disabled={progress !== null}
              onClick={() => setMode("rebuild")}
            >
              上传影像重建
            </Button>
            <Button
              variant={mode === "import" ? "default" : "outline"}
              className="min-h-11"
              aria-pressed={mode === "import"}
              disabled={progress !== null}
              onClick={() => setMode("import")}
            >
              接入已有模型
            </Button>
          </div>
          {!point ? (
            <p
              role="status"
              className="text-muted-foreground rounded border border-dashed p-4 text-sm"
            >
              选择点位后即可创建模型。
            </p>
          ) : mode === "rebuild" ? (
            <ReconstructionPanel
              key={point.id}
              pointId={point.id}
              pointName={point.name}
              onCreated={() => onCreated(point.id, "rebuild")}
            />
          ) : (
            <form
              onSubmit={(event) => void create(event)}
              className="space-y-4"
            >
              <label className="block space-y-2 text-sm">
                <span>模型名称</span>
                <Input
                  required
                  maxLength={120}
                  value={title}
                  disabled={progress !== null}
                  placeholder={`${point.name} · 三维模型`}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    requestId.current = "";
                  }}
                />
              </label>
              <label className="block space-y-2 text-sm">
                <span>PLY 或 GLB 模型文件</span>
                <input
                  type="file"
                  accept=".ply,.glb"
                  disabled={progress !== null}
                  className="block min-h-11 w-full min-w-0 rounded border p-2 text-xs"
                  onChange={(event) => {
                    const selected = event.target.files?.[0] ?? null;
                    setFile(null);
                    requestId.current = "";
                    setError("");
                    if (
                      selected &&
                      (!/\.(ply|glb)$/i.test(selected.name) ||
                        !selected.size ||
                        selected.size > 256 * 1024 ** 2)
                    ) {
                      setError("请选择非空且不超过 256 MiB 的 PLY 或 GLB 文件");
                      return;
                    }
                    setFile(selected);
                  }}
                />
              </label>
              <p className="text-muted-foreground text-xs leading-5">
                支持彩色点云、高斯 PLY 和内嵌贴图的 GLB，最多 256
                MiB。接入后保存到该点位，刷新页面仍可查看。
              </p>
              {error && (
                <p
                  role="alert"
                  className="text-destructive rounded border p-3 text-sm"
                >
                  {error}
                </p>
              )}
              {progress !== null && (
                <div role="status" className="space-y-2">
                  <progress className="w-full" max="100" value={progress} />
                  <p className="text-xs">
                    {progress < 100
                      ? `正在上传模型 ${progress}%`
                      : "正在保存模型…"}
                  </p>
                </div>
              )}
              <Button
                type="submit"
                className="min-h-11 w-full"
                disabled={!file || !title.trim() || progress !== null}
              >
                {progress === null ? "保存并接入地图" : "正在接入…"}
              </Button>
              {progress !== null && (
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 w-full"
                  onClick={() => {
                    controller.current?.abort();
                    setProgress(null);
                    setError("上传已取消，可使用相同文件重试");
                  }}
                >
                  取消上传
                </Button>
              )}
            </form>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
