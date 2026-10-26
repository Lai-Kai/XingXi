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

export type MapModelsPage = {
  data: RegisteredMapModel[];
  next_cursor: string | null;
};

export async function listMapModelsPage({
  signal,
  pointId,
  cursor,
  limit = 100,
}: {
  signal?: AbortSignal;
  pointId?: string;
  cursor?: string;
  limit?: number;
} = {}): Promise<MapModelsPage> {
  signal?.throwIfAborted();
  const query = new URLSearchParams({ limit: String(limit) });
  if (pointId !== undefined) query.set("point_id", pointId);
  if (cursor !== undefined) query.set("cursor", cursor);
  const response = await fetch(`${base()}/page?${query.toString()}`, {
    signal,
  });
  if (!response.ok) throw new Error("暂时无法读取已接入模型");
  const value = (await response.json()) as Partial<MapModelsPage> | null;
  if (
    !value ||
    !Array.isArray(value.data) ||
    (value.next_cursor !== null &&
      (typeof value.next_cursor !== "string" || !value.next_cursor))
  ) {
    throw new Error("模型分页接口返回无效响应");
  }
  signal?.throwIfAborted();
  return value as MapModelsPage;
}

export async function listMapModels(
  signal?: AbortSignal,
  pointId?: string,
): Promise<RegisteredMapModel[]> {
  const models = new Map<string, RegisteredMapModel>();
  const cursors = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await listMapModelsPage({ signal, pointId, cursor });
    for (const model of page.data) models.set(model.id, model);
    if (page.next_cursor === null) return [...models.values()];
    if (cursors.has(page.next_cursor)) {
      throw new Error("模型分页游标重复，请刷新后重试");
    }
    cursors.add(page.next_cursor);
    cursor = page.next_cursor;
  } while (cursor);
  return [...models.values()];
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
