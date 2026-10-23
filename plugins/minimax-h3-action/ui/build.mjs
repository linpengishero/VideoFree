// Build a dependency-free collaboration module for runtime loading.
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const here = new URL('.', import.meta.url);
const [source, css] = await Promise.all([
  readFile(new URL('./Collaboration.js', here), 'utf8'),
  readFile(new URL('./Collaboration.css', here), 'utf8'),
]);
await mkdir(new URL('./dist/', here), { recursive: true });
await writeFile(new URL('./dist/collaboration.js', here),
  `const H3A_STYLES = ${JSON.stringify(css)};\n${source}`, 'utf8');
