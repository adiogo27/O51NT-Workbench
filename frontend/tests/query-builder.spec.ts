import { expect, test } from "@playwright/test";

test("montar query → abrir no Google registra histórico e abre o deeplink", async ({ page, context }) => {
  // Nenhum tráfego real ao Google: a aba aberta recebe uma resposta falsa.
  await context.route("https://www.google.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>google-fake</title>" }),
  );

  await page.goto("/query");
  await expect(page.getByRole("heading", { name: "Query Builder" })).toBeVisible();
  await page.getByRole("button", { name: "Limpar", exact: true }).first().click();

  // Precisão: termo + frase exata; Temporal: after
  await page.getByLabel("Termos (E)").fill("PRF");
  await page.getByLabel("Termos (E)").press("Enter");
  await page.getByLabel('Frases exatas ("…")').fill("Polícia Rodoviária Federal");
  await page.getByLabel('Frases exatas ("…")').press("Enter");
  await page.getByLabel("after: (posterior a)").fill("2026-10-01");

  const preview = page.locator("output");
  const esperado = '"Polícia Rodoviária Federal" PRF after:2026-10-01';
  await expect(preview).toHaveText(esperado);
  await expect(page.getByText("Query válida.")).toBeVisible();

  const [popup] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("button", { name: /^Abrir no Google(?! Notícias)/ }).click(),
  ]);
  await popup.waitForLoadState();
  const url = new URL(popup.url());
  expect(url.hostname).toBe("www.google.com");
  expect(url.pathname).toBe("/search");
  expect(url.searchParams.get("q")).toBe(esperado);

  // o clique gravou o histórico no backend (outros testes paralelos também gravam: procura a entrada, não exige a 1ª)
  await expect
    .poll(async () => {
      const h = (await (await page.request.get("/api/query/history")).json()) as { query: string; motor: string }[];
      return h.some((x) => x.query === esperado && x.motor === "google");
    })
    .toBe(true);
});

test("validador aponta janela temporal vazia", async ({ page }) => {
  await page.goto("/query");
  await page.getByRole("button", { name: "Limpar", exact: true }).first().click();
  await page.getByLabel("Termos (E)").fill("PRF");
  await page.getByLabel("Termos (E)").press("Enter");
  await page.getByLabel("after: (posterior a)").fill("2026-10-10");
  await page.getByLabel("before: (anterior a)").fill("2026-10-01");
  await expect(page.getByRole("alert").filter({ hasText: "janela vazia" })).toBeVisible();
});

test("busca via SearXNG fica desabilitada quando a query usa operadores do Google", async ({ page }) => {
  await page.goto("/query");
  await page.getByRole("button", { name: "Limpar", exact: true }).first().click();
  await page.getByLabel("Termos (E)").fill("PRF");
  await page.getByLabel("Termos (E)").press("Enter");
  await page.getByRole("tab", { name: "Scraping ético" }).click();
  const botao = page.getByRole("button", { name: "Buscar via SearXNG" });
  await expect(botao).toBeEnabled();

  await page.getByRole("tab", { name: "Deeplinks" }).click();
  await page.getByLabel("after: (posterior a)").fill("2026-10-01");
  await expect(page.locator("output")).toHaveText("PRF after:2026-10-01");
  await page.getByRole("tab", { name: "Scraping ético" }).click();
  await expect(botao).toBeDisabled();
  await expect(page.getByText("Operadores do Google não são respeitados por outros motores. Use o deeplink.")).toBeVisible();
  await expect(page.locator('span[title^="Operadores do Google"]')).toHaveCount(1);
});

test("aba Convites: deeplinks do PDF + busca via SearXNG habilitada com consultas simples (v2)", async ({ page }) => {
  await page.goto("/invites");
  await page.getByLabel("Termo a ser pesquisado").fill("eleições");
  await expect(page.getByRole("button", { name: /^Abrir no Google(?! Notícias)/ }).first()).toBeVisible(); // subaba Deeplinks
  await page.getByRole("tab", { name: "Scraping ético" }).click();
  // v2: ao SearXNG vão consultas geradas pelo backend só com `site:` e aspas (Bing/DDG honram) → botão habilitado
  await expect(page.getByText(/Consultas que serão enviadas/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Buscar convites via SearXNG" })).toBeEnabled();
  await expect(page.getByText("Operadores do Google não são respeitados por outros motores. Use o deeplink.")).toHaveCount(0);
});

test("painel X/TweetDeck: since + -is:retweet entram na query e abrem o deeplink do X", async ({ page, context }) => {
  await context.route("https://x.com/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>x-fake</title>" }));
  await page.goto("/query");
  await page.getByRole("button", { name: "Limpar", exact: true }).first().click();
  await page.getByLabel("Termos (E)").fill("PRF");
  await page.getByLabel("Termos (E)").press("Enter");
  await page.getByLabel("since: (a partir de)").fill("2026-10-04");
  await page.getByLabel("Excluir retweets (-is:retweet)").check();
  await expect(page.locator("output")).toHaveText("PRF -is:retweet since:2026-10-04");

  const [popup] = await Promise.all([context.waitForEvent("page"), page.getByRole("button", { name: /^Abrir no X \(recentes\)/ }).click()]);
  await popup.waitForLoadState();
  const url = new URL(popup.url());
  expect(url.hostname).toBe("x.com");
  expect(url.searchParams.get("q")).toBe("PRF -is:retweet since:2026-10-04");
  expect(url.searchParams.get("f")).toBe("live");

  // operadores do X também desabilitam a busca via SearXNG, com a mensagem própria
  await page.getByRole("tab", { name: "Scraping ético" }).click();
  await expect(page.getByRole("button", { name: "Buscar via SearXNG" })).toBeDisabled();
  await expect(page.getByText("Operadores do X/Twitter só funcionam no X. Use o deeplink do X.")).toBeVisible();
});
