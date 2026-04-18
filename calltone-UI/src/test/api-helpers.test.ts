import { describe, it, expect } from "vitest";
import {
  isAudioFile,
  ACCEPTED_AUDIO_TYPES,
  MAX_UPLOAD_SIZE_BYTES,
} from "@/services/api";

describe("isAudioFile", () => {
  it("accepts common audio mime types", () => {
    expect(isAudioFile({ name: "x.wav", type: "audio/wav" } as File)).toBe(true);
    expect(isAudioFile({ name: "x.mp3", type: "audio/mpeg" } as File)).toBe(true);
    expect(isAudioFile({ name: "x.flac", type: "audio/flac" } as File)).toBe(true);
  });

  it("falls back to extension when mime is empty", () => {
    expect(isAudioFile({ name: "clip.wav", type: "" } as File)).toBe(true);
    expect(isAudioFile({ name: "clip.mp3", type: "" } as File)).toBe(true);
  });

  it("rejects executables, pdfs, images", () => {
    expect(
      isAudioFile({ name: "x.exe", type: "application/x-msdownload" } as File),
    ).toBe(false);
    expect(isAudioFile({ name: "x.pdf", type: "application/pdf" } as File)).toBe(false);
    expect(isAudioFile({ name: "x.jpg", type: "image/jpeg" } as File)).toBe(false);
  });
});

describe("upload constants", () => {
  it("exposes the accepted audio types list", () => {
    expect(ACCEPTED_AUDIO_TYPES.length).toBeGreaterThanOrEqual(5);
    expect(ACCEPTED_AUDIO_TYPES).toContain("audio/wav");
  });

  it("caps uploads at 100 MB", () => {
    expect(MAX_UPLOAD_SIZE_BYTES).toBe(100 * 1024 * 1024);
  });
});
