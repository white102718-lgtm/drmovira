import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // The desk is served by the canvas app as a same-origin static sub-application.
  base: '/director-desk/',
  build: {
    emptyOutDir: true,
    outDir: '../public/director-desk',
  },
  // This independent React app uses plain CSS. Do not inherit the Vue app's
  // workspace PostCSS pipeline, which is irrelevant to the embedded bundle.
  css: {
    postcss: {
      plugins: [],
    },
  },
  assetsInclude: ['**/*.fbx', '**/*.obj'],
  plugins: [react()],
  server: {
    fs: {
      allow: [
        decodeURIComponent(new URL('.', import.meta.url).pathname),
        decodeURIComponent(new URL('../模型库', import.meta.url).pathname),
      ],
    },
  },
});
