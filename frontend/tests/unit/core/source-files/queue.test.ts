import { expect, test } from "@rstest/core";

import {
  createSourceUploadQueue,
  sourceConflictActions,
} from "@/core/source-files/queue";

function fakeFile(name: string, size: number): File {
  return { name, size, lastModified: 0 } as File;
}

test("createSourceUploadQueue applies server limits per file without dropping valid files", () => {
  const queue = createSourceUploadQueue(
    [
      fakeFile("valid.PDF", 10),
      fakeFile("forged.exe", 5),
      fakeFile("large.png", 30),
    ],
    {
      max_files: 3,
      max_file_size: 20,
      max_total_size: 40,
      allowed_extensions: [".pdf", ".png", ".jpg", ".jpeg", ".docx"],
    },
  );

  expect(queue.map((item) => item.status)).toEqual([
    "queued",
    "failed",
    "failed",
  ]);
  expect(queue[1]?.error).toContain("类型");
  expect(queue[2]?.error).toContain("大小");
  expect(queue[0]?.file.name).toBe("valid.PDF");
});

test("sourceConflictActions exposes only valid duplicate decisions", () => {
  expect(sourceConflictActions("duplicate_file")).toEqual([
    "reference_existing",
    "new_version",
  ]);
  expect(sourceConflictActions("same_name_different_content")).toEqual([
    "new_version",
  ]);
  expect(sourceConflictActions("storage_failed")).toEqual([]);
});
