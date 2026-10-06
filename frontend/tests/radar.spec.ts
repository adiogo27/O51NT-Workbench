import { expect, test } from "@playwright/test";

test("radar: tira de status, fontes seedadas, cadastrar fonte e ver aba de resultados", async ({ page }) => {
  await page.goto("/monitors");
  await expect(page.getByRole("heading", { name: "Radar", exact: true })).toBeVisible();
  await expect(page.getByText("monitores ativos", { exact: true })).toBeVisible();
  await expect(page.getByText("fontes ativas", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Fontes do radar" }).click();
  await expect(page.getByText("g1 — política")).toBeVisible();
  await page.getByLabel("Nome da fonte").fill("Fonte de teste");
  await page.getByLabel("URL do feed").fill("https://exemplo.org/feed.xml"); // só cadastro: nenhum acesso à rede
  await page.getByRole("button", { name: "Cadastrar fonte" }).click();
  await expect(page.getByText("Fonte de teste")).toBeVisible();

  await page.getByRole("tab", { name: /^Resultados/ }).click();
  await expect(page.getByText(/Nenhum hit/)).toBeVisible();

  // o formulário de monitor agora expõe o modo de casamento
  await page.getByRole("tab", { name: "Monitores" }).click();
  await expect(page.getByLabel("Casamento no Radar")).toHaveValue("termos");
});
