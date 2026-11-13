import { describe, expect, it } from "@rstest/core";

import {
  mapPixelRatio,
  readMapPerformance,
  saveMapPerformance,
  MAP_PERFORMANCE_KEY,
} from "@/core/map/display-performance";

describe("map display performance", () => {
  it("caps high density pixel work without upscaling low density displays", () => {
    expect(mapPixelRatio("balanced", 3)).toBe(1.5);
    expect(mapPixelRatio("light", 3)).toBe(1);
    expect(mapPixelRatio("balanced", 0.75)).toBe(0.75);
    expect(mapPixelRatio("light", NaN)).toBe(1);
    expect(mapPixelRatio("balanced", -1)).toBe(1);
  });
  it("restores only supported preferences and survives restricted storage", () => {
    let value: string | null = null;
    const storage = {
      getItem: () => value,
      setItem: (key: string, next: string) => {
        expect(key).toBe(MAP_PERFORMANCE_KEY);
        value = next;
      },
    };
    expect(readMapPerformance(storage)).toBe("balanced");
    saveMapPerformance(storage, "light");
    expect(readMapPerformance(storage)).toBe("light");
    value = "unknown";
    expect(readMapPerformance(storage)).toBe("balanced");
    const denied = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(readMapPerformance(denied)).toBe("balanced");
    expect(() => saveMapPerformance(denied, "light")).not.toThrow();
  });
});
