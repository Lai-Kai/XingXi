import { describe, expect, it } from "@rstest/core";

import { enUS } from "@/core/i18n/locales/en-US";
import { zhCN } from "@/core/i18n/locales/zh-CN";
import { RECIPES } from "@/core/scheduled-tasks/recipes";

describe("Xingxi research recipes", () => {
  for (const [locale, translations] of Object.entries({ enUS, zhCN })) {
    it(`provides source-bound, report-only research drafts in ${locale}`, () => {
      expect(RECIPES).toHaveLength(4);
      for (const recipe of RECIPES) {
        const labels = translations.scheduledTasks.recipes[recipe.titleKey];
        expect(labels.title).not.toMatch(/GitHub|Trending|tech news|科技新闻/);
        expect(labels.prompt).toMatch(/木渎|Mudu/);
        expect(labels.prompt).toMatch(/出处|evidence IDs/);
        expect(labels.prompt).toMatch(
          /不.*(修改|写入|合并)|do not (modify|merge)/,
        );
      }
    });
  }

  it("uses daily or Monday morning schedules and defers the timezone to the form", () => {
    expect(RECIPES.map((recipe) => recipe.schedule)).toEqual([
      ...Array.from({ length: 3 }, () => ({
        schedule_type: "cron",
        schedule_spec: { cron: "0 9 * * *" },
        timezone: "",
      })),
      {
        schedule_type: "cron",
        schedule_spec: { cron: "0 9 * * 1" },
        timezone: "",
      },
    ]);
  });
});
