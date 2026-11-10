/**
 * Jest 配置文件 — 简洁模式自动轮询引擎单元测试
 *
 * 运行方式：
 *   npx jest --config tests/compact-poll/jest.config.js
 *   npx jest --config tests/compact-poll/jest.config.js --coverage
 */

module.exports = {
  // 使用 jsdom 模拟浏览器环境
  testEnvironment: 'jsdom',

  // 根目录为项目根目录（tests/compact-poll/ 的上两级）
  rootDir: '../../',

  // 只匹配 compact-poll 目录下的测试文件
  testMatch: ['**/tests/compact-poll/**/*.test.js'],

  // 单个测试超时时间
  testTimeout: 10000,

  // 详细输出每个用例的结果
  verbose: true,

  // 在每个测试文件执行前加载全局 Mock 和轮询引擎
  setupFilesAfterEnv: ['<rootDir>/tests/compact-poll/setup.js'],
};
