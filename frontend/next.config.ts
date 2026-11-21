import type { NextConfig } from "next";

// Frontend woła backend przez /api/* (bez CORS). W Dockerze BACKEND_URL=http://backend:8000.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  output: "standalone",
  experimental: {
    // lokalny model (np. PLLuM na laptopie) odpowiada 30-90 s; domyślny limit proxy to 30 s -> błąd 500
    proxyTimeout: 300_000,
    // Aplikacja jest za logowaniem (sesja w localStorage), strony renderują się w przeglądarce.
    // Walidacja „instant UI” tylko dla segmentów, które jawnie ustawią `export const instant`.
    instantInsights: { validationLevel: "manual-warning" },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
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
