import { test, expect } from '@playwright/test';

/**
 * Test que verifica acceso al Workshop Dashboard después del login.
 * Depende del setup (auth.setup.ts) para tener sesión válida.
 */
test.describe('Workshop Dashboard', () => {
  test('accede al paso 7 - Deploy Your Team', async ({ page }) => {
    await page.goto('/event/dashboard/en-US/workshop/7-deploy-your-team');
    await page.waitForLoadState('networkidle');

    // Verifica que estamos en el contenido del workshop (no en login)
    // Ajusta este selector según el contenido real de la página
    const content = page.locator('main, [role="main"], .content, article').first();
    await expect(content).toBeVisible({ timeout: 15000 });

    // Screenshot de verificación
    await page.screenshot({ path: 'screenshots/deploy-your-team.png', fullPage: true });
    console.log('📸 Screenshot: screenshots/deploy-your-team.png');
  });

  test('extrae credenciales AWS del dashboard', async ({ page }) => {
    // Los workshops suelen mostrar credenciales en la sección de "Get AWS CLI credentials"
    await page.goto('/event/dashboard/en-US/workshop/7-deploy-your-team');
    await page.waitForLoadState('networkidle');

    // Busca secciones con credenciales AWS
    const credSection = page.locator('text=/AWS_ACCESS_KEY|credentials|CLI/i').first();

    if (await credSection.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('🔑 Sección de credenciales encontrada');

      // Intenta copiar/extraer las credenciales
      const pageContent = await page.textContent('body');
      const accessKeyMatch = pageContent?.match(/AWS_ACCESS_KEY_ID[=:]\s*["']?(\w+)/);
      if (accessKeyMatch) {
        console.log(`   Access Key: ${accessKeyMatch[1].substring(0, 8)}...`);
      }
    }

    await page.screenshot({ path: 'screenshots/credentials.png', fullPage: true });
  });
});
