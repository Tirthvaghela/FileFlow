import { describe, expect, it } from "vitest";
import { buildCategoryColorMap, categoryBadge, formatBytes } from "./categoryMeta.js";

describe("buildCategoryColorMap", () => {
  it("assigns colors deterministically by alphabetical order, not input order", () => {
    const a = buildCategoryColorMap(["Zebra", "Apple", "Mango"]);
    const b = buildCategoryColorMap(["Mango", "Zebra", "Apple"]);
    expect(a).toEqual(b);
  });

  it("gives every distinct category a different color, cycling the palette after 8", () => {
    const map = buildCategoryColorMap(["A", "B", "C"]);
    const colors = Object.values(map);
    expect(new Set(colors).size).toBe(3);
  });

  it("de-duplicates repeated category names", () => {
    const map = buildCategoryColorMap(["Documents", "Documents", "Images"]);
    expect(Object.keys(map)).toHaveLength(2);
  });
});

describe("categoryBadge", () => {
  it("uses the hardcoded override for known categories", () => {
    expect(categoryBadge("Documents")).toBe("DOC");
    expect(categoryBadge("Source Code")).toBe("{ }");
  });

  it("derives a 3-letter badge from unknown category names", () => {
    expect(categoryBadge("Finance Folder")).toBe("FIN");
  });

  it("falls back to ??? for a name with no letters", () => {
    expect(categoryBadge("123")).toBe("???");
  });
});

describe("formatBytes", () => {
  it("formats zero as 0 B", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("picks the largest unit that keeps the value under 1024", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("drops the decimal once the value reaches 100+", () => {
    expect(formatBytes(150 * 1024 * 1024)).toBe("150 MB");
  });
});
