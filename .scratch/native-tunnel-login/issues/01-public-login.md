# Restore login through the native deployment's public hostname

Status: ready-for-human

The public login page reloads as `/login?` without reaching the Gateway login
endpoint. Next.js rejects the public hostname on its development WebSocket and
font endpoints. Local authentication remains available.

## Acceptance

- Configure the public development hostname explicitly using an environment variable.
- Public login must submit through JavaScript and reach the existing authentication API.
- Unconfigured origins remain blocked; existing accounts and corpus data are preserved.
- Record unit, browser, and deployment verification.

## Comments

- 2026-10-15: Reproduced on the public hostname. Captured browser and origin logs under the native launcher's private `.runtime/` directory.
- 2026-10-15: Added `DEER_FLOW_DEV_ORIGINS` support and configured the deployed public hostname in the existing private startup environment. Restarted the native services on the same ports. The regression first failed against the original configuration, then all three tests passed, including rejecting unconfigured origins and retaining local access.
- 2026-10-15: Public browser verification now submits the login form instead of navigating to `/login?`; its development WebSocket connects successfully. A real API request using synthetic invalid credentials receives the expected 401 instead of an origin rejection. HTTPS issues a Secure CSRF cookie, an existing-account signed session reads `/auth/me` successfully, and the authenticated corpus page loads without failed requests. Existing password hashes and token versions match the pre-switch backup. No real account password was needed for verification.
- 2026-10-15: `git diff --check` passed. Frontend ESLint has zero errors and four existing graph-overview warnings. Full `pnpm check` reaches TypeScript but is blocked by the missing installed `@google/model-viewer` dependency in the unchanged map viewer and map-preview test; this package is already declared in `frontend/package.json`.
- 2026-10-15: Restored the existing locked frontend dependencies using the checkout's pnpm store; full `pnpm check` now passes with only the four existing graph-overview warnings. All 36 focused map and development-origin unit tests pass. An authenticated real-GLB browser regression passes, and the public Tunnel map returns 200 with seven model markers, authenticated reads returning 200, a connected development WebSocket, and no page errors or failed same-origin responses. See issue 02 and the private native runtime artifacts.
