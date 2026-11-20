import path from 'node:path'
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(__dirname, '..'),
  },
  images: {
    unoptimized: true,
  },

  // Browser only ever calls /api/*, /static/* (voice notes, .ics); both are proxied to the FastAPI backend.
  async rewrites() {
    const backendUrl = process.env.AGENT_BACKEND_URL?.replace(/\/$/, '')
    if (!backendUrl) {
      return []
    }
    return [
      { source: '/api/:path*', destination: `${backendUrl}/:path*` },
      { source: '/static/:path*', destination: `${backendUrl}/static/:path*` },
    ]
  },
}

export default nextConfig
