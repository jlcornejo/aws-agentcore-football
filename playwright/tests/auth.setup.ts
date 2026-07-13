import { test as setup, expect } from '@playwright/test';
import path from 'path';

const AUTH_FILE = path.join(__dirname, '../auth/session.json');

/**
 * Setup: Login al AWS Workshop Event Dashboard.
 *
 * El flujo típico del Workshop Event Dashboard es:
 * 1. Te redirige a la página de login
 * 2. Introduces el Event Access Code (hash del evento)
 * 3. Aceptas términos y condiciones
 * 4. Quedas loggeado en el dashboard
 *
 * IMPORTANTE: Edita EVENT_ACCESS_CODE con el código de tu evento.
 */
setup('login al workshop dashboard', async ({ page }) => {
  const EVENT_ACCESS_CODE = process.env.WORKSHOP_EVENT_CODE || '';

  if (!EVENT_ACCESS_CODE) {
    console.log('⚠️  No se proporcionó WORKSHOP_EVENT_CODE.');
    console.log('   Usa: WORKSHOP_EVENT_CODE=tu-codigo npm run login');
    console.log('   O ejecuta codegen para grabar el flujo manualmente:');
    console.log('   npm run codegen');
  }

  // Navega al dashboard del workshop
  await page.goto('/event/dashboard/en-US/workshop/7-deploy-your-team');

  // Espera a que cargue la página de login o el dashboard
  await page.waitForLoadState('networkidle');

  // --- Flujo de login del Workshop Event ---
  // El formulario puede variar. Usamos selectores genéricos.

  // Si hay un campo de Event Access Code
  const accessCodeInput = page.locator('input[placeholder*="access" i], input[placeholder*="code" i], input[name*="code" i], input[type="text"]').first();

  if (await accessCodeInput.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('📝 Encontrado formulario de Event Access Code');
    await accessCodeInput.fill(EVENT_ACCESS_CODE);

    // Click en el botón de submit/join
    const submitBtn = page.locator('button[type="submit"], button:has-text("Join"), button:has-text("Next"), button:has-text("Submit")').first();
    await submitBtn.click();
    await page.waitForLoadState('networkidle');
  }

  // Si hay checkbox de términos y condiciones
  const termsCheckbox = page.locator('input[type="checkbox"]').first();
  if (await termsCheckbox.isVisible({ timeout: 3000 }).catch(() => false)) {
    console.log('✅ Aceptando términos y condiciones');
    await termsCheckbox.check();

    const acceptBtn = page.locator('button:has-text("Accept"), button:has-text("Agree"), button:has-text("Continue")').first();
    if (await acceptBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await acceptBtn.click();
    }
  }

  // Espera a que el dashboard cargue completamente
  await page.waitForLoadState('networkidle');

  // Toma screenshot para verificar
  await page.screenshot({ path: 'auth/login-result.png', fullPage: true });
  console.log('📸 Screenshot guardado en auth/login-result.png');

  // Guarda la sesión (cookies + localStorage)
  await page.context().storageState({ path: AUTH_FILE });
  console.log('💾 Sesión guardada en auth/session.json');
});
