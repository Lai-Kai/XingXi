import { afterEach, expect, test, rs } from "@rstest/core";

afterEach(() => {
  rs.unstubAllGlobals();
});

test("createSourceDocument registers traceable source metadata", async () => {
  const fetchMock = rs.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
    new Response(
      JSON.stringify({
        id: "source-1",
        title: "木渎镇志",
        edition: "1996 年版",
        source_institution: "苏州市吴中区地方志办公室",
      }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    ),
  );
  rs.stubGlobal("fetch", fetchMock);

  const { createSourceDocument } = await import("@/core/source-files/api");
  const source = await createSourceDocument({
    title: "木渎镇志",
    edition: "1996 年版",
    source_institution: "苏州市吴中区地方志办公室",
    source_type: "gazetteer",
    source_level: "A",
    holder: "苏州市吴中区地方志办公室",
  });

  expect(source.id).toBe("source-1");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] ?? [];
  expect(url).toBe("/api/source-documents");
  expect(init?.method).toBe("POST");
  expect(JSON.parse(String(init?.body))).toEqual({
    title: "木渎镇志",
    edition: "1996 年版",
    source_institution: "苏州市吴中区地方志办公室",
    source_type: "gazetteer",
    source_level: "A",
    holder: "苏州市吴中区地方志办公室",
  });
});

test("uploadSourceFile reports real XMLHttpRequest upload progress", async () => {
  const progress = rs.fn();
  let opened: { method: string; url: string } | null = null;

  class FakeXMLHttpRequest {
    status = 200;
    responseText = JSON.stringify({
      success_count: 1,
      failure_count: 0,
      items: [
        {
          filename: "source.pdf",
          status: "uploaded",
          file: {
            id: "source-file-1",
            document_id: "source-1",
            object_key: "users/source-1/objects/original/aa/hash",
            original_filename: "source.pdf",
            mime_type: "application/pdf",
            size: 10,
            uploaded_by: "admin-1",
            uploaded_at: "2026-07-21T00:00:00Z",
          },
          ingestion_job: {
            id: "job-1",
            document_id: "source-1",
            source_file_id: "source-file-1",
            status: "pending",
            current_step: "parse",
            progress_percent: 0,
            steps: [],
            error_code: null,
            error_message: null,
            version: 1,
            event_sequence: 1,
            created_at: "2026-07-21T00:00:00Z",
            updated_at: "2026-07-21T00:00:00Z",
            completed_at: null,
          },
        },
      ],
    });
    withCredentials = false;
    private listeners = new Map<string, () => void>();
    upload = {
      addEventListener: (
        _name: string,
        listener: (event: ProgressEvent) => void,
      ) => {
        listener({
          lengthComputable: true,
          loaded: 5,
          total: 10,
        } as ProgressEvent);
      },
    };

    open(method: string, url: string) {
      opened = { method, url };
    }

    setRequestHeader() {
      return undefined;
    }

    addEventListener(name: string, listener: () => void) {
      this.listeners.set(name, listener);
    }

    send() {
      this.listeners.get("load")?.();
    }

    abort() {
      this.listeners.get("abort")?.();
    }
  }

  rs.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);

  const { uploadSourceFile } = await import("@/core/source-files/api");
  const file = Object.assign(
    new Blob(["1234567890"], { type: "application/pdf" }),
    { name: "source.pdf", lastModified: 0 },
  ) as File;
  const task = uploadSourceFile("source-1", file, progress);
  const result = await task.promise;

  expect(opened).toEqual({
    method: "POST",
    url: "/api/source-documents/source-1/files",
  });
  expect(progress).toHaveBeenCalledWith(50);
  expect(result.file.id).toBe("source-file-1");
  expect(result.ingestionJob?.id).toBe("job-1");
});

test("uploadSourceFile cancel aborts only its active request", async () => {
  class PendingXMLHttpRequest {
    status = 0;
    responseText = "";
    withCredentials = false;
    private listeners = new Map<string, () => void>();
    upload = { addEventListener: () => undefined };

    open() {
      return undefined;
    }

    setRequestHeader() {
      return undefined;
    }

    addEventListener(name: string, listener: () => void) {
      this.listeners.set(name, listener);
    }

    send() {
      return undefined;
    }

    abort() {
      this.listeners.get("abort")?.();
    }
  }
  rs.stubGlobal("XMLHttpRequest", PendingXMLHttpRequest);
  const { uploadSourceFile } = await import("@/core/source-files/api");
  const file = Object.assign(new Blob(["pending"]), {
    name: "pending.pdf",
    lastModified: 0,
  }) as File;
  const task = uploadSourceFile("source-1", file, () => undefined);

  task.cancel();

  await expect(task.promise).rejects.toThrow("上传已取消");
});

