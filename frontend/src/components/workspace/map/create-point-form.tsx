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
import { createMapPoint } from "@/core/map/api";
import { type MapPoint } from "@/core/map/types";

export type PickedLocation = { lon: number; lat: number };

export function CreatePointForm({
  location,
  onPickAgain,
  onCancel,
  onCreated,
}: {
  location: PickedLocation;
  onPickAgain: () => void;
  onCancel: () => void;
  onCreated: (point: MapPoint) => void;
}) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving || !name.trim()) return;
    const request = new AbortController();
    controller.current = request;
    requestId.current ||= crypto.randomUUID();
    setSaving(true);
    setError("");
    try {
      const point = await createMapPoint(
        { name: name.trim(), ...location, request_id: requestId.current },
        request.signal,
      );
      if (!request.signal.aborted) onCreated(point);
    } catch (failure) {
      if (!request.signal.aborted)
        setError(
          failure instanceof Error ? failure.message : "点位保存失败，请重试",
        );
    } finally {
      if (!request.signal.aborted) setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onCancel();
      }}
    >
      <DialogContent
        className="w-[94vw] sm:max-w-md"
        onEscapeKeyDown={(event) => {
          if (saving) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          if (saving) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle>创建点位</DialogTitle>
          <DialogDescription>
            为地图选中的位置输入名称，保存后可关联三维模型。
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void save(event)} className="space-y-4">
          <p className="bg-muted rounded-md p-3 text-sm" data-picked-location>
            经度 {location.lon.toFixed(6)} · 纬度 {location.lat.toFixed(6)}
          </p>
          <label className="block space-y-2 text-sm">
            <span>点位名称</span>
            <Input
              value={name}
              maxLength={120}
              required
              autoFocus
              disabled={saving}
              placeholder="例如：永安桥东侧"
              onChange={(event) => {
                setName(event.target.value);
                requestId.current = "";
                setError("");
              }}
            />
          </label>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={saving}
              className="min-h-11"
              onClick={onCancel}
            >
              取消
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              className="min-h-11"
              onClick={onPickAgain}
            >
              重新选点
            </Button>
            <Button
              type="submit"
              disabled={saving || !name.trim()}
              className="min-h-11"
            >
              {saving ? "正在保存…" : "保存点位"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
