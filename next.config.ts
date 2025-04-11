import type {NextConfig} from 'next';

const nextConfig: NextConfig = {
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  distDir: 'dist',
  assetPrefix: '.',
  webpack: (config, options) => {
    config.module.rules.push({
      test: /\.(woff|woff2|otf)$/,
      use: [
        {
          loader: 'file-loader',
          options: {
            outputPath: 'static/fonts',
            publicPath: '/_next/static/fonts',
            name: '[name].[ext]',
          },
        },
      ],
    });
    return config;
  },
};

export default nextConfig;
