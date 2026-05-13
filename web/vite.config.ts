import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Proxies /api → localhost:8090 so the React dev server can hit the
// aria-dashboard aiohttp app (started via `python -m aria.simulator.web_dashboard
// --port 8090`). Earlier dev configs used :8765, which no longer matches a
// running service and produced opaque 500s in the browser; :8090 is the
// canonical local dashboard port.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8090',
      '/lib': 'http://localhost:8090',
    },
  },
  // satellite.js@7 ships top-level `await` in its WASM pthreads loader.
  // The Vite default target list (chrome87/edge88/firefox78/safari14)
  // pre-dates top-level await and esbuild refuses to bundle it — the
  // dev server then serves a stale broken pre-bundle and the page is
  // blank. esnext lifts the restriction; modern browsers support it.
  optimizeDeps: {
    esbuildOptions: { target: 'esnext' },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'esnext',
    // Split vendor chunks so Three.js (800 KB) doesn't reload on app changes
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-three': ['three', 'three-stdlib'],
          'vendor-r3f': ['@react-three/fiber', '@react-three/drei'],
          'vendor-react': ['react', 'react-dom'],
        },
      },
    },
  },
});
