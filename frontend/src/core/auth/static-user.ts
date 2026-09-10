import type { User } from "./types";

export const STATIC_WEBSITE_USER: User = {
  id: "static-website-user",
  email: "static@example.local",
  system_role: "admin",
  business_role: "government",
  organization_name: null,
  capabilities: [],
  needs_setup: false,
  oauth_provider: null,
};
