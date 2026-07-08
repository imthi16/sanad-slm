#!/usr/bin/env node
// Sovereign gate (`just verify-no-cdn`, CLAUDE.md §4): no external origins in web dist/.
//
// Two tiers:
//  1. HTML + CSS — FETCHABLE contexts (link/img/font/@import/url()): ZERO external origins
//     tolerated. Any hit is a hard fail.
//  2. JS — string scan with an explicit allowlist of origins proven inert (each justified
//     below). Anything not allowlisted is a hard fail.
//
// Runtime backstops (defense in depth, §10): nginx CSP `default-src 'self'` blocks any
// attempted fetch these strings could make, and the sovereign compose network is
// `internal: true`. This gate keeps the *build* honest; those keep the runtime honest.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const dist = process.argv[2] ?? "dist";

// JS-only allowlist — every entry needs a reason:
const JS_ALLOWLIST = new Map([
  // framework error-decoder / docs links embedded in minified error messages; never fetched
  ["react.dev", "React error-decoder URLs in error strings"],
  ["reactrouter.com", "react-router docs links in error strings"],
  ["tailwindcss.com", "tailwind docs links in error strings"],
  ["github.com", "library issue-tracker links in error strings"],
  ["docs.pmnd.rs", "react-three-fiber docs links in error strings"],
  // troika-three-text's fallback-font resolver base. Unreachable in Sanad: every <Text>
  // passes a self-hosted woff (see PipelineOrbit), and CSP font-src/connect-src are 'self'.
  ["cdn.jsdelivr.net", "troika fallback-font resolver default, disabled by explicit font= props"],
]);

const URL_RE = /https?:\/\/([a-zA-Z0-9.-]+)/g;
const IGNORED_HOSTS = new Set(["localhost", "127.0.0.1", "www.w3.org"]); // w3.org = xmlns only

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else yield p;
  }
}

let failed = false;
const seen = { html_css: new Set(), js_blocked: new Set(), js_allowed: new Set() };

for (const file of walk(dist)) {
  const isJs = file.endsWith(".js");
  const isHtmlCss = file.endsWith(".html") || file.endsWith(".css");
  if (!isJs && !isHtmlCss) continue;
  let content = readFileSync(file, "utf8");
  if (isHtmlCss) {
    // license banners / html comments are not fetchable — scan only live markup/rules
    content = content.replace(/\/\*[\s\S]*?\*\//g, "").replace(/<!--[\s\S]*?-->/g, "");
  }
  for (const match of content.matchAll(URL_RE)) {
    const host = match[1];
    if (IGNORED_HOSTS.has(host)) continue;
    if (isHtmlCss) {
      seen.html_css.add(host);
      failed = true;
    } else if (JS_ALLOWLIST.has(host)) {
      seen.js_allowed.add(host);
    } else {
      seen.js_blocked.add(host);
      failed = true;
    }
  }
}

for (const host of seen.html_css) {
  console.error(`✗ HTML/CSS references external origin (fetchable context): ${host}`);
}
for (const host of seen.js_blocked) {
  console.error(`✗ JS references non-allowlisted external origin: ${host}`);
}
for (const host of seen.js_allowed) {
  console.warn(`· allowed inert JS string: ${host} — ${JS_ALLOWLIST.get(host)}`);
}

if (failed) {
  console.error("✗ verify-no-cdn FAILED — sovereign build must not reference external origins");
  process.exit(1);
}
console.log("✓ no fetchable external origins in dist/ (sovereign gate)");
