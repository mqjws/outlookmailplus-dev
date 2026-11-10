/**
 * Jest 配置文件 - 布局系统测试
 */

module.exports = {
  // 测试环境
  testEnvironment: 'jsdom',

  // 根目录
  rootDir: '../../',

  // 测试文件匹配模式
  testMatch: [
    '**/tests/layout-system/unit/**/*.test.js',
    '**/tests/layout-system/integration/**/*.test.js',
    '**/tests/layout-system/performance/**/*.test.js',
    '**/tests/layout-system/accessibility/**/*.test.js'
  ],

  // 覆盖率配置
  collectCoverage: true,
  coverageDirectory: 'tests/layout-system/coverage',
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80
    }
  },

  // 覆盖率收集范围
  collectCoverageFrom: [
    'static/js/layout-manager.js',
    'static/js/state-manager.js',
    '!**/node_modules/**',
    '!**/tests/**'
  ],

  // 设置超时时间
  testTimeout: 10000,

  // 详细输出
  verbose: true,

  // 模拟 localStorage
  setupFilesAfterEnv: ['<rootDir>/tests/layout-system/setup.js']
};
