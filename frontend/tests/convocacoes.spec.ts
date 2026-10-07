import { expect, test } from "@playwright/test";

// PNG 1x1 válido (a análise só por texto não depende do OCR; a imagem garante o caminho de upload/evidência)
const PNG_1x1 = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("convocações: analisar texto de cartaz gera detecção crítica, alerta na inbox e convite registrado", async ({ page }) => {
  await page.goto("/convocacoes");
  await expect(page.getByRole("heading", { level: 1, name: "Convocações" })).toBeVisible();
  await expect(page.getByText("críticas na fila", { exact: true })).toBeVisible();

  await page.getByLabel("Texto do post / legenda (opcional)").fill(
    "GRITO DOS EXCLUÍDOS — REVOLTA NAS RUAS — DIA 11 DE OUTUBRO EM BELO HORIZONTE, MINAS GERAIS — ATO NÃO PACÍFICO. Grupo: chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM",
  );
  await page.locator("#conv-file").setInputFiles({ name: "cartaz.png", mimeType: "image/png", buffer: PNG_1x1 });
  await page.getByRole("button", { name: "Analisar", exact: true }).click();

  // 1ª análise carrega o OCR (e baixa os modelos se o diretório estiver vazio): tolerância maior
  await expect(page.getByText(/Léxico \(OCR \+ texto\)/)).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText("CRÍTICA", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("ato nao pacifico", { exact: true })).toBeVisible();
  await expect(page.getByText(/chat\.whatsapp\.com\/GM4b5kGzIFm36GoyM7AOlM/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /alerta #\d+/ })).toBeVisible();

  // fila mostra a detecção com data/local extraídos
  await page.getByRole("tab", { name: /^Fila/ }).click();
  await expect(page.getByText(/11\/10\/2026/).first()).toBeVisible();
  await expect(page.getByText(/Belo Horizonte\/MG/).first()).toBeVisible();

  // inbox de alertas + badge no menu
  await expect(page.getByLabel(/alerta\(s\) não lido\(s\)/)).toBeVisible();
  await page.getByRole("link", { name: /Alertas/ }).click();
  await expect(page.getByText("Convocação", { exact: true })).toBeVisible();
  await expect(page.getByText(/ATO NÃO PACÍFICO/).first()).toBeVisible();

  // convite extraído do texto do cartaz aparece em Convites com status desconhecido e botão Testar
  await page.goto("/invites");
  await expect(page.getByText("chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM").first()).toBeVisible();
  await expect(page.getByText("desconhecido").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Testar$/ }).first()).toBeVisible();
});

test("convocações: fontes — validação de canal do Telegram e cadastro de busca no Bluesky", async ({ page }) => {
  await page.goto("/convocacoes");
  await page.getByRole("tab", { name: "Fontes" }).click();
  await page.getByLabel("Tipo").selectOption("telegram_canal");
  await page.getByLabel("Parâmetro (termo, @canal ou dork)").fill("a b");
  await page.getByRole("button", { name: "Cadastrar fonte" }).click();
  await expect(page.getByText(/canal do Telegram inválido/)).toBeVisible();

  await page.getByLabel("Tipo").selectOption("bluesky_busca");
  await page.getByLabel("Parâmetro (termo, @canal ou dork)").fill("ato não pacífico");
  await page.getByRole("button", { name: "Cadastrar fonte" }).click(); // só cadastro: nenhum acesso à rede
  await expect(page.getByText(/Bluesky — busca: ato não pacífico/)).toBeVisible();
});
