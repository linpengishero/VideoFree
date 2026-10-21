import { defineConfig } from 'astro/config';
import { remarkNote } from './src/lib/remarkNote.js';

export default defineConfig({
  site: 'https://videofreestudio.com',
  trailingSlash: 'ignore',
  build: { inlineStylesheets: 'auto' },
  markdown: {
    remarkPlugins: [remarkNote],
  },
});
