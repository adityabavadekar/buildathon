import type { NextConfig } from 'next'

const BACKEND_HOST = process.env.BACKEND_HOST ?? '127.0.0.1'
const BACKEND_PORT = process.env.BACKEND_PORT ?? '8000'

const nextConfig: NextConfig = {
  // Rewrites proxy backend requests during local development
  // eslint-disable-next-line @typescript-eslint/require-await
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://${BACKEND_HOST}:${BACKEND_PORT}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
