import { fetch, readCsrfCookie } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type Reconstruction = {
  id: string;
  title: string;
  point_id: string | null;
  point_name: string | null;
  input_type: "video" | "images";
  quality: "fast" | "balanced" | "high";
  status: "transferring" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  preprocessing?: "none" | "flux3";
  pipeline_profile?: string;
  preprocess_progress?: { completed: number; total: number };
  created_at: string;
  log?: string;
  error?: string | null;
  connection_error?: string | null;
  cancel_requested?: boolean;
  files: { name: string; size: number }[];
  artifact?: {
    size: number;
    sha256: string;
    kind?: "gaussian" | "point_cloud";
    splat_count?: number;
    point_count?: number;
  };
  artifact_url?: string;
};
export type ReconstructionCapabilities = {
  enabled: boolean;
  flux3_enabled?: boolean;
  max_bytes: number;
  max_files: number;
  extensions: string[];
};
const base = () => `${getBackendBaseURL()}/api/reconstructions`;
export const reconstructionArtifact = (job: Reconstruction) =>
  `${base()}/${encodeURIComponent(job.id)}/artifact/final.ply`;
export const isReconstructing = (job: Reconstruction) =>
  job.status === "transferring" || job.status === "running";

async function result<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const value = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : `请求失败 (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}
export const reconstructionCapabilities = (signal?: AbortSignal) =>
  fetch(`${base()}/capabilities`, { signal }).then(
    result<ReconstructionCapabilities>,
  );
export const listReconstructions = (pointId: string, signal?: AbortSignal) =>
  fetch(`${base()}?${new URLSearchParams({ point_id: pointId })}`, {
    signal,
  }).then(result<Reconstruction[]>);
export const refreshReconstruction = (id: string, signal?: AbortSignal) =>
  fetch(`${base()}/${encodeURIComponent(id)}`, { signal }).then(
    result<Reconstruction>,
  );
export const cancelReconstruction = (id: string) =>
  fetch(`${base()}/${encodeURIComponent(id)}/cancel`, { method: "POST" }).then(
    result<Reconstruction>,
  );

export function uploadReconstruction(
  form: FormData,
  signal: AbortSignal,
  progress: (percent: number) => void,
): Promise<Reconstruction> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", base());
    request.withCredentials = true;
    const csrf = readCsrfCookie();
    if (csrf) request.setRequestHeader("X-CSRF-Token", csrf);
    const abort = () => request.abort();
    signal.addEventListener("abort", abort, { once: true });
    request.onloadend = () => signal.removeEventListener("abort", abort);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        progress(Math.round((event.loaded / event.total) * 100));
    };
    request.onerror = () => reject(new Error("上传连接中断；可用相同素材重试"));
    request.onabort = () =>
      reject(new DOMException("上传已中止", "AbortError"));
    request.onload = () => {
      try {
        const value = JSON.parse(request.responseText) as Reconstruction & {
          detail?: unknown;
        };
        if (request.status >= 200 && request.status < 300) resolve(value);
        else
          reject(
            new Error(
              typeof value.detail === "string"
                ? value.detail
                : `上传失败 (${request.status})`,
            ),
          );
      } catch {
        reject(new Error("服务器返回无效响应"));
      }
    };
    if (signal.aborted) {
      reject(new DOMException("上传已中止", "AbortError"));
      return;
    }
    request.send(form);
  });
}
