const webpack = require('webpack');

module.exports = {
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
      // ...existing code...
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
    // Correct websocket config for dev-client:
    // If you use ngrok with HTTPS, point client.webSocketURL to the ngrok host on port 443 (wss).
    // Replace the hostname below with your ngrok host if needed.
    client: {
      webSocketURL: {
        protocol: 'wss',
        hostname: '5543-2405-201-3004-d09d-e838-3470-27b1-6b78.ngrok-free.app.ngrok.io',
        port: 443,
        pathname: '/ws'
      }
      // Alternatively remove webSocketURL entirely to use the default local ws endpoint.
    },
  },
};