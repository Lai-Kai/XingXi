export class GatewayApiError extends Error {
  readonly code: string;
  readonly traceId: string | null;
  readonly retryable: boolean;
  readonly status: number;

  constructor(
    message: string,
    details: { code?: string; trace_id?: string; retryable?: boolean },
    status: number,
  ) {
    super(message);
    this.name = "GatewayApiError";
    this.code = details.code ?? "request_failed";
    this.traceId = details.trace_id ?? null;
    this.retryable = details.retryable ?? status >= 500;
    this.status = status;
  }
}

export async function throwGatewayApiError(
  response: Response,
  fallback: string,
): Promise<never> {
  const body = (await response.json().catch(() => ({}))) as {
    detail?: unknown;
    error?: {
      code?: string;
      message?: string;
      trace_id?: string;
      retryable?: boolean;
    };
  };
  const message =
    body.error?.message ??
    (typeof body.detail === "string" ? body.detail : fallback);
  throw new GatewayApiError(message, body.error ?? {}, response.status);
}
