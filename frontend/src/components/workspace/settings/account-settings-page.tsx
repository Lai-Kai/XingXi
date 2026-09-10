"use client";

import { LogOutIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetch, getCsrfHeaders } from "@/core/api/fetcher";
import { useAuth } from "@/core/auth/AuthProvider";
import { businessRoleLabel } from "@/core/auth/permissions";
import {
  parseAuthError,
  userSchema,
  type BusinessRole,
  type User,
} from "@/core/auth/types";
import { useI18n } from "@/core/i18n/hooks";

import { SettingsSection } from "./settings-section";

export function AccountSettingsPage() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const isSsoUser = Boolean(user?.oauth_provider);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError(t.settings.account.passwordMismatch);
      return;
    }
    if (newPassword.length < 8) {
      setError(t.settings.account.passwordTooShort);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getCsrfHeaders(),
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        const authError = parseAuthError(data);
        setError(authError.message);
        return;
      }

      setMessage(t.settings.account.passwordChangedSuccess);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      setError(t.settings.account.networkError);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <SettingsSection title={t.settings.account.profileTitle}>
        <div className="space-y-2">
          <div className="grid grid-cols-[max-content_max-content] items-center gap-4">
            <span className="text-muted-foreground text-sm">
              {t.settings.account.email}
            </span>
            <span className="text-sm font-medium">{user?.email ?? "—"}</span>
            <span className="text-muted-foreground text-sm">
              {t.settings.account.role}
            </span>
            <span className="text-sm font-medium">
              {user ? businessRoleLabel(user.business_role) : "—"}
              {user?.system_role === "admin" ? " · 系统管理员" : ""}
            </span>
            {user?.organization_name && (
              <>
                <span className="text-muted-foreground text-sm">所属机构</span>
                <span className="text-sm font-medium">{user.organization_name}</span>
              </>
            )}
            {isSsoUser && (
              <>
                <span className="text-muted-foreground text-sm">
                  {t.settings.account.ssoProvider}
                </span>
                <span className="text-sm font-medium capitalize">
                  {user?.oauth_provider}
                </span>
              </>
            )}
          </div>
        </div>
      </SettingsSection>

      {user?.system_role === "admin" && <UserRoleManagement />}

      {!isSsoUser ? (
        <SettingsSection
          title={t.settings.account.changePasswordTitle}
          description={t.settings.account.changePasswordDescription}
        >
          <form onSubmit={handleChangePassword} className="max-w-sm space-y-3">
            <Input
              type="password"
              placeholder={t.settings.account.currentPassword}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
            <Input
              type="password"
              placeholder={t.settings.account.newPassword}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
            />
            <Input
              type="password"
              placeholder={t.settings.account.confirmNewPassword}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
            {message && <p className="text-sm text-green-500">{message}</p>}
            <Button
              type="submit"
              variant="outline"
              size="sm"
              disabled={loading}
            >
              {loading
                ? t.settings.account.updating
                : t.settings.account.updatePassword}
            </Button>
          </form>
        </SettingsSection>
      ) : (
        <SettingsSection
          title={t.settings.account.changePasswordTitle}
          description={t.settings.account.ssoPasswordDescription}
        >
          <p className="text-muted-foreground text-sm">
            {t.settings.account.ssoPasswordMessage.replace(
              "{provider}",
              user?.oauth_provider ?? "",
            )}
          </p>
        </SettingsSection>
      )}

      <SettingsSection title="" description="">
        <Button
          variant="destructive"
          size="sm"
          onClick={logout}
          className="gap-2"
        >
          <LogOutIcon className="size-4" />
          {t.settings.account.signOut}
        </Button>
      </SettingsSection>
    </div>
  );
}

const BUSINESS_ROLES: BusinessRole[] = [
  "public",
  "researcher",
  "cultural_institution",
  "government",
  "study_team",
];

function UserRoleManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/v1/auth/users", { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("无法读取用户角色");
        const payload: unknown = await response.json();
        setUsers(userSchema.array().parse(payload));
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "无法读取用户角色"),
      )
      .finally(() => setLoading(false));
  }, []);

  async function saveProfile(target: User) {
    setSavingId(target.id);
    setError("");
    try {
      const response = await fetch(
        `/api/v1/auth/users/${encodeURIComponent(target.id)}/business-profile`,
        {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json", ...getCsrfHeaders() },
          body: JSON.stringify({
            business_role: target.business_role,
            organization_name: target.organization_name || null,
          }),
        },
      );
      if (!response.ok) throw new Error("保存角色失败");
      const updated = userSchema.parse(await response.json());
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存角色失败");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <SettingsSection
      title="用户与场景角色"
      description="为账号分配真实业务角色和所属机构；权限由后端同步执行。"
    >
      {loading ? (
        <p className="text-muted-foreground text-sm">正在读取用户...</p>
      ) : (
        <div className="space-y-3">
          {users.map((target) => (
            <div
              key={target.id}
              className="grid gap-2 rounded-md border p-3 lg:grid-cols-[minmax(180px,1fr)_180px_minmax(160px,1fr)_72px] lg:items-center"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{target.email}</p>
                <p className="text-muted-foreground text-xs">
                  {target.system_role === "admin" ? "系统管理员" : "普通账号"}
                </p>
              </div>
              <select
                aria-label={`${target.email} 的业务角色`}
                value={target.business_role}
                onChange={(event) =>
                  setUsers((current) =>
                    current.map((item) =>
                      item.id === target.id
                        ? { ...item, business_role: event.target.value as BusinessRole }
                        : item,
                    ),
                  )
                }
                className="h-9 rounded-md border bg-background px-2 text-sm"
              >
                {BUSINESS_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {businessRoleLabel(role)}
                  </option>
                ))}
              </select>
              <Input
                aria-label={`${target.email} 的所属机构`}
                value={target.organization_name ?? ""}
                placeholder="所属机构（可选）"
                onChange={(event) =>
                  setUsers((current) =>
                    current.map((item) =>
                      item.id === target.id
                        ? { ...item, organization_name: event.target.value }
                        : item,
                    ),
                  )
                }
              />
              <Button
                type="button"
                size="sm"
                disabled={savingId === target.id}
                onClick={() => void saveProfile(target)}
              >
                {savingId === target.id ? "保存中" : "保存"}
              </Button>
            </div>
          ))}
          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>
      )}
    </SettingsSection>
  );
}
