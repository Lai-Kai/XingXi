import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

// Reuse the existing suite and an explicitly isolated, already-built frontend.
// Chrome is installed locally; no second browser dependency is downloaded.
export default defineConfig({
  ...base,
  use: {
    ...base.use,
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3106",
    channel: "chrome",
  },
  workers: 2,
  webServer: {
    command:
      "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3106",
    url: "http://127.0.0.1:3106",
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      SKIP_ENV_VALIDATION: "1",
      DEER_FLOW_AUTH_DISABLED: "1",
    },
  },
});