test("uploadSourceFile preserves duplicate details for the decision UI", async () => {
  const existingFile = {
    id: "source-file-existing",
    document_id: "source-1",
    object_key: "users/source-1/objects/original/aa/hash",
    original_filename: "existing.pdf",
    mime_type: "application/pdf",
    size: 10,
    sha256: "a".repeat(64),
    duplicate_of_file_id: null,
    version_of_file_id: null,
    uploaded_by: "admin-1",
    uploaded_at: "2026-07-21T00:00:00Z",
  };
  class DuplicateXMLHttpRequest {
    status = 200;
    responseText = JSON.stringify({
      success_count: 0,
      failure_count: 1,
      items: [
        {
          filename: "renamed.pdf",
          status: "failed",
          error_code: "duplicate_file",
          error: "File content already exists",
          existing_file: existingFile,
        },
      ],
    });
    withCredentials = false;
    private listeners = new Map<string, () => void>();
    upload = { addEventListener: () => undefined };
    open() {
      return undefined;
    }
    setRequestHeader() {
      return undefined;
    }
    addEventListener(name: string, listener: () => void) {
      this.listeners.set(name, listener);
    }
    send() {
      this.listeners.get("load")?.();
    }
    abort() {
      return undefined;
    }
  }
  rs.stubGlobal("XMLHttpRequest", DuplicateXMLHttpRequest);
  const { SourceUploadError, uploadSourceFile } =
    await import("@/core/source-files/api");
  const file = Object.assign(new Blob(["duplicate"]), {
    name: "renamed.pdf",
    lastModified: 0,
  }) as File;

  const error = await uploadSourceFile(
    "source-1",
    file,
    () => undefined,
  ).promise.catch((reason: unknown) => reason);

  expect(error).toBeInstanceOf(SourceUploadError);
  if (!(error instanceof SourceUploadError)) {
    throw new Error("Expected SourceUploadError");
  }
  expect(error.code).toBe("duplicate_file");
  expect(error.existingFile).toEqual(existingFile);
});

test("review API keeps exact chunk-set scope and submits structured batch decisions", async () => {
  const fetchMock = rs.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      if (url.includes("/review/queue")) {
        return new Response(
          JSON.stringify({
            document_id: "document-1",
            source_file_id: "file-1",
            chunk_set_id: "chunk-set-1",
            split_version: "split-v1",
            pages: [],
            chunks: [],
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/review/decisions") && init?.method === "POST") {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response("not found", { status: 404 });
    },
  );
  rs.stubGlobal("fetch", fetchMock);
  const { getReviewQueue, submitReviewDecisions } =
    await import("@/core/source-files/api");

  const queue = await getReviewQueue("document-1", "file-1", "chunk-set-1");
  await submitReviewDecisions("document-1", "file-1", [
    {
      target_type: "chunk",
      target_id: "chunk-1",
      decision: "disputed",
      comment: "版本异文待确认",
    },
  ]);

  expect(queue.chunk_set_id).toBe("chunk-set-1");
  const queueInput = fetchMock.mock.calls[0]?.[0];
  const queueUrl =
    typeof queueInput === "string"
      ? queueInput
      : queueInput instanceof URL
        ? queueInput.toString()
        : queueInput?.url;
  expect(queueUrl).toContain("chunk_set_id=chunk-set-1");
  const decisionInit = fetchMock.mock.calls[1]?.[1];
  expect(decisionInit?.method).toBe("POST");
  if (typeof decisionInit?.body !== "string") {
    throw new Error("Expected JSON request body");
  }
  expect(JSON.parse(decisionInit.body)).toEqual({
    items: [
      {
        target_type: "chunk",
        target_id: "chunk-1",
        decision: "disputed",
        comment: "版本异文待确认",
      },
    ],
  });
});
