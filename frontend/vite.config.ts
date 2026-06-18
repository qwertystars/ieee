import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    chunkSizeWarningLimit: 1000, // maplibre-gl is ~800 KB minified; that's expected
    rollupOptions: {
      output: {
        manualChunks: {
          // maplibre-gl is ~1MB — isolate it so app chunk stays small
          maplibre: ['maplibre-gl'],
          vendor: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'axios'],
        },
      },
    },
  },
})
