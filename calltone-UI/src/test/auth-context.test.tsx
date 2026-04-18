import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useAuth } from "@/contexts/AuthContext";

// Stop AuthContext.tsx from making a real `/auth/me` call when AuthProvider
// is mounted — not all tests need it, but the import chain still pulls axios.
vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>(
    "@/services/api",
  );
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      logout: vi.fn(),
      me: vi.fn().mockResolvedValue({ data: null }),
    },
  };
});

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("useAuth throws when consumed outside AuthProvider", () => {
    // React logs the thrown error — silence it for this test only
    const origError = console.error;
    console.error = () => {};
    try {
      expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
    } finally {
      console.error = origError;
    }
  });
});
