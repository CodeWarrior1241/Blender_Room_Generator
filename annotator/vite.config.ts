import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// `room_gen annotate` serves dist/ at `/` and the JSON API at `/api` (room_gen/server.py).
// In development run `room_gen annotate --port 5174 --no-open` and `npm run dev`.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5174',
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
