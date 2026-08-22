import http from "node:http";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const employerId = "a2111111-1111-4111-8111-111111111111";
const freelancerUser = { id: freelancerId, email: "freelancer@example.com", roles: ["freelancer"] };
const employerUser = { id: employerId, email: "employer@example.com", roles: ["employer"] };
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
const reviews = [{ id: "61111111-1111-4111-8111-111111111111", project_id: "71111111-1111-4111-8111-111111111111", reviewer_user_id: employerId, freelancer_user_id: freelancerId, rating: 5, comment: "Clear thinking, precise delivery, and excellent communication.", created_at: "2026-07-02T12:00:00+00:00" }];
let gigs = [{
  id: "b1111111-1111-4111-8111-111111111111",
  freelancer_profile_id: profile.id,
  title: "Design an accessible product system",
  description: "A defined service for interaction architecture, accessible components, and delivery guidance.",
  is_active: true,
  packages: [
    { id: "b2111111-1111-4111-8111-111111111111", tier: "BASIC", amount_minor: 120000, currency: "USD", delivery_days: 7, revisions: 1, description: "Core flow and accessibility audit." },
    { id: "b3111111-1111-4111-8111-111111111111", tier: "STANDARD", amount_minor: 240000, currency: "USD", delivery_days: 10, revisions: 2, description: "Audit plus component recommendations." },
  ],
  requirements: [{ id: "b4111111-1111-4111-8111-111111111111", prompt: "Share product goals and existing research.", required: true }],
}];
let projects = [{
  id: "c1111111-1111-4111-8111-111111111111",
  employer_user_id: employerId,
  title: "Rebuild a cross-market checkout",
  description: "Design and validate a checkout architecture that works across multiple regulatory markets.",
  budget_min_minor: 800000,
  budget_max_minor: 1400000,
  currency: "USD",
  status: "OPEN",
  skills: ["Product Design", "Research", "Design Systems"],
}];

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

function json(response, status, value) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(value));
}

function sessionUser(request) {
  const token = request.headers.authorization;
  if (token === "Bearer access-freelancer") return freelancerUser;
  if (token === "Bearer access-employer") return employerUser;
  return null;
}

async function body(request) {
  let value = "";
  for await (const chunk of request) value += chunk;
  return value ? JSON.parse(value) : {};
}

