import { describe, expect, it } from "vitest";
import { formatTime, modePill, riskLabel, relativeTime } from "../src/utils/format";

describe("format utils", () => {
  it("formats timestamps in Asia/Kolkata", () => {
    // 2026-09-19 10:00 UTC == 15:30 IST
    const iso = "2026-09-19T10:00:00+00:00";
    const out = formatTime(iso);
    expect(out).toContain("Sept");
    expect(out).toContain("03:30"); // IST display
  });

  it("handles null timestamps", () => {
    expect(formatTime(null)).toBe("—");
    expect(relativeTime(null)).toBe("—");
  });

  it("labels demo data explicitly", () => {
    const pill = modePill("demo");
    expect(pill?.text).toBe("DEMO DATA");
    const cached = modePill("live", "cached");
    expect(cached?.text).toBe("CACHED DATA");
  });

  it("risk labels are readable, not colour-only", () => {
    expect(riskLabel.low).toBe("Low Risk");
    expect(riskLabel.moderate).toBe("Moderate Risk");
    expect(riskLabel.high).toBe("High Risk");
  });
});
