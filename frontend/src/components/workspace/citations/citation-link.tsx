import { ExternalLinkIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  evidenceDetailPath,
  parseEvidenceHref,
} from "@/core/citations/sources";
import { recordOperationEvent } from "@/core/operations/api";

export function CitationLink({
  href,
  children,
  onClick,
  ...props
}: ComponentProps<"a">) {
  const evidenceId = parseEvidenceHref(href);
  const domain = evidenceId ? "evidence" : extractDomain(href ?? "");

  // Priority: children > domain
  const childrenText =
    typeof children === "string"
      ? children.replace(/^citation:\s*/i, "")
      : null;
  const isGenericText = childrenText === "Source" || childrenText === "来源";
  const displayText = isGenericText ? domain : (childrenText ?? domain);
  const resolvedHref = evidenceId ? evidenceDetailPath(evidenceId) : href;

  return (
    <HoverCard closeDelay={0} openDelay={0}>
      <HoverCardTrigger asChild>
        <a
          href={resolvedHref}
          target={evidenceId ? undefined : "_blank"}
          rel={evidenceId ? undefined : "noopener noreferrer"}
          className="inline-flex items-center"
          data-evidence-id={evidenceId ?? undefined}
          data-citation-protocol={evidenceId ? "evidence" : "http"}
          onClick={(event) => {
            event.stopPropagation();
            recordOperationEvent({
              event_type: "citation_open",
              entity_id: evidenceId ?? undefined,
              entity_name: displayText ?? undefined,
              metadata: { href: resolvedHref ?? "" },
            });
            onClick?.(event);
          }}
          {...props}
        >
          <Badge
            variant="secondary"
            className="hover:bg-secondary/80 mx-0.5 cursor-pointer gap-1 rounded-full px-2 py-0.5 text-xs font-normal"
          >
            {displayText}
          </Badge>
        </a>
      </HoverCardTrigger>
      <HoverCardContent className="w-72" align="start">
        <div className="p-3">
          <div className="space-y-1">
            {displayText && (
              <h4 className="truncate text-sm leading-tight font-medium">
                {displayText}
              </h4>
            )}
            {evidenceId ? (
              <p className="text-muted-foreground truncate text-xs break-all">
                资料出处编号：{evidenceId}
              </p>
            ) : (
              href && (
                <p className="text-muted-foreground truncate text-xs break-all">
                  {href}
                </p>
              )
            )}
          </div>
          <a
            href={resolvedHref}
            target={evidenceId ? undefined : "_blank"}
            rel={evidenceId ? undefined : "noopener noreferrer"}
            className="text-primary mt-2 inline-flex items-center gap-1 text-xs hover:underline"
            onClick={() =>
              recordOperationEvent({
                event_type: "citation_open",
                entity_id: evidenceId ?? undefined,
                entity_name: displayText ?? undefined,
                metadata: { href: resolvedHref ?? "" },
              })
            }
          >
            {evidenceId ? "查看出处详情" : "访问来源"}
            <ExternalLinkIcon className="size-3" />
          </a>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return url;
  }
}
