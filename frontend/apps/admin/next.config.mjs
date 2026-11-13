import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "../..");
// Where the Next.js server forwards API calls when there is no nginx in front (pnpm dev).
const apiUrl = process.env.INTERNAL_API_URL ?? "http://localhost:8000";

/** @type {import("next").NextConfig} */
const config = {
  basePath: "/admin",
  output: "standalone",
  outputFileTracingRoot: root,
  transpilePackages: ["@sanad/ui", "@sanad/i18n", "@sanad/api-client"],
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*`, basePath: false },
      { source: "/health/:path*", destination: `${apiUrl}/health/:path*`, basePath: false },
    ];
  },
};

export default config;
