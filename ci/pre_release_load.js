import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = (__ENV.BASE_URL || "").replace(/\/$/, "");
if (!baseUrl) {
  throw new Error("BASE_URL is required");
}

const loadDuration = __ENV.LOAD_DURATION || "5m";
const soakDuration = __ENV.SOAK_DURATION || "30m";
const loadVus = Number(__ENV.LOAD_VUS || "20");
const soakVus = Number(__ENV.SOAK_VUS || "20");

export const options = {
  scenarios: {
    public_read_load: {
      executor: "constant-vus",
      vus: loadVus,
      duration: loadDuration,
      exec: "publicReadTraffic",
    },
    public_read_soak: {
      executor: "constant-vus",
      vus: soakVus,
      duration: soakDuration,
      startTime: loadDuration,
      exec: "publicReadTraffic",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000", "p(99)<2000"],
  },
};

const publicPaths = ["/health/ready", "/api/v1/gigs", "/api/v1/projects"];

export function publicReadTraffic() {
  for (const path of publicPaths) {
    const response = http.get(`${baseUrl}${path}`, {
      tags: { endpoint: path },
      timeout: "10s",
    });
    check(response, {
      [`${path} returns 200`]: (result) => result.status === 200,
    });
  }
  sleep(0.25);
}
