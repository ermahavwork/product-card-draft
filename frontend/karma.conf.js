module.exports = (config) => config.set({
  frameworks: ['jasmine'],
  plugins: [require('karma-jasmine'), require('karma-chrome-launcher')],
  reporters: ['progress'],
  browsers: ['Headless'],
  customLaunchers: { Headless: { base: 'ChromeHeadless', flags: ['--no-sandbox'] } },
  restartOnFileChange: false,
});
