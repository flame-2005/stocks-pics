import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page depends on the signed-in session and on data that changes four times a day,
  // so the app renders dynamically per request instead of using Cache Components.
  cacheComponents: false,
  async headers() {
    // Pages must never be served stale. Next's own assets and hot-reload channel are excluded:
    // a no-store header on /_next/* makes the dev client reload the page in a loop.
    return [
      {
        source: "/((?!_next/|favicon.ico).*)",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
    ];
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
