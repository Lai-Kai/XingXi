import type { ScheduleValue } from "@/components/workspace/scheduled-task-schedule-input";

export type RecipeTitleKey =
  | "mapSources"
  | "mapPoints"
  | "placeNames"
  | "mapWeekly";

export type Recipe = {
  id: string;
  icon: string;
  titleKey: RecipeTitleKey;
  schedule: ScheduleValue;
};

// Front-end-only starter recipes. The schedule's timezone is left empty so the
// ScheduleInput falls back to the browser-detected timezone when applied.
// Titles, descriptions and prompts are localized together by the page.
export const RECIPES: Recipe[] = [
  {
    id: "map-sources",
    icon: "🗺️",
    titleKey: "mapSources",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "map-points",
    icon: "📍",
    titleKey: "mapPoints",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "place-names",
    icon: "🏷️",
    titleKey: "placeNames",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "map-weekly",
    icon: "📚",
    titleKey: "mapWeekly",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * 1" },
      timezone: "",
    },
  },
];
