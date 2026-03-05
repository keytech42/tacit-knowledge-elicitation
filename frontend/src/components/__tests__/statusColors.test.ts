import { describe, it, expect } from "vitest";
import {
  STATUS_COLOR_TOKEN,
  VALID_STATUS_TOKENS,
  badgeColor,
  borderColor,
} from "../statusColors";

describe("STATUS_COLOR_TOKEN", () => {
  it("maps every status to a valid token", () => {
    for (const [status, token] of Object.entries(STATUS_COLOR_TOKEN)) {
      expect(
        (VALID_STATUS_TOKENS as readonly string[]).includes(token),
        `status "${status}" maps to unknown token "${token}"`,
      ).toBe(true);
    }
  });

  it("covers all question statuses", () => {
    for (const s of ["draft", "proposed", "in_review", "published", "closed", "archived"]) {
      expect(STATUS_COLOR_TOKEN).toHaveProperty(s);
    }
  });

  it("covers all answer statuses", () => {
    for (const s of ["submitted", "under_review", "approved", "revision_requested", "rejected"]) {
      expect(STATUS_COLOR_TOKEN).toHaveProperty(s);
    }
  });

  it("covers review verdicts", () => {
    for (const s of ["pending", "changes_requested"]) {
      expect(STATUS_COLOR_TOKEN).toHaveProperty(s);
    }
  });
});

describe("badgeColor", () => {
  it("generates consistent bg/text/border classes from a token", () => {
    const classes = badgeColor("status-blue");
    expect(classes).toBe("bg-status-blue/10 text-status-blue border border-status-blue/20");
  });

  it("works for every valid token", () => {
    for (const token of VALID_STATUS_TOKENS) {
      const classes = badgeColor(token);
      expect(classes).toContain(`bg-${token}/10`);
      expect(classes).toContain(`text-${token}`);
      expect(classes).toContain(`border-${token}/20`);
    }
  });
});

describe("borderColor", () => {
  it("generates a border class from a token", () => {
    expect(borderColor("status-green")).toBe("border-status-green/30");
  });

  it("works for every valid token", () => {
    for (const token of VALID_STATUS_TOKENS) {
      expect(borderColor(token)).toBe(`border-${token}/30`);
    }
  });
});

describe("badge and border color consistency", () => {
  it("badge and border derive from the same token for every status", () => {
    for (const [status, token] of Object.entries(STATUS_COLOR_TOKEN)) {
      const badge = badgeColor(token);
      const border = borderColor(token);

      // Both should reference the same token
      expect(badge, `badge for "${status}"`).toContain(token);
      expect(border, `border for "${status}"`).toContain(token);
    }
  });
});
