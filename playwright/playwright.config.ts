import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: 'https://catalog.us-east-1.prod.workshops.aws',
    trace: 'on-first-retry',
    screenshot: 'on',
    video: 'on',
    // Mantiene la sesión entre tests
    storageState: './auth/session.json',
  },
  projects: [
    // Proyecto de setup: hace login y guarda la sesión
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
      use: {
        storageState: undefined, // No usa sesión previa
      },
    },
    // Proyecto principal: usa la sesión guardada
    {
      name: 'workshop',
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
});
