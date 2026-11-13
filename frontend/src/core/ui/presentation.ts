/** Product messages must never echo service responses, credentials or diagnostics. */
export function publicErrorMessage(_error: unknown, fallback: string): string {
  return fallback;
}
