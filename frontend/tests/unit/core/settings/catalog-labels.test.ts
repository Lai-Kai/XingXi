import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@rstest/core";

import { zhCN } from "@/core/i18n/locales/zh-CN";
import {
  getMemoryCategoryLabel,
  getSkillLabel,
  getToolLabel,
  isProductSkill,
} from "@/core/settings/catalog-labels";

test("every shipped product skill has a Chinese display without modifying its identity", () => {
  const root = resolve(process.cwd(), "../skills/public");
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    if (!existsSync(resolve(root, entry.name, "SKILL.md"))) continue;
    const markdown = readFileSync(
      resolve(root, entry.name, "SKILL.md"),
      "utf8",
    );
    const name = /^name:\s*(.+)$/m.exec(markdown)?.[1] ?? entry.name;
    const skill = {
      name,
      category: "public",
      description: "Original description",
    };
    if (!isProductSkill(skill)) continue;
    const label = getSkillLabel(skill, "zh-CN");
    expect(label.name, name).toMatch(/\p{Script=Han}/u);
    expect(label.description, name).toMatch(/\p{Script=Han}/u);
    expect(label.description).not.toMatch(/deer.?flow/i);
    expect(skill.name).toBe(name);
  }
});

test("custom metadata is retained while built-in identities stay hidden in both languages", () => {
  const skill = {
    name: "data-analysis",
    description: "用户自定义说明",
    category: "custom",
  };
  expect(getSkillLabel(skill, "zh-CN")).toEqual(skill);
  expect(getSkillLabel({ ...skill, category: "public" }, "en-US").name).toBe(
    "Data analysis",
  );
  for (const locale of ["zh-CN", "en-US"] as const) {
    const unknownSkill = getSkillLabel(
      {
        name: "private-sdk",
        description: "API JSON internal",
        category: "public",
      },
      locale,
      2,
    );
    const unknownTool = getToolLabel(
      "private-mcp",
      "PostgreSQL internal endpoint",
      locale,
      2,
    );
    expect(JSON.stringify([unknownSkill, unknownTool])).not.toMatch(
      /private|sdk|API|JSON|mcp|PostgreSQL|endpoint/i,
    );
    expect(unknownSkill.name).toContain("3");
    expect(unknownTool.name).toContain("3");
  }
});

test("legacy product integration is omitted while current research skills remain available", () => {
  expect(
    isProductSkill({ name: "claude-to-deerflow", category: "public" }),
  ).toBe(false);
  expect(isProductSkill({ name: "skill-reviewer", category: "public" })).toBe(
    true,
  );
});

test("the supplied tool configuration and memory categories use Chinese display labels", () => {
  const config = JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../extensions_config.example.json"),
      "utf8",
    ),
  ) as {
    mcpServers: Record<string, { description: string }>;
  };
  for (const [name, tool] of Object.entries(config.mcpServers)) {
    expect(getToolLabel(name, tool.description, "zh-CN").description).toMatch(
      /\p{Script=Han}/u,
    );
  }
  expect(getMemoryCategoryLabel("context", "zh-CN")).toBe("背景信息");
  expect(getMemoryCategoryLabel("地方研究", "zh-CN")).toBe("地方研究");
});

test("every Chinese settings label is localized and the product translations contain no legacy branding", () => {
  const visit = (value: unknown) => {
    if (typeof value === "string") expect(value).toMatch(/\p{Script=Han}/u);
    else if (value && typeof value === "object")
      Object.values(value).forEach(visit);
  };
  visit(zhCN.settings);
  expect(JSON.stringify(zhCN)).not.toMatch(/deer.?flow/i);
  expect(zhCN.settings.notification.testTitle).toBe("星羲");
});
