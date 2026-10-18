"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  cancelReconstruction,
  isReconstructing,
  listReconstructions,
  reconstructionArtifact,
  reconstructionCapabilities,
  refreshReconstruction,
  uploadReconstruction,
  type Reconstruction,
  type ReconstructionCapabilities,
} from "@/core/map/reconstructions";

const PlyViewer = dynamic(() => import("./ply-viewer"), {
  ssr: false,
  loading: () => <p role="status">正在准备 PLY 预览…</p>,
});
const statuses = {
  transferring: "传送至服务器",
  running: "正在重建",
  completed: "重建完成",
  failed: "重建失败",
  cancelled: "已取消",
};
const stages: Record<string, string> = {
  starting: "启动引擎",
  preparing_frames: "准备原始图片",
  original_cameras: "原图相机重建",
  preprocessing: "FLUX3 图片预处理",
  extracting: "视频抽帧",
  frames: "视频抽帧",
  features: "特征提取",
  matching: "图像匹配",
  reconstruction: "相机重建",
  training: "高斯训练",
  brush: "高斯训练",
  completed: "已完成",
  transferring: "传送素材",
  cancelled: "已取消",
  failed: "运行失败",
};

export function ReconstructionPanel({
  pointId,
  pointName,
  onCreated,
  onCompleted,
}: {
  pointId: string;
  pointName: string;
  onCreated?: (job: Reconstruction) => void;
  onCompleted?: () => void;
}) {
  const [jobs, setJobs] = useState<Reconstruction[]>([]);
  const [limits, setLimits] = useState<ReconstructionCapabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [quality, setQuality] = useState("fast");
  const [preprocessing, setPreprocessing] = useState("none");
  const [preprocessPrompt, setPreprocessPrompt] = useState("");
  const [title, setTitle] = useState(`${pointName}影像重建`);
  const [progress, setProgress] = useState<number | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const upload = useRef<AbortController | null>(null);
  const requestId = useRef("");
  const mounted = useRef(true);
  const fileInput = useRef<HTMLInputElement>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    setLoading(true);
    void Promise.all([
      reconstructionCapabilities(controller.signal),
      listReconstructions(pointId, controller.signal),
    ])
      .then(([capabilities, list]) => {
        if (controller.signal.aborted) return;
        setLimits(capabilities);
        setJobs(list);
        setError("");
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error ? failure.message : "无法读取重建任务",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      mounted.current = false;
      controller.abort();
      upload.current?.abort();
    };
  }, [pointId, reload]);
  const replace = useCallback(
    (job: Reconstruction) =>
      setJobs((current) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]),
    [],
  );
  useEffect(() => {
    const active = jobs.filter(isReconstructing);
    if (!active.length) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void Promise.all(
        active.map((job) => refreshReconstruction(job.id, controller.signal)),
      )
        .then((updated) => {
          if (!controller.signal.aborted)
            setJobs((current) =>
              current.map(
                (job) => updated.find((value) => value.id === job.id) ?? job,
              ),
            );
          if (
            !controller.signal.aborted &&
            updated.some((job) => job.status === "completed")
          )
            onCompleted?.();
        })
        .catch((failure: unknown) => {
          if (!controller.signal.aborted) {
            setError(
              failure instanceof Error ? failure.message : "状态读取失败",
            );
            setReload((value) => value + 1);
          }
        });
    }, 4000);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [jobs, onCompleted]);

  const submit = async () => {
    if (!files.length || !limits || progress !== null) return;
    const imageCount = files.filter((file) =>
      /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(file.name),
    ).length;
    const video =
      files.length === 1 &&
      /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(files[0]!.name);
    if ((!video && imageCount !== files.length) || (!video && imageCount < 2)) {
      setError("请选择一个视频或至少两张图片，不能混合上传");
      return;
    }
    if (
      files.length > limits.max_files ||
      files.reduce((sum, file) => sum + file.size, 0) > limits.max_bytes
    ) {
      setError("素材超出服务器的文件数量或大小限制");
      return;
    }
    const form = new FormData();
    requestId.current ||= crypto.randomUUID();
    form.set("request_id", requestId.current);
    form.set("title", title.trim());
    form.set("quality", quality);
    form.set("preprocessing", preprocessing);
    if (preprocessing === "flux3" && preprocessPrompt.trim())
      form.set("preprocess_prompt", preprocessPrompt.trim());
    form.set("point_id", pointId);
    form.set("point_name", pointName);
    for (const file of files) form.append("files", file);
    const controller = new AbortController();
    upload.current = controller;
    setProgress(0);
    setError("");
    try {
      const job = await uploadReconstruction(
        form,
        controller.signal,
        setProgress,
      );
      if (!mounted.current) return;
      replace(job);
      setFiles([]);
      requestId.current = "";
      if (fileInput.current) fileInput.current.value = "";
      onCreated?.(job);
    } catch (failure) {
      if (mounted.current)
        setError(failure instanceof Error ? failure.message : "上传失败");
    } finally {
      if (mounted.current) setProgress(null);
    }
  };
  const cancel = async (job: Reconstruction) => {
    setCancelling(job.id);
    setError("");
    try {
      const value = await cancelReconstruction(job.id);
      if (mounted.current) replace(value);
    } catch (failure) {
      if (mounted.current)
        setError(failure instanceof Error ? failure.message : "取消失败");
    } finally {
      if (mounted.current) setCancelling(null);
    }
  };

  return (
    <section aria-label="影像重建" className="space-y-5 text-sm">
      <div>
        <h3 className="font-medium">为{pointName}重建三维场景</h3>
        <p className="text-muted-foreground mt-2 text-xs leading-5">
          上传环绕拍摄的视频或照片，使用远程 OOOSplat
          重建。结果保存为该点位的待核验素材。
        </p>
      </div>
      {loading && <p role="status">正在读取重建服务…</p>}
      {error && (
        <div
          role="alert"
          className="rounded border border-amber-300 bg-amber-50 p-3 text-amber-950"
        >
          {error}
          <Button
            variant="ghost"
            className="mt-2 min-h-11"
            onClick={() => setReload((value) => value + 1)}
          >
            重新连接
          </Button>
        </div>
      )}
      {limits && !limits.enabled && (
        <p className="bg-muted rounded p-3">
          远程连接尚未配置，请在 Gateway 配置 SSH 后重启服务。
        </p>
      )}
      <form
        className="space-y-3 rounded-md border p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="block space-y-1">
          <span>重建名称</span>
          <Input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              requestId.current = "";
            }}
            maxLength={120}
            required
            disabled={progress !== null}
          />
        </label>
        <label className="block space-y-1">
          <span>视频或多张照片</span>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept={limits?.extensions.join(",")}
            className="block min-h-11 w-full rounded border p-2 text-xs"
            disabled={!limits?.enabled || progress !== null}
            onChange={(event) => {
              setFiles(Array.from(event.target.files ?? []));
              requestId.current = "";
              setError("");
            }}
          />
        </label>
        <p className="text-muted-foreground text-xs">
          一个视频，或 2–{limits?.max_files ?? 500} 张照片；总大小不超过{" "}
          {Math.round((limits?.max_bytes ?? 2 * 1024 ** 3) / 1024 ** 3)} GiB。
        </p>
        {!!files.length && (
          <p className="text-xs break-all">
            已选择 {files.length} 个文件 ·{" "}
            {(
              files.reduce((sum, file) => sum + file.size, 0) /
              1024 ** 2
            ).toFixed(1)}{" "}
            MiB
          </p>
        )}
        <label className="flex min-h-11 items-center justify-between gap-2">
          <span>重建精度</span>
          <select
            aria-label="重建精度"
            className="bg-background min-h-11 rounded border px-3"
            value={quality}
            disabled={progress !== null}
            onChange={(event) => {
              setQuality(event.target.value);
              requestId.current = "";
            }}
          >
            <option value="fast">快速</option>
            <option value="balanced">均衡</option>
            <option value="high">精细</option>
          </select>
        </label>
        <label className="block space-y-1">
          <span>图片预处理</span>
          <select
            aria-label="图片预处理"
            className="bg-background min-h-11 w-full rounded border px-3"
            value={preprocessing}
            disabled={progress !== null}
            onChange={(event) => {
              setPreprocessing(event.target.value);
              requestId.current = "";
            }}
          >
            <option value="none">原图直接重建</option>
            <option value="flux3" disabled={!limits?.flux3_enabled}>
              FLUX3 图片编辑{limits?.flux3_enabled ? "" : "（尚未配置）"}
            </option>
          </select>
        </label>
        {preprocessing === "flux3" && (
          <label className="block space-y-1">
            <span>图片编辑提示词</span>
            <textarea
              aria-label="图片编辑提示词"
              rows={4}
              maxLength={4000}
              className="bg-background w-full rounded border p-3"
              placeholder="留空使用默认指令：保留主体与视角，整理为白色背景，去除无关遮挡。"
              value={preprocessPrompt}
              disabled={progress !== null}
              onChange={(event) => {
                setPreprocessPrompt(event.target.value);
                requestId.current = "";
              }}
            />
            <span className="text-muted-foreground block text-xs">
              编辑图用于重建，原图会保留。模型可能补画局部内容；白色背景不等于透明背景。
            </span>
          </label>
        )}
        {progress !== null && (
          <div role="status" className="space-y-2">
            <progress value={progress} max={100} className="w-full" />
            <p>
              {progress < 100
                ? `正在上传至 Gateway ${progress}%`
                : "上传完成，正在保存并启动远程任务…"}
            </p>
          </div>
        )}
        <Button
          type="submit"
          className="min-h-11 w-full"
          disabled={
            !limits?.enabled ||
            !files.length ||
            progress !== null ||
            !title.trim()
          }
        >
          上传并重建
        </Button>
      </form>
      <section aria-label="重建记录" className="space-y-3">
        <h3 className="font-medium">重建记录</h3>
        {!loading && !jobs.length && (
          <p className="text-muted-foreground text-xs">该点位暂无重建任务。</p>
        )}
        {jobs.map((job) => (
          <article key={job.id} className="space-y-3 rounded-md border p-3">
            <div className="flex items-start justify-between gap-2">
              <h4 className="min-w-0 font-medium break-all">{job.title}</h4>
              <span className="text-primary shrink-0 text-xs">
                {statuses[job.status]}
              </span>
            </div>
            <p className="text-muted-foreground text-xs">
              {job.input_type === "video"
                ? "视频"
                : `${job.files.length} 张照片`}{" "}
              · {new Date(job.created_at).toLocaleString("zh-CN")}
            </p>
            {isReconstructing(job) && (
              <p role="status" className="text-xs">
                {job.cancel_requested
                  ? job.preprocessing === "flux3"
                    ? "正在取消；当前 FLUX3 图片完成后停止"
                    : "正在请求取消…"
                  : (stages[job.stage.toLowerCase()] ?? job.stage)}
              </p>
            )}
            {job.preprocessing === "flux3" && (
              <p className="text-muted-foreground text-xs">
                FLUX3 预处理
                {job.preprocess_progress
                  ? ` · ${job.preprocess_progress.completed}/${job.preprocess_progress.total}`
                  : " · 保留原图"}
              </p>
            )}
            {(job.error ?? job.connection_error) && (
              <p role="alert" className="text-destructive text-xs break-all">
                {job.error ?? job.connection_error}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {isReconstructing(job) && (
                <Button
                  variant="outline"
                  className="min-h-11"
                  disabled={cancelling === job.id}
                  onClick={() => void cancel(job)}
                >
                  取消重建
                </Button>
              )}
              {job.status === "completed" && job.artifact && (
                <>
                  {job.artifact.size <= 256 * 1024 ** 2 && (
                    <Button
                      className="min-h-11"
                      onClick={() =>
                        setPreview(preview === job.id ? null : job.id)
                      }
                    >
                      {preview === job.id
                        ? "关闭预览"
                        : job.artifact.kind === "point_cloud"
                          ? "查看彩色点云"
                          : "查看高斯模型"}
                    </Button>
                  )}
                  <a
                    href={reconstructionArtifact(job)}
                    className="text-primary inline-flex min-h-11 items-center px-2 underline"
                  >
                    下载 PLY
                  </a>
                </>
              )}
            </div>
            {job.artifact && (
              <p className="text-muted-foreground text-xs">
                {(
                  job.artifact.point_count ?? job.artifact.splat_count
                )?.toLocaleString() ?? "未知数量"}{" "}
                {job.artifact.kind === "point_cloud" ? "个彩色点" : "个高斯"} ·{" "}
                {(job.artifact.size / 1024 ** 2).toFixed(1)} MiB · 待实地核验
                {job.artifact.size > 256 * 1024 ** 2
                  ? "；模型较大，请下载查看"
                  : ""}
              </p>
            )}
            {preview === job.id && (
              <PlyViewer
                key={job.id}
                source={reconstructionArtifact(job)}
                title={job.title}
              />
            )}
            <details>
              <summary className="text-muted-foreground min-h-11 cursor-pointer py-3 text-xs">
                运行日志
              </summary>
              <pre className="bg-muted max-h-52 overflow-auto rounded p-2 text-[11px] break-all whitespace-pre-wrap">
                {job.log ?? "暂无日志"}
              </pre>
            </details>
          </article>
        ))}
      </section>
    </section>
  );
}
