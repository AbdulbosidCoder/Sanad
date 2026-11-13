// Parses every ```mermaid block in the given Markdown files and fails on syntax errors.
// Usage: node check-mermaid.mjs <file.md> [...]
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const dom = new JSDOM('<!doctype html><body></body>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
for (const k of ['Element', 'HTMLElement', 'Node', 'DocumentFragment']) globalThis[k] = dom.window[k];

const mermaid = (await import('mermaid')).default;
mermaid.initialize({ startOnLoad: false });

let total = 0;
let failed = 0;
for (const file of process.argv.slice(2)) {
  const text = fs.readFileSync(file, 'utf8');
  for (const match of text.matchAll(/```mermaid\r?\n([\s\S]*?)```/g)) {
    total++;
    const line = text.slice(0, match.index).split('\n').length;
    try {
      await mermaid.parse(match[1]);
    } catch (err) {
      failed++;
      const msg = String(err?.message ?? err).split('\n').slice(0, 4).join(' ');
      console.log(`::error file=${file},line=${line}::Mermaid syntax error: ${msg}`);
    }
  }
}
console.log(`Mermaid: checked ${total} diagram(s), ${failed} failed.`);
process.exit(failed ? 1 : 0);
