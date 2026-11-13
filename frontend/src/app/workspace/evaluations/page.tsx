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
    <main className="xingxi-module bg-muted/60 text-foreground size-full overflow-y-auto">
      <BusinessMobileHeader title="问答评测" />
      <div className="mx-auto min-h-full max-w-[1500px] px-4 py-7 sm:px-8 lg:px-10 lg:py-10">
        <BusinessPageHeader
          title="星羲问答评测"
          description="自动测试、回答与出处核对，保留每一次判定与复核"
          icon={FlaskConical}
        />
        <div className="mt-6">
          {allowed ? (
            <AgentEvaluations canExecute={user?.system_role === "admin"} />
          ) : (
            <BusinessEmptyState
              icon={ShieldCheck}
              title="无问答评测查看权限"
              description="评测记录仅对具有治理读取权限的用户开放。"
            />
          )}
        </div>
      </div>
    </main>
  );
}
