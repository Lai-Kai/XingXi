import { fetch, readCsrfCookie } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
import { type MapPoint } from "@/core/map/types";

export type RegisteredMapModel = {
  id: string;
  point_id: string;
  entity_id: string;
  title: string;
  kind: "mesh" | "gaussian" | "point_cloud";
  format: "glb" | "ply";
  size_bytes: number;
  sha256: string;
  source: "upload" | "reconstruction";
  created_at: string;
  preview_url: string;
  download_url: string;
  point_count?: number;
  splat_count?: number;
};
const base = () => `${getBackendBaseURL()}/api/map/model-assets`;
export const modelFileUrl = (model: RegisteredMapModel, download = false) =>
  `${base()}/${encodeURIComponent(model.id)}/file${download ? "?download=true" : ""}`;
export const modelsForPoint = (
  models: RegisteredMapModel[],
  point: Pick<MapPoint, "id" | "entityId">,
) =>
  models.filter(
    (model) =>
      model.point_id === point.id && model.entity_id === point.entityId,
  );

export async function listMapModels(
  signal?: AbortSignal,
): Promise<RegisteredMapModel[]> {
  const response = await fetch(base(), { signal });
  if (!response.ok) throw new Error("暂时无法读取已接入模型");
  return response.json() as Promise<RegisteredMapModel[]>;
}

export function uploadMapModel(
  form: FormData,
  signal: AbortSignal,
  progress: (value: number) => void,
): Promise<RegisteredMapModel> {
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
    request.onerror = () => reject(new Error("模型上传连接中断，可重试接入"));
    request.onabort = () =>
      reject(new DOMException("上传已中止", "AbortError"));
    request.onload = () => {
      try {
        const value = JSON.parse(request.responseText) as RegisteredMapModel & {
          detail?: unknown;
        };
        if (request.status >= 200 && request.status < 300) resolve(value);
        else
          reject(
            new Error(
              typeof value.detail === "string"
                ? value.detail
                : `模型接入失败 (${request.status})`,
            ),
          );
      } catch {
        reject(new Error("模型接入接口返回无效响应"));
      }
    };
    if (signal.aborted) {
      reject(new DOMException("上传已中止", "AbortError"));
      return;
    }
    request.send(form);
  });
}
