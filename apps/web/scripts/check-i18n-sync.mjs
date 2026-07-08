#!/usr/bin/env node
// CI gate (working agreement #4): every en/*.json key must have its ar/*.json sibling and
// vice versa. Machine-drafted Arabic is flagged via "_review": "pending-native".
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "i18n");
const enDir = join(root, "en");
const arDir = join(root, "ar");

let failed = false;

for (const file of readdirSync(enDir).filter((f) => f.endsWith(".json"))) {
  const en = JSON.parse(readFileSync(join(enDir, file), "utf8"));
  let ar;
  try {
    ar = JSON.parse(readFileSync(join(arDir, file), "utf8"));
  } catch {
    console.error(`✗ missing Arabic sibling for i18n/en/${file}`);
    failed = true;
    continue;
  }
  const enKeys = new Set(Object.keys(en).filter((k) => k !== "_review"));
  const arKeys = new Set(Object.keys(ar).filter((k) => k !== "_review"));
  for (const k of enKeys) {
    if (!arKeys.has(k)) {
      console.error(`✗ ${file}: key "${k}" exists in en but not in ar`);
      failed = true;
    }
  }
  for (const k of arKeys) {
    if (!enKeys.has(k)) {
      console.error(`✗ ${file}: key "${k}" exists in ar but not in en`);
      failed = true;
    }
  }
  if (ar._review === "pending-native") {
    console.warn(`⚠ ${file}: Arabic strings are machine-drafted (pending native review)`);
  }
}

if (failed) process.exit(1);
console.log("✓ en/ar i18n catalogs are in sync");
