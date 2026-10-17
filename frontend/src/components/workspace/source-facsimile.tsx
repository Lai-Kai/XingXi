"use client";

import { ExternalLink } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { sourceFileContentUrl } from "@/core/source-files/api";

export function SourceFacsimile({
  documentId,
  fileId,
  fileType,
  page,
}: {
  documentId: string;
  fileId: string;
  fileType?: string;
  page: number;
}) {
  const [failed, setFailed] = useState(false);
  const url = sourceFileContentUrl(documentId, fileId);
  const image = ["PNG", "JPG", "JPEG", "WEBP"].includes(
    fileType?.toUpperCase() ?? "",
  );
  const pdf = fileType?.toUpperCase() === "PDF";
  return (
    <div className="bg-muted/40 rounded-lg border p-2">
      <div className="bg-card relative min-h-72 overflow-hidden rounded border">
        {image && !failed ? (
          <Image
            unoptimized
            src={url}
            alt="已上传的原始影像"
            width={1200}
            height={1600}
            className="h-auto w-full object-contain"
            onError={() => setFailed(true)}
          />
        ) : pdf ? (
          <iframe
            title={`原件影印 · 第 ${page} 页`}
            src={`${url}#page=${page}`}
            className="h-[48dvh] min-h-72 w-full"
          />
        ) : (
          <p className="text-muted-foreground px-4 py-12 text-sm leading-7">
            {failed ? "影像暂无法显示。" : "此文件格式请打开原件查阅。"}
            可继续核对右侧文本。
          </p>
        )}
      </div>
      <a
        href={pdf ? `${url}#page=${page}` : url}
        target="_blank"
        rel="noreferrer"
        className="text-primary mt-2 inline-flex min-h-9 items-center gap-1 text-xs underline underline-offset-4"
      >
        打开原件 · 第 {page} 页<ExternalLink className="size-3" />
      </a>
    </div>
  );
}
