import type { NextConfig } from "next";

/**
 * Next.js configuration for theory-bets-web app.
 *
 * Transpiles @dock108/ui package to ensure compatibility with Next.js
 * build process. This is required for all apps using shared UI components.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@dock108/ui", "@dock108/ui-kit", "@dock108/js-core"],
};

export default nextConfig;

