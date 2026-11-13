import { afterEach, expect, rs, test } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MapPage from "@/app/workspace/map/page";
import OperationsPage from "@/app/workspace/operations/page";
import QualityPage from "@/app/workspace/quality/page";
import { useMapCatalog } from "@/core/map/use-map-catalog";

rs.mock("@/core/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { system_role: "user", capabilities: [] } }),
}));
rs.mock("@/components/ui/sidebar", () => ({
  SidebarTrigger: "button",
  useSidebar: () => ({
    isMobile: true,
    openMobile: false,
    toggleSidebar: rs.fn(),
  }),
}));
rs.mock("@/core/map/use-map-catalog", () => ({ useMapCatalog: rs.fn() }));
rs.mock("@/components/workspace/map/maplibre-canvas", () => ({
  MapLibreCanvas: () => null,
}));

afterEach(() => {
  rs.clearAllMocks();
});

test("map loading and failure retain a mobile navigation button", () => {
  for (const error of [null, "地图服务连接失败"]) {
    rs.mocked(useMapCatalog).mockReturnValue({
      baseCatalog: null,
      catalog: null,
      error,
      customPointsError: null,
      reloadKey: 0,
      reload: rs.fn(),
      retryCustomPoints: rs.fn(),
      addCustomPoint: rs.fn(),
    });
    const html = renderToStaticMarkup(createElement(MapPage));
    expect(html).toContain("古舆地图");
    expect(html).toMatch(/<div[^>]*md:hidden[^>]*><button/);
    if (error) {
      expect(html).toContain("地图资料暂时无法加载");
      expect(html).toContain("重新加载");
    } else {
      expect(html).toContain("正在读取古舆地图资料");
    }
  }
});

test("permission screens retain mobile navigation so readers can leave", () => {
  for (const [page, title] of [
    [QualityPage, "无质量治理权限"],
    [OperationsPage, "无运营治理权限"],
  ] as const) {
    const html = renderToStaticMarkup(createElement(page));
    expect(html).toContain(title);
    expect(html).toMatch(/<div[^>]*md:hidden[^>]*><button/);
  }
});
