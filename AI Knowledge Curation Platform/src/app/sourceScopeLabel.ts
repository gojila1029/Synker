import type { Source } from "../types";

/**
 * A discovery_provider source (a channel/playlist URL with no single
 * resolvable video) behaves differently from a direct_resource source: it
 * can produce many candidates over time instead of exactly one, and can
 * legitimately stay "failed" when discovery is unsupported (e.g. a search
 * results URL). Surface that distinction instead of leaving it silent.
 */
export function sourceScopeLabel(scope: Source["sourceScope"] | undefined): string | null {
  if (scope === "discovery_provider") {
    return "Channel · auto-discovers videos";
  }
  return null;
}
