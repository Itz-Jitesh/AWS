import type { NextConfig } from "next";

// Same-origin service proxies. The worker (Agent B) and ai (Agent C) services
// send no CORS headers, and browsers must never be pointed at cross-origin
// service URLs directly. The frontend fetches /service/worker/* and
// /service/ai/*; Next rewrites forward them server-side (DEC-INT-01 alias).
const workerTarget = (
  process.env.PLANPROOF_WORKER_URL ??
  process.env.NEXT_PUBLIC_WORKER_URL ??
  ""
).replace(/\/$/, "");
const aiTarget = (
  process.env.PLANPROOF_AI_URL ?? process.env.NEXT_PUBLIC_AI_URL ?? ""
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    const rules: Array<{ source: string; destination: string }> = [];
    if (workerTarget) {
      rules.push({
        source: "/service/worker/:path*",
        destination: `${workerTarget}/:path*`,
      });
    }
    if (aiTarget) {
      rules.push({
        source: "/service/ai/:path*",
        destination: `${aiTarget}/:path*`,
      });
    }
    return rules;
  },
};

export default nextConfig;
