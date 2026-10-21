import type { NextConfig } from "next";

// The browser talks to one origin; Next proxies API calls to FastAPI so the
// session cookie is first-party and no CORS is ever granted.
const API = process.env.ESCAPEMENT_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/.well-known/escapement-keys.json", destination: `${API}/.well-known/escapement-keys.json` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default config;
