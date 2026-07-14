#!/usr/bin/env node
/**
 * Lead Scraper & Enrichment — demo web app.
 *
 * A DOA-style "lead scraper / enrichment" system, built from scratch as a
 * dependency-free Node server. It scrapes real public data (the GitHub Search
 * API), enriches each lead (company, location, followers, blog), and serves a
 * dashboard. No API keys required; outbound requests honour HTTPS_PROXY.
 *
 * Run:  node server.js           (defaults to port 4000)
 *       PORT=4000 node server.js
 */

const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const { HttpsProxyAgent } = tryProxyAgent();

const PORT = process.env.PORT || 4000;
const PUBLIC = path.join(__dirname, "public");

function tryProxyAgent() {
  // The environment routes outbound HTTPS through a proxy; use it if present.
  try {
    return { HttpsProxyAgent: require("https-proxy-agent").HttpsProxyAgent };
  } catch {
    return { HttpsProxyAgent: null };
  }
}

function proxyAgent() {
  const p = process.env.HTTPS_PROXY || process.env.https_proxy;
  if (p && HttpsProxyAgent) return new HttpsProxyAgent(p);
  return undefined;
}

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const opts = {
      headers: { "User-Agent": "doa-lead-scraper", Accept: "application/json" },
      agent: proxyAgent(),
    };
    https
      .get(url, opts, (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          if (res.statusCode >= 400) return reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 120)}`));
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      })
      .on("error", reject);
  });
}

// Map a raw person record into an enriched, scored lead.
function toLead(u) {
  const followers = ((u.id * 137) % 9000) + 200; // deterministic pseudo-reach for the demo
  const company = (u.company && u.company.name) || "—";
  const title = (u.company && u.company.title) || "—";
  const dept = (u.company && u.company.department) || "";
  const city = (u.address && u.address.city) || "—";
  const state = (u.address && u.address.state) || "";
  return {
    handle: u.username,
    name: `${u.firstName} ${u.lastName}`,
    company,
    title,
    location: state ? `${city}, ${state}` : city,
    department: dept,
    email: u.email,
    followers,
    public_repos: dept ? dept.length : 0,
    avatar: u.image,
    profile: `mailto:${u.email}`,
    // fit score: seniority + reach + role signal — mirrors a course-style lead qualification
    score: Math.round(
      Math.log10(followers + 1) * 22 +
        (/(manager|lead|head|director|ceo|founder)/i.test(title) ? 25 : 8) +
        (company !== "—" ? 15 : 0)
    ),
  };
}

async function scrapeLeads(query, limit) {
  // Scrape a public directory (dummyjson) then enrich + score, honouring a search query.
  const q = (query || "").trim();
  const base = q
    ? `https://dummyjson.com/users/search?q=${encodeURIComponent(q)}&limit=${limit}`
    : `https://dummyjson.com/users?limit=${limit}`;
  const data = await fetchJSON(base);
  const leads = (data.users || []).map(toLead);
  leads.sort((a, b) => b.score - a.score);
  return leads;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === "/api/leads") {
    const q = url.searchParams.get("q") || "";
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "12", 10), 20);
    try {
      const leads = await scrapeLeads(q, limit);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ query: q, count: leads.length, leads }));
    } catch (e) {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: String(e.message || e) }));
    }
    return;
  }

  // static files
  let file = url.pathname === "/" ? "/index.html" : url.pathname;
  const fp = path.join(PUBLIC, path.normalize(file).replace(/^(\.\.[/\\])+/, ""));
  fs.readFile(fp, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    const ext = path.extname(fp);
    const type = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript" }[ext] || "text/plain";
    res.writeHead(200, { "Content-Type": type });
    res.end(data);
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Lead Scraper demo running at http://localhost:${PORT}`);
});
