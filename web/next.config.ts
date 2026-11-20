import path from 'node:path'
import type { NextConfig } from 'next'

// STATIC_EXPORT=1 builds a static site served by FastAPI itself (one container, no Node at runtime).
const staticExport = process.env.STATIC_EXPORT === '1'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(__dirname, '..'),
  },
  images: {
    unoptimized: true,
  },
  ...(staticExport ? { output: 'export' as const, trailingSlash: true } : {}),

  // Dev: the browser only calls /api/* and /static/*; both are proxied to the FastAPI backend.
  // (Rewrites are unsupported with `output: export`; in production FastAPI serves /api and /static itself.)
  async rewrites() {
    const backendUrl = process.env.AGENT_BACKEND_URL?.replace(/\/$/, '')
    if (staticExport || !backendUrl) {
      return []
    }
    return [
      { source: '/api/:path*', destination: `${backendUrl}/:path*` },
      { source: '/static/:path*', destination: `${backendUrl}/static/:path*` },
    ]
  },
}

export default nextConfig
