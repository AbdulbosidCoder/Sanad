// Checks that relative links in Markdown files point to existing files.
// External (http/https/mailto) links and pure #anchors are skipped.
// Usage: node check-links.mjs <file.md> [...]
import fs from 'node:fs';
import path from 'node:path';

let broken = 0;
let total = 0;
for (const file of process.argv.slice(2)) {
  const text = fs.readFileSync(file, 'utf8').replace(/```[\s\S]*?```/g, '');
  for (const match of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    const target = match[1];
    if (/^(https?:|mailto:|#)/.test(target)) continue;
    total++;
    const resolved = path.resolve(path.dirname(file), decodeURIComponent(target.split('#')[0]));
    if (!fs.existsSync(resolved)) {
      broken++;
      console.log(`::error file=${file}::Broken link: ${target}`);
    }
  }
}
console.log(`Links: checked ${total} relative link(s), ${broken} broken.`);
process.exit(broken ? 1 : 0);
