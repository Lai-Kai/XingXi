"use client";

import { ArrowLeft, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";

export default function ChatError({ reset }: { reset: () => void }) {
  const router = useRouter();

  return (
    <main
      className="xingxi-chat flex size-full min-h-0 items-center justify-center px-5"
      role="alert"
    >
      <div className="xingxi-panel bg-card/80 w-full max-w-md rounded-2xl border border-white/80 p-6 text-center shadow-sm">
        <h1 className="text-xl font-semibold">对话页面暂时无法加载</h1>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          当前页面发生异常。可以重试加载，或返回星羲智能体重新进入对话。
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="home-primary flex h-10 items-center gap-2 rounded-xl px-4 text-sm font-medium text-white"
          >
            <RotateCcw className="size-4" />
            重新加载
          </button>
          <button
            type="button"
            onClick={() => router.push("/workspace/agent")}
            className="bg-card flex h-10 items-center gap-2 rounded-xl border border-blue-100 px-4 text-sm font-medium text-blue-700 hover:bg-blue-50"
          >
            <ArrowLeft className="size-4" />
            返回星羲智能体
          </button>
        </div>
      </div>
    </main>
  );
}
