import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { copyFileSync, mkdirSync } from 'fs';

// https://vitejs.dev/config
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'copy-log-viewer',
      closeBundle() {
        // Copy LogViewer.html to build directory after build
        const src = path.resolve(__dirname, 'src/components/LogViewer.html');
        const dest = path.resolve(__dirname, '.vite/build/renderer/LogViewer.html');
        try {
          mkdirSync(path.dirname(dest), { recursive: true });
          copyFileSync(src, dest);
          console.log('✓ Copied LogViewer.html to build directory');
        } catch (err) {
          console.warn('Failed to copy LogViewer.html:', err);
        }
      },
    },
  ],
  root: path.resolve(__dirname),
  base: './',
  build: {
    outDir: path.resolve(__dirname, '.vite/build/renderer'),
    emptyOutDir: false,
    rollupOptions: {
      input: {
        main_window: path.resolve(__dirname, 'index.html'),
      },
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
