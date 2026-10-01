import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async redirects() {
    // Preserve existing attendance/employee links while using the homepage.
    return [{ source: "/work-hours", destination: "/", permanent: true }];
  },
};
export default config;
