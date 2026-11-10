module.exports = {
  testEnvironment: 'jsdom',
  rootDir: '../../',
  testMatch: ['**/tests/browser-extension/**/*.test.js'],
  testTimeout: 10000,
  verbose: true,
  setupFilesAfterEnv: ['<rootDir>/tests/browser-extension/setup.js'],
};
