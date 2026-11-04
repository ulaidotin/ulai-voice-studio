// Fails if "livekit" appears anywhere in the app source or its dependency manifests.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const targets = ["src", "package.json", "package-lock.json"];
const hits = [];
// This check's own npm script entry is the one allowed mention.
const SELF = /^\s*"check:no-livekit":\s*"node scripts\/check-no-livekit\.mjs",?\s*$/;

function scan(path) {
  if (statSync(path).isDirectory()) {
    for (const entry of readdirSync(path)) scan(join(path, entry));
    return;
  }
  readFileSync(path, "utf8")
    .split("\n")
    .forEach((line, i) => {
      if (/livekit/i.test(line) && !SELF.test(line)) hits.push(`${path}:${i + 1}: ${line.trim().slice(0, 120)}`);
    });
}

for (const t of targets) scan(t);

if (hits.length) {
  console.error(`Found ${hits.length} LiveKit reference(s):\n${hits.join("\n")}`);
  process.exit(1);
}
console.log("No LiveKit references found.");
