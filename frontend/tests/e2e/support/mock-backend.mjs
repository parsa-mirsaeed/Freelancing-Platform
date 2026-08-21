import http from "node:http";

const USER_ID = "11111111-1111-4111-8111-111111111111";

const profile = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  user_id: USER_ID,
  title: "Platform & API Engineer",
  bio: "Designs reliable marketplace backends, developer platforms, and data-intensive product systems.",
  hourly_rate_minor: 14500,
  currency: "USD",
  timezone: "Europe/Zurich",
  accepting_work: true,
  languages: ["English", "German"],
  skills: ["python", "postgresql", "distributed-systems", "api-design"],
  projection_version: 7,
  availability: {
    rules: [
      { id: "r1", weekday: 0, start_time: "09:00", end_time: "17:00", timezone: "Europe/Zurich" },
      { id: "r2", weekday: 2, start_time: "10:00", end_time: "18:00", timezone: "Europe/Zurich" },
    ],
    exceptions: [
      { id: "e1", date: "2026-09-04", available: false, start_time: null, end_time: null, reason: "Conference" },
    ],
  },
};

const searchItem = {
  freelancer_id: USER_ID,
  title: profile.title,
  bio: profile.bio,
  skills: profile.skills,
  rating: 4.9,
  completed_jobs: 18,
  hourly_rate_minor: profile.hourly_rate_minor,
  currency: profile.currency,
  availability: true,
  languages: profile.languages,
  portfolio_text: "Marketplace reliability platform API architecture",
  projection_version: 7,
  updated_at: "2026-08-21T18:20:00+00:00",
};

const portfolio = {
  items: [
    {
      id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      title: "Marketplace reliability program",
      description: "Reworked transactional boundaries, outbox delivery, and operational observability.",
      external_url: "https://example.com/case-study",
      files: [
        { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", mime_type: "application/pdf", file_size_bytes: 842120, scan_status: "SAFE" },
      ],
    },
  ],
};

const reviews = {
  items: [
    {
      id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      project_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      reviewer_user_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
      freelancer_user_id: USER_ID,
      rating: 5,
      comment: "Clear architecture, excellent delivery discipline, and strong communication.",
      created_at: "2026-08-18T09:30:00+00:00",
    },
  ],
};

function send(response, status, body) {
  const content = JSON.stringify(body);
  response.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(content),
  });
  response.end(content);
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:8000");

  if (url.pathname === "/health/live") return send(response, 200, { status: "ok" });
  if (url.pathname === "/api/v1/auth/me") return send(response, 401, { error: { code: "unauthorized", message: "Authentication required" } });
  if (url.pathname === "/api/v1/search/freelancers") return send(response, 200, { items: [searchItem] });
  if (url.pathname === `/api/v1/freelancers/${USER_ID}`) return send(response, 200, profile);
  if (url.pathname === `/api/v1/freelancers/${USER_ID}/portfolio`) return send(response, 200, portfolio);
  if (url.pathname === `/api/v1/freelancers/${USER_ID}/reviews`) return send(response, 200, reviews);

  return send(response, 404, { error: { code: "not_found", message: "Mock endpoint not found" } });
});

server.listen(8000, "127.0.0.1", () => {
  console.log("mock backend listening on http://127.0.0.1:8000");
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
