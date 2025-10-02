const webpack = require('webpack');

module.exports = {
  // This sets the public path for production (important for GitHub Pages or subdomain hosting!)
  publicPath: process.env.NODE_ENV === 'production'
    ? '/<REPO_NAME>/'   // <-- Replace <REPO_NAME> with your repository/project name for GitHub Pages, or '/' if deploying at root
    : '/',

  configureWebpack: {
    plugins: [
      new webpack.DefinePlugin({
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: JSON.stringify(true),
      }),
    ],
  },

  chainWebpack: config => {
    const vueRule = config.module.rule('vue').use('vue-loader');
    vueRule.tap(options => {
      options.compilerOptions = options.compilerOptions || {};
      // ... insert any additional compilerOptions here ...
      return options;
    });
  },

  devServer: {
    allowedHosts: 'all',
    proxy: {
      '/api': {
        target: process.env.VUE_APP_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
    client: {
      webSocketURL: {
        protocol: 'wss',
        hostname: '5543-2405-201-3004-d09d-e838-3470-27b1-6b78.ngrok-free.app.ngrok.io',
        port: 443,
        pathname: '/ws'
      }
      // Alternatively remove webSocketURL to use the default local ws endpoint.
    },
  },
};
