import { describe, expect, it } from "@rstest/core";

import {
  mapDataNotice,
  modelErrorMessage,
  modelSourceLabel,
  reconstructionStageLabel,
} from "@/core/map/model-presentation";

describe("map model presentation", () => {
  it("uses functional progress and never echoes unknown worker phases", () => {
    expect(reconstructionStageLabel("STARTING_FLUX")).toBe("准备图片处理");
    expect(reconstructionStageLabel("preprocessing")).toBe(
      "主体提取与背景整理",
    );
    expect(reconstructionStageLabel("PrivateVendorModel-2026")).toBe(
      "正在处理",
    );
  });

  it("does not echo arbitrary implementation names or server paths from errors", () => {
    for (const value of [
      "FLUX3 / OOOSplat / ComfyUI / Tripo / DeerFlow failed",
      "PrivateVendorModel-v7 @ /data/private-project/worker.py",
      undefined,
      { detail: "PrivateVendorModel failed" },
    ]) {
      expect(modelErrorMessage(value)).toBe("处理未完成，请稍后重试。");
    }
    expect(
      modelErrorMessage(
        new Error("SparkRenderer failed"),
        "无法预览，请下载查看。",
      ),
    ).toBe("无法预览，请下载查看。");
  });

  it("keeps actionable permission and connection outcomes without technical details", () => {
    expect(modelErrorMessage("CSRF failure in Gateway")).toContain("刷新页面");
    expect(modelErrorMessage("401 from PrivateServer")).toBe(
      "请先登录后再操作。",
    );
    expect(modelErrorMessage("403: administrator permission denied")).toContain(
      "账号无权",
    );
    expect(
      modelErrorMessage("SSH host key fingerprint mismatch: PrivateServer"),
    ).toContain("暂时无法连接");
    expect(modelErrorMessage("SFTP timeout in private-project")).toContain(
      "连接暂时中断",
    );
  });

  it("retains resource and file recovery guidance without exposing backend messages", () => {
    expect(modelErrorMessage("OOOSplat CUDA out of memory")).toContain(
      "当前暂时无法处理",
    );
    expect(modelErrorMessage("ComfyUI no space left on device")).toContain(
      "存储空间不足",
    );
    expect(modelErrorMessage("FLUX3 尚未配置")).toContain("功能暂不可用");
    expect(modelErrorMessage("缺少 PLY 文件头: private-project")).toContain(
      "模型文件无法读取",
    );
    expect(modelErrorMessage("PLY 超过浏览器预览上限（256 MiB）")).toContain(
      "文件超过大小限制",
    );
    expect(modelErrorMessage("invalid GLB from PrivateModel")).toContain(
      "格式与完整性",
    );
  });

  it("retains review caveats while translating internal version terminology", () => {
    expect(
      mapDataNotice("知识版本 v3（internal）；2 个点位为待复核草稿。"),
    ).toBe("知识版本 v3（内部工作版本）；2 个点位为待复核草稿。");
    expect(mapDataNotice("当前没有 active 知识版本，地图目录为空。")).toBe(
      "当前没有正在使用的资料版本，地图目录为空。",
    );
  });

  it("distinguishes server file access from account authorization", () => {
    const failure =
      "[Errno 13] Permission denied: '/data/private/gpu_locks/allocator.lock'";
    expect(modelErrorMessage(failure)).toContain("服务端权限");
    expect(modelErrorMessage(failure)).not.toContain("账号无权");
    expect(modelErrorMessage(failure)).not.toContain("/data/");
    expect(modelErrorMessage("OSError: [Errno 13] access refused")).toContain(
      "服务端权限",
    );
    expect(modelErrorMessage("EACCES: open private file")).toContain(
      "服务端权限",
    );
  });

  it("keeps worker access errors separate from HTTP account errors", () => {
    expect(modelErrorMessage("403 Forbidden", undefined, "worker")).toContain(
      "服务端权限",
    );
    expect(modelErrorMessage("403 Forbidden")).toContain("账号无权");
  });

  it("shows provenance categories while preserving generator metadata internally", () => {
    const asset = { generator: "Tripo", provenance: "speculative" as const };
    expect(modelSourceLabel(asset)).toBe("生成示意");
    expect(asset.generator).toBe("Tripo");
    expect(modelSourceLabel({ generator: "用户接入" })).toBe("用户接入");
    expect(modelSourceLabel({ generator: "PrivateProject" })).toBe("三维素材");
    expect(modelSourceLabel({})).toBe("待确认");
  });
});
