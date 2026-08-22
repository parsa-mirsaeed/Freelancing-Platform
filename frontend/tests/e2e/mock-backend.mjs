import http from "node:http";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const user = { id: freelancerId, email: "freelancer@example.com", roles: ["freelancer"] };
let profile = {
  id: "21111111-1111-4111-8111-111111111111",
  user_id: freelancerId,
  title: "Product systems designer",
  bio: "I design complex product workflows, interaction systems, and accessible design systems for global teams.",
  hourly_rate_minor: 14500,
  currency: "USD",
  timezone: "Europe/Zurich",
  accepting_work: true,
  languages: ["English", "German"],
  skills: ["Product Design", "Design Systems", "Research"],
  projection_version: 4,
  availability: {
    rules: [{ id: "31111111-1111-4111-8111-111111111111", weekday: 0, start_time: "09:00", end_time: "17:00", timezone: "Europe/Zurich" }],
    exceptions: [],
  },
};
let portfolio = [{
  id: "41111111-1111-4111-8111-111111111111",
  title: "Global banking design system",
  description: "A multi-market interaction and component system.",
  external_url: "https://example.com/work",
  files: [{ id: "51111111-1111-4111-8111-111111111111", mime_type: "application/pdf", file_size_bytes: 2400, scan_status: "SAFE" }],
}];
const reviews = [{ id: "61111111-1111-4111-8111-111111111111", project_id: "71111111-1111-4111-8111-111111111111", reviewer_user_id: "81111111-1111-4111-8111-111111111111", freelancer_user_id: freelancerId, rating: 5, comment: "Clear thinking, precise delivery, and excellent communication.", created_at: "2026-07-02T12:00:00+00:00" }];

function searchItem() {
  return {
    freelancer_id: freelancerId,
    title: profile.title,
    bio: profile.bio,
    skills: ["product-design", "design-systems", "research"],
    rating: 4.9,
    completed_jobs: 18,
    hourly_rate_minor: profile.hourly_rate_minor,
    currency: profile.currency,
    availability: profile.accepting_work,
    languages: profile.languages,
    projection_version: profile.projection_version,
    updated_at: "2026-08-19T10:00:00+00:00",
  };
}

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function authorized(request) {
  return request.headers.authorization === "Bearer access-token";
}

async function body(request) {
  let value = "";
  for await (const chunk of request) value += chunk;
  return value ? JSON.parse(value) : {};
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:8000");
  const method = request.method ?? "GET";
  if (url.pathname === "/health/live") return json(response, 200, { status: "ok" });
  if (url.pathname === "/api/v1/auth/login" && method === "POST") {
    return json(response, 200, { user, access_token: "access-token", refresh_token: "refresh-token", token_type: "Bearer" });
  }
  if (url.pathname === "/api/v1/auth/me") return authorized(request) ? json(response, 200, user) : json(response, 401, { error: { message: "Authentication required" } });
  if (url.pathname === "/api/v1/auth/logout" && method === "POST") return authorized(request) ? response.writeHead(204).end() : json(response, 401, { error: { message: "Authentication required" } });
  if (url.pathname === "/api/v1/auth/refresh" && method === "POST") {
    return json(response, 200, { access_token: "access-token", refresh_token: "refresh-token", token_type: "Bearer" });
  }
  if (url.pathname === "/api/v1/search/freelancers") {
    const query = url.searchParams.get("q")?.toLowerCase() ?? "";
    return json(response, 200, { items: query.includes("no-match") ? [] : [searchItem()] });
  }
  if (url.pathname === `/api/v1/freelancers/${freelancerId}` && method === "GET") return json(response, 200, profile);
  if (url.pathname === `/api/v1/freelancers/${freelancerId}/portfolio` && method === "GET") return json(response, 200, { items: portfolio });
  if (url.pathname === `/api/v1/freelancers/${freelancerId}/reviews` && method === "GET") return json(response, 200, { items: reviews });

  if (!authorized(request)) return json(response, 401, { error: { message: "Authentication required" } });
  if (url.pathname === "/api/v1/freelancers/me/profile" && method === "GET") return json(response, 200, profile);
  if (url.pathname === "/api/v1/freelancers/me/profile" && method === "PUT") {
    const input = await body(request);
    profile = { ...profile, ...input, projection_version: profile.projection_version + 1 };
    return json(response, 200, profile);
  }
  if (url.pathname === "/api/v1/freelancers/me/availability/rules" && method === "PUT") {
    const input = await body(request);
    const rules = (input.rules ?? []).map((rule, index) => ({ ...rule, id: `31111111-1111-4111-8111-${String(index + 2).padStart(12, "0")}` }));
    profile = { ...profile, availability: { ...profile.availability, rules }, projection_version: profile.projection_version + 1 };
    return json(response, 200, { rules });
  }
  if (url.pathname === "/api/v1/freelancers/me/availability/exceptions" && method === "PUT") {
    const input = await body(request);
    const exception = { id: "91111111-1111-4111-8111-111111111111", ...input };
    profile = { ...profile, availability: { ...profile.availability, exceptions: [...profile.availability.exceptions.filter((item) => item.date !== exception.date), exception] } };
    return json(response, 200, exception);
  }
  if (url.pathname === "/api/v1/freelancers/me/portfolio" && method === "POST") {
    const input = await body(request);
    const item = { id: `a1111111-1111-4111-8111-${String(portfolio.length + 1).padStart(12, "0")}`, title: input.title, description: input.description ?? "", external_url: input.external_url ?? null, files: [] };
    portfolio = [item, ...portfolio];
    return json(response, 201, item);
  }
  if (url.pathname.startsWith("/api/v1/portfolio/") && method === "DELETE") {
    const id = url.pathname.split("/").at(-1);
    portfolio = portfolio.filter((item) => item.id !== id);
    response.writeHead(204);
    return response.end();
  }
  return json(response, 404, { error: { message: "Mock route not found" } });
});

server.listen(8000, "127.0.0.1", () => console.log("mock backend listening on 8000"));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
