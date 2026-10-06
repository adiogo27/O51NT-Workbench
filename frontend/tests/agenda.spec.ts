import { expect, test } from "@playwright/test";

test("agenda: cadastrar compromisso com impacto em rodovia, ver queries e criar monitor", async ({ page }) => {
  await page.goto("/agenda");
  await page.getByLabel("Dia", { exact: true }).fill("2026-10-03");

  await page.getByLabel("Candidato(a)").fill("Candidato A");
  await page.getByLabel("Partido").fill("XYZ");
  await page.getByLabel("Tipo", { exact: true }).selectOption("carreata");
  await page.getByLabel("Título").fill("Carreata de encerramento");
  await page.getByLabel("Data", { exact: true }).fill("2026-10-03");
  await page.getByLabel("Início (HH:MM)").fill("14:30");
  await page.getByLabel("Cidade").fill("Americana");
  await page.getByLabel("UF", { exact: true }).selectOption("SP");
  await page.getByLabel("Rodovias federais envolvidas").fill("br 116");
  await page.getByLabel("Rodovias federais envolvidas").press("Enter");
  await page.getByLabel("Poderá impactar o fluxo viário em rodovia federal").check();
  await page.getByRole("button", { name: "Cadastrar compromisso" }).click();

  // o cartão completo (lista do dia) tem o botão "Queries"; a linha de "Próximos 7 dias" não
  const card = page
    .getByRole("listitem")
    .filter({ hasText: "Carreata de encerramento" })
    .filter({ has: page.getByRole("button", { name: "Queries" }) });
  await expect(card).toBeVisible();
  await expect(card.getByText("impacto em rodovia federal")).toBeVisible();
  await expect(card.getByText("BR-116")).toBeVisible(); // normalizada

  await card.getByRole("button", { name: "Queries" }).click();
  await expect(card.getByText(/\(BR-116 OR "BR 116" OR BR116\)/).first()).toBeVisible();
  await expect(card.getByText(/after:2026-10-02/)).toBeVisible();
  await expect(card.getByText(/-is:retweet since:2026-10-02/)).toBeVisible();

  await card.getByRole("button", { name: "Monitorar" }).click();
  await expect(card.getByText(/monitor #\d+/)).toBeVisible();

  // aparece na lista de impacto nos próximos 7 dias
  await expect(page.getByRole("heading", { name: "Próximos 7 dias com impacto em rodovia federal" })).toBeVisible();
});
