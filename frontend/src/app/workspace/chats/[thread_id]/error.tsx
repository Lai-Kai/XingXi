"use client";

import { ArrowLeft, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";

export default function ChatError({ reset }: { reset: () => void }) {
  const router = useRouter();

  return (
    <main
      className="flex size-full min-h-0 items-center justify-center bg-[#edf4f5] px-5 text-[#202b2e]"
      role="alert"
    >
      <div className="w-full max-w-md text-center">
        <h1 className="text-xl font-semibold">对话页面暂时无法加载</h1>
        <p className="mt-3 text-sm leading-6 text-[#61757a]">
          当前页面发生异常。可以重试加载，或返回星羲智能体重新选择研究模式。
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="flex h-10 items-center gap-2 rounded-md bg-[#202b2e] px-4 text-sm font-medium text-white hover:bg-[#344145]"
          >
            <RotateCcw className="size-4" />
            重新加载
          </button>
          <button
            type="button"
            onClick={() => router.push("/workspace/agent")}
            className="flex h-10 items-center gap-2 rounded-md border border-[#c7d7da] bg-white px-4 text-sm font-medium text-[#285f68] hover:bg-[#f7fbfb]"
          >
            <ArrowLeft className="size-4" />
            返回模式选择
          </button>
        </div>
      </div>
    </main>
  );
}
