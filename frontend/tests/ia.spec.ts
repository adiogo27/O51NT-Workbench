import { expect, test } from "@playwright/test";

test("assistente de IA: página, faixa de status, abas e opção IA nos alertas", async ({ page }) => {
  await page.goto("/ia");
  await expect(page.getByRole("heading", { name: "Assistente de IA", exact: true })).toBeVisible();
  await expect(page.getByText("na fila", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("desligado em Tema")).toBeVisible();
  await page.getByRole("tab", { name: /^Aprovações/ }).click();
  await expect(page.getByText("Nada aguardando aprovação.")).toBeVisible();
  await page.getByRole("tab", { name: "Custo" }).click();
  await expect(page.getByText(/Custo \(14 dias\)/)).toBeVisible();

  await page.goto("/alertas");
  await expect(page.getByLabel("Tipo").locator("option", { hasText: "IA" })).toHaveCount(1);

  await page.goto("/monitors");
  await page.getByRole("tab", { name: "Fontes do radar" }).click();
  await expect(page.getByLabel("Tipo da fonte")).toHaveValue("feed");
  await page.getByLabel("Tipo da fonte").selectOption("pagina");
  await expect(page.getByLabel("URL da página")).toBeVisible();
});
