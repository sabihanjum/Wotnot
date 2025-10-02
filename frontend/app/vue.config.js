const webpack = require('webpack');

module.exports = {
  publicPath: '/',

  configureWebpack: {
    plugins: [
      new webpack.DefinePlugin({
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: JSON.stringify(true)
      }),
    ],
  },

  chainWebpack: config => {
    const vueRule = config.module.rule('vue').use('vue-loader');
    vueRule.tap(options => {
      options.compilerOptions = options.compilerOptions || {};
      // You can put other compilerOptions here.
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
      // Remove webSocketURL to use default local ws endpoint if needed.
    },
  },
};
