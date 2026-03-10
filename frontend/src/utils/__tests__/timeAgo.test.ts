import { describe, it, expect, vi, afterEach } from "vitest";
import { timeAgo, exactDateTime } from "../timeAgo";

describe("timeAgo", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function fakeNow(isoString: string) {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(isoString));
  }

  it("returns 'just now' for timestamps less than 60 seconds ago", () => {
    fakeNow("2026-03-10T12:00:30Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("just now");
  });

  it("returns 'just now' for a timestamp 0 seconds ago", () => {
    fakeNow("2026-03-10T12:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("just now");
  });

  it("returns '1 minute ago' for a timestamp 60 seconds ago", () => {
    fakeNow("2026-03-10T12:01:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("1 minute ago");
  });

  it("returns '5 minutes ago' for a timestamp 5 minutes ago", () => {
    fakeNow("2026-03-10T12:05:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("5 minutes ago");
  });

  it("returns '59 minutes ago' for a timestamp 59 minutes ago", () => {
    fakeNow("2026-03-10T12:59:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("59 minutes ago");
  });

  it("returns '1 hour ago' for a timestamp 60 minutes ago", () => {
    fakeNow("2026-03-10T13:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("1 hour ago");
  });

  it("returns '3 hours ago' for a timestamp 3 hours ago", () => {
    fakeNow("2026-03-10T15:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("3 hours ago");
  });

  it("returns '23 hours ago' for a timestamp 23 hours ago", () => {
    fakeNow("2026-03-11T11:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("23 hours ago");
  });

  it("returns 'Yesterday' for a timestamp 24-47 hours ago", () => {
    fakeNow("2026-03-11T12:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("Yesterday");
  });

  it("returns '3 days ago' for a timestamp 3 days ago", () => {
    fakeNow("2026-03-13T12:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("3 days ago");
  });

  it("returns '6 days ago' for a timestamp 6 days ago", () => {
    fakeNow("2026-03-16T12:00:00Z");
    expect(timeAgo("2026-03-10T12:00:00Z")).toBe("6 days ago");
  });

  it("returns a formatted date for timestamps 7+ days ago", () => {
    fakeNow("2026-03-17T12:00:00Z");
    const result = timeAgo("2026-03-10T12:00:00Z");
    // Should contain "Mar" and "10" and "2026"
    expect(result).toContain("Mar");
    expect(result).toContain("10");
    expect(result).toContain("2026");
  });

  it("returns a formatted date for timestamps months ago", () => {
    fakeNow("2026-06-15T12:00:00Z");
    const result = timeAgo("2026-01-05T12:00:00Z");
    expect(result).toContain("Jan");
    expect(result).toContain("5");
    expect(result).toContain("2026");
  });
});

describe("exactDateTime", () => {
  it("formats a date with month, day, year, hour, and minute", () => {
    const result = exactDateTime("2026-03-10T14:30:00Z");
    // Result should contain date parts (exact format depends on locale)
    expect(result).toContain("2026");
    expect(result).toContain("Mar");
    expect(result).toContain("10");
  });
});
