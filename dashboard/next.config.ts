import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page depends on the signed-in session and on data that changes four times a day,
  // so the app renders dynamically per request instead of using Cache Components.
  cacheComponents: false,
  async headers() {
    return [{ source: "/:path*", headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }] }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
