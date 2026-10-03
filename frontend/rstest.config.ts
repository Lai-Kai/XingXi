import { resolve } from "path";

import { pluginReact } from "@rsbuild/plugin-react";
import { defineConfig } from "@rstest/core";

export default defineConfig({
  reporters: process.env.TEST_REPORT_DIR
    ? [
        "default",
        [
          "json",
          { outputPath: resolve(process.env.TEST_REPORT_DIR, "results.json") },
        ],
      ]
    : ["default"],
  plugins: [pluginReact()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  output: {
    // Streamdown imports KaTeX CSS as a side effect. Bundle these packages so
    // Rsbuild processes that CSS import instead of Node trying to load it.
    bundleDependencies: ["streamdown", "katex"],
  },
  include: ["tests/unit/**/*.test.ts"],
});
