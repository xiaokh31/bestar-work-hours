import "server-only";
import type { ApiClientOptions } from "./api-client";

export function getServerApiOptions(): ApiClientOptions {
  return {
    baseUrl: process.env.API_ORIGIN,
    serviceKey: process.env.API_SERVICE_SECRET,
    deploymentBypass: process.env.API_DEPLOYMENT_BYPASS_SECRET,
  };
}
