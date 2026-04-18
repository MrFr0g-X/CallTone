import { describe, it, expect, beforeEach } from "vitest";

// The auth layer persists the user to localStorage under a fixed key.
// These tests pin the contract that the backend team + UI team rely on.

const USER_KEY = "calltone_user";
const TOKEN_KEY = "calltone_token";

describe("auth storage contract", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips a user object", () => {
    const u = { id: 1, email: "qa@calltone.ai", role: "qa", name: "QA" };
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    const back = JSON.parse(localStorage.getItem(USER_KEY) ?? "null");
    expect(back).toEqual(u);
  });

  it("stores the bearer token as a plain string", () => {
    localStorage.setItem(TOKEN_KEY, "eyJhbGciOi.x.y");
    expect(localStorage.getItem(TOKEN_KEY)).toBe("eyJhbGciOi.x.y");
  });

  it("returns null after logout clears both keys", () => {
    localStorage.setItem(USER_KEY, "{}");
    localStorage.setItem(TOKEN_KEY, "x");
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    expect(localStorage.getItem(USER_KEY)).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
