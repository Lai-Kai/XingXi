"use client";

import { FlaskConical, ShieldCheck } from "lucide-react";

import { AgentEvaluations } from "@/components/workspace/agent-evaluations";
import {
  BusinessEmptyState,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasCapability } from "@/core/auth/permissions";

export default function EvaluationsPage() {
  const { user } = useAuth();
  const allowed = hasCapability(user, "governance:read");
  return (
    <main className="size-full overflow-y-auto bg-[#f7fafb] text-[#202b2e]">
      <BusinessMobileHeader title="Agent 评测" />
      <div className="mx-auto min-h-full max-w-[1500px] px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <BusinessPageHeader
          title="星羲 Agent 自动评测"
          description="自动测试、运行轨迹与证据核对，保留每一次判定与复核"
          icon={FlaskConical}
        />
        <div className="mt-6">
          {allowed ? (
            <AgentEvaluations canExecute={user?.system_role === "admin"} />
          ) : (
            <BusinessEmptyState
              icon={ShieldCheck}
              title="无 Agent 评测查看权限"
              description="评测记录仅对具有治理读取权限的用户开放。"
            />
          )}
        </div>
      </div>
    </main>
  );
}
