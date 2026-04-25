import { describe, it, expect } from "vitest";
import { isAudioFile, MAX_UPLOAD_SIZE_BYTES } from "@/services/api";

// Mirrors the backend rules in backend/app/main.py:upload_call.

function validateUpload(
  file: Pick<File, "name" | "type" | "size">,
): { ok: true } | { ok: false; reason: string } {
  if (!isAudioFile(file)) return { ok: false, reason: "type" };
  if (file.size > MAX_UPLOAD_SIZE_BYTES) return { ok: false, reason: "size" };
  if (file.size === 0) return { ok: false, reason: "empty" };
  return { ok: true };
}

describe("upload validation (pre-POST checks)", () => {
  it("accepts a small wav", () => {
    expect(
      validateUpload({ name: "a.wav", type: "audio/wav", size: 1024 }),
    ).toEqual({ ok: true });
  });

  it("rejects wrong type", () => {
    expect(
      validateUpload({ name: "a.exe", type: "application/x-msdownload", size: 1024 }),
    ).toEqual({ ok: false, reason: "type" });
  });

  it("rejects >200 MB files", () => {
    expect(
      validateUpload({ name: "big.wav", type: "audio/wav", size: 250 * 1024 * 1024 }),
    ).toEqual({ ok: false, reason: "size" });
  });

  it("rejects empty files", () => {
    expect(
      validateUpload({ name: "empty.wav", type: "audio/wav", size: 0 }),
    ).toEqual({ ok: false, reason: "empty" });
  });
});
