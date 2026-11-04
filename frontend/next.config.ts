import type { NextConfig } from "next";

// /api/* is forwarded to the backend by src/app/api/[...path]/route.ts rather than a rewrite:
// rewrites are fixed at build time, and BACKEND_URL has to be read when the server starts.
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
