"use client";

import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { MCPConfigRequestError } from "@/core/mcp/api";
import { useMCPConfig, useEnableMCPServer } from "@/core/mcp/hooks";
import type { MCPServerConfig } from "@/core/mcp/types";
import { getToolLabel } from "@/core/settings/catalog-labels";
import { env } from "@/env";

import { SettingsSection } from "./settings-section";

export function ToolSettingsPage() {
  const { t } = useI18n();
  const { config, isLoading, error } = useMCPConfig();
  const adminRequired =
    error instanceof MCPConfigRequestError && error.isAdminRequired;
  return (
    <SettingsSection
      title={t.settings.tools.title}
      description={t.settings.tools.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : adminRequired ? (
        <div className="text-muted-foreground text-sm">
          {t.settings.tools.adminRequired}
        </div>
      ) : error ? (
        <div role="alert" className="text-destructive text-sm">
          {t.settings.tools.loadError}
        </div>
      ) : (
        config && <MCPServerList servers={config.mcp_servers} />
      )}
    </SettingsSection>
  );
}

function MCPServerList({
  servers,
}: {
  servers?: Record<string, MCPServerConfig>;
}) {
  const { t, locale } = useI18n();
  const { mutate: enableMCPServer } = useEnableMCPServer();
  const entries = Object.entries(servers ?? {});
  if (entries.length === 0) {
    return (
      <div className="text-muted-foreground text-sm">
        {t.settings.tools.empty}
      </div>
    );
  }
  return (
    <div className="flex w-full flex-col gap-4">
      {entries.map(([name, config], index) => {
        const label = getToolLabel(name, config.description, locale, index);
        return (
          <Item className="w-full" variant="outline" key={name}>
            <ItemContent>
              <ItemTitle>
                <div className="flex items-center gap-2">
                  <div>{label.name}</div>
                </div>
              </ItemTitle>
              <ItemDescription className="line-clamp-4">
                {label.description}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <Switch
                aria-label={label.name}
                checked={config.enabled}
                disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                onCheckedChange={(checked) =>
                  enableMCPServer({ serverName: name, enabled: checked })
                }
              />
            </ItemActions>
          </Item>
        );
      })}
    </div>
  );
}
