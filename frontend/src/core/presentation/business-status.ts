export type BusinessStatusTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger";

export type BusinessStatus =
  | "pending"
  | "running"
  | "awaiting_review"
  | "reviewed"
  | "completed"
  | "failed"
  | "cancelled"
  | "disputed"
  | "rejected"
  | "supported"
  | "insufficient"
  | "conflicting"
  | "inferred"
  | "active"
  | "archived"
  | "in_project"
  | "demo";

export type BusinessStatusPresentation = {
  label: string;
  tone: BusinessStatusTone;
};

const presentations: Record<BusinessStatus, BusinessStatusPresentation> = {
  pending: { label: "等待处理", tone: "neutral" },
  running: { label: "正在处理", tone: "info" },
  awaiting_review: { label: "等待复核", tone: "warning" },
  reviewed: { label: "已复核", tone: "success" },
  completed: { label: "已完成", tone: "success" },
  failed: { label: "处理失败", tone: "danger" },
  cancelled: { label: "已取消", tone: "neutral" },
  disputed: { label: "存在争议", tone: "warning" },
  rejected: { label: "已退回", tone: "danger" },
  supported: { label: "证据充分", tone: "success" },
  insufficient: { label: "证据不足", tone: "warning" },
  conflicting: { label: "证据冲突", tone: "danger" },
  inferred: { label: "包含推断", tone: "info" },
  active: { label: "进行中", tone: "info" },
  archived: { label: "已归档", tone: "neutral" },
  in_project: { label: "已加入项目", tone: "success" },
  demo: { label: "演示数据", tone: "warning" },
};

export function getBusinessStatusPresentation(
  status: BusinessStatus,
): BusinessStatusPresentation {
  return presentations[status];
}
