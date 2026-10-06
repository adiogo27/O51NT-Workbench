import { expect, test } from "@playwright/test";

test("boletim: adicionar notícia, ver na prévia, cadastrar perfil e ver menções", async ({ page }) => {
  await page.goto("/boletim");
  await page.getByLabel("Dia do boletim").fill("2026-10-02");

  await page.getByLabel("Seção").selectOption("noticia");
  await page.getByLabel("Título / manchete").fill("PRF promete livre deslocamento do eleitor");
  await page.getByLabel("URL").fill("https://exemplo.org/noticia");
  await page.getByLabel("Fonte / veículo").fill("Metrópoles");
  await page.getByRole("button", { name: "Adicionar item" }).click();

  const noticias = page.getByRole("heading", { name: /^Notícias relevantes/ }).locator("..");
  await expect(noticias.getByRole("link", { name: "PRF promete livre deslocamento do eleitor" })).toBeVisible();
  await expect(page.getByText("INFORMAÇÕES RELEVANTES - 02 OUT 2026 (sexta-feira)").first()).toBeVisible();
  await expect(page.locator("pre")).toContainText("## NOTÍCIAS RELEVANTES\n- **PRF promete livre deslocamento do eleitor** (Metrópoles) — https://exemplo.org/noticia");

  await page.getByRole("tab", { name: "Perfis vigiados" }).click();
  await page.getByLabel("Rede").selectOption("x");
  await page.getByLabel("Usuário ou URL do perfil").fill("https://x.com/PRFBrasil");
  await page.getByLabel("Rótulo").fill("PRF Brasil");
  await page.getByLabel("Categoria").selectOption("institucional");
  await page.getByRole("button", { name: "Cadastrar perfil" }).click();

  const linha = page.getByRole("listitem").filter({ hasText: "PRF Brasil" });
  await expect(linha.getByRole("link", { name: "https://x.com/PRFBrasil" })).toBeVisible();
  await linha.getByRole("button", { name: "Menções" }).click();
  await expect(linha.getByText(/\(from:PRFBrasil OR @PRFBrasil\) -is:retweet since:/)).toBeVisible();
  await expect(linha.getByRole("button", { name: /^Abrir no X \(recentes\)/ })).toBeVisible();
});
