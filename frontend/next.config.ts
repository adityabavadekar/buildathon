import type { NextConfig } from 'next'

const BACKEND_HOST = process.env.BACKEND_HOST ?? '127.0.0.1'
const BACKEND_PORT = process.env.BACKEND_PORT ?? '8000'

const nextConfig: NextConfig = {
  // eslint-disable-next-line @typescript-eslint/require-await
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Credentials', value: 'true' },
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET,DELETE,PATCH,POST,PUT,OPTIONS' },
          {
            key: 'Access-Control-Allow-Headers',
            value:
              'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, x-request-id',
          },
        ],
      },
      {
        source: '/:path*',
        headers: [
          { key: 'Access-Control-Allow-Credentials', value: 'true' },
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET,DELETE,PATCH,POST,PUT,OPTIONS' },
          {
            key: 'Access-Control-Allow-Headers',
            value:
              'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, x-request-id',
          },
        ],
      },
    ]
  },
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
