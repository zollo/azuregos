import { describe, expect, it } from "vitest";
import { ApiError } from "./client";

describe("ApiError", () => {
  it("carries a status code and message", () => {
    const err = new ApiError(404, "Not found");
    expect(err.status).toBe(404);
    expect(err.message).toBe("Not found");
    expect(err).toBeInstanceOf(Error);
  });
});
