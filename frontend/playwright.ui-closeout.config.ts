import { defineConfig } from "@playwright/test";

import base from "./playwright.ui-redesign.config";

// Reuse the same built app. Login gets a separate server with the SSR bypass off.
export default defineConfig({
  ...base,
  webServer: [
    {
      command:
        "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3106",
      url: "http://127.0.0.1:3106",
      reuseExistingServer: false,
      env: { SKIP_ENV_VALIDATION: "1", DEER_FLOW_AUTH_DISABLED: "1" },
    },
    {
      command:
        "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3107",
      url: "http://127.0.0.1:3107/login",
      reuseExistingServer: false,
      env: {
        SKIP_ENV_VALIDATION: "1",
        DEER_FLOW_AUTH_DISABLED: "0",
        DEER_FLOW_INTERNAL_GATEWAY_BASE_URL: "http://127.0.0.1:8001",
        DEER_FLOW_TRUSTED_ORIGINS: "http://127.0.0.1:3107",
      },
    },
  ],
});
