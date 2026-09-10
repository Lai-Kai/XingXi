import type { BusinessCapability, BusinessRole, User } from "./types";

const BUSINESS_ROLE_LABELS: Record<BusinessRole, string> = {
  public: "游客 / 公众",
  researcher: "研究人员",
  cultural_institution: "文博机构",
  government: "管理部门",
  study_team: "研学团队",
};

export function businessRoleLabel(role: BusinessRole) {
  return BUSINESS_ROLE_LABELS[role];
}

export function hasCapability(
  user:
    | (Pick<User, "system_role"> & Partial<Pick<User, "capabilities">>)
    | null
    | undefined,
  capability: BusinessCapability,
) {
  return user?.system_role === "admin" || user?.capabilities?.includes(capability) === true;
}

export function canManageSourceDocuments(
  user:
    | (Pick<User, "system_role"> & Partial<Pick<User, "capabilities">>)
    | null
    | undefined,
) {
  return hasCapability(user, "source:manage");
}
