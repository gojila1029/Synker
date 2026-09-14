import { describe, it, expect } from "vitest";
import { sourceScopeLabel } from "./sourceScopeLabel";

describe("sourceScopeLabel", () => {
  it("returns a discovery hint for a discovery_provider source", () => {
    expect(sourceScopeLabel("discovery_provider")).toBe("Channel · auto-discovers videos");
  });

  it("returns null for a direct_resource source (no badge needed)", () => {
    expect(sourceScopeLabel("direct_resource")).toBeNull();
  });

  it("returns null when sourceScope is undefined (older API response)", () => {
    expect(sourceScopeLabel(undefined)).toBeNull();
  });
});