function nextId(prefix, length) {
  return `${prefix}1111111-1111-4111-8111-${String(length + 1).padStart(12, "0")}`;
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:8000");
  const method = request.method ?? "GET";
  if (url.pathname === "/health/live") return json(response, 200, { status: "ok" });
  if (url.pathname === "/api/v1/auth/login" && method === "POST") {
    const input = await body(request);
    const user = input.email === employerUser.email ? employerUser : freelancerUser;
    const role = user.roles[0];
    return json(response, 200, { user, access_token: `access-${role}`, refresh_token: `refresh-${role}`, token_type: "Bearer" });
  }
  if (url.pathname === "/api/v1/auth/me") {
    const user = sessionUser(request);
    return user ? json(response, 200, user) : json(response, 401, { error: { message: "Authentication required" } });
  }
  if (url.pathname === "/api/v1/auth/logout" && method === "POST") {
    return sessionUser(request) ? response.writeHead(204).end() : json(response, 401, { error: { message: "Authentication required" } });
  }
  if (url.pathname === "/api/v1/auth/refresh" && method === "POST") {
    const input = await body(request);
    const role = String(input.refresh_token ?? "").includes("employer") ? "employer" : "freelancer";
    return json(response, 200, { access_token: `access-${role}`, refresh_token: `refresh-${role}`, token_type: "Bearer" });
  }
  if (url.pathname === "/api/v1/search/freelancers") {
    const query = url.searchParams.get("q")?.toLowerCase() ?? "";
    return json(response, 200, { items: query.includes("no-match") ? [] : [searchItem()] });
  }
  if (url.pathname === `/api/v1/freelancers/${freelancerId}` && method === "GET") return json(response, 200, profile);
  if (url.pathname === `/api/v1/freelancers/${freelancerId}/portfolio` && method === "GET") return json(response, 200, { items: portfolio });
  if (url.pathname === `/api/v1/freelancers/${freelancerId}/reviews` && method === "GET") return json(response, 200, { items: reviews });
  if (url.pathname === "/api/v1/gigs" && method === "GET") return json(response, 200, { items: gigs.filter((gig) => gig.is_active) });
  if (url.pathname.startsWith("/api/v1/gigs/") && method === "GET") {
    const id = url.pathname.split("/").at(-1);
    const gig = gigs.find((item) => item.id === id);
    return gig ? json(response, 200, gig) : json(response, 404, { error: { message: "Gig not found" } });
  }
  if (url.pathname === "/api/v1/projects" && method === "GET") return json(response, 200, { items: projects.filter((project) => project.status === "OPEN") });
  if (url.pathname.startsWith("/api/v1/projects/") && method === "GET" && !url.pathname.endsWith("/close")) {
    const id = url.pathname.split("/").at(-1);
    const project = projects.find((item) => item.id === id);
    return project ? json(response, 200, project) : json(response, 404, { error: { message: "Project not found" } });
  }

  const user = sessionUser(request);
  if (!user) return json(response, 401, { error: { message: "Authentication required" } });
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
    const item = { id: nextId("d", portfolio.length), title: input.title, description: input.description ?? "", external_url: input.external_url ?? null, files: [] };
    portfolio = [item, ...portfolio];
    return json(response, 201, item);
  }
  if (url.pathname.startsWith("/api/v1/portfolio/") && method === "DELETE") {
    const id = url.pathname.split("/").at(-1);
    portfolio = portfolio.filter((item) => item.id !== id);
    response.writeHead(204);
    return response.end();
  }
  if (url.pathname === "/api/v1/gigs" && method === "POST" && user.roles.includes("freelancer")) {
    const input = await body(request);
    const gig = { id: nextId("e", gigs.length), freelancer_profile_id: profile.id, is_active: true, ...input, packages: input.packages.map((item, index) => ({ id: nextId("f", gigs.length * 3 + index), ...item })), requirements: input.requirements.map((item, index) => ({ id: nextId("1", gigs.length * 5 + index), ...item })) };
    gigs = [gig, ...gigs];
    return json(response, 201, gig);
  }
  if (url.pathname.startsWith("/api/v1/gigs/") && method === "PUT" && user.roles.includes("freelancer")) {
    const id = url.pathname.split("/").at(-1);
    const input = await body(request);
    const existing = gigs.find((item) => item.id === id);
    if (!existing) return json(response, 404, { error: { message: "Gig not found" } });
    const saved = { ...existing, ...input, packages: input.packages.map((item, index) => ({ id: nextId("2", index), ...item })), requirements: input.requirements.map((item, index) => ({ id: nextId("3", index), ...item })) };
    gigs = gigs.map((item) => item.id === id ? saved : item);
    return json(response, 200, saved);
  }
  if (url.pathname === "/api/v1/projects" && method === "POST" && user.roles.includes("employer")) {
    const input = await body(request);
    const project = { id: nextId("4", projects.length), employer_user_id: employerId, status: "OPEN", ...input };
    projects = [project, ...projects];
    return json(response, 201, project);
  }
  if (url.pathname.startsWith("/api/v1/projects/") && method === "PUT" && user.roles.includes("employer")) {
    const id = url.pathname.split("/").at(-1);
    const input = await body(request);
    const existing = projects.find((item) => item.id === id);
    if (!existing) return json(response, 404, { error: { message: "Project not found" } });
    const saved = { ...existing, ...input };
    projects = projects.map((item) => item.id === id ? saved : item);
    return json(response, 200, saved);
  }
  if (url.pathname.endsWith("/close") && method === "POST" && user.roles.includes("employer")) {
    const id = url.pathname.split("/").at(-2);
    const existing = projects.find((item) => item.id === id);
    if (!existing) return json(response, 404, { error: { message: "Project not found" } });
    const closed = { ...existing, status: "CLOSED" };
    projects = projects.map((item) => item.id === id ? closed : item);
    return json(response, 200, closed);
  }
  return json(response, 404, { error: { message: "Mock route not found" } });
});

server.listen(8000, "127.0.0.1", () => console.log("mock backend listening on 8000"));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
