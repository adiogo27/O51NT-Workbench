// Gera o "Guia O51NT — Op. Eleições 2026.pdf" na raiz do projeto, com capturas de tela reais.
//
// - Sobe um backend ISOLADO (banco temporário, porta 8061) e semeia dados de demonstração neutros.
// - Aplica o tema claro (melhor para impressão), fotografa cada recurso com o Chromium headless
//   e renderiza o HTML do guia em PDF (page.pdf). Nenhum dado do usuário é tocado.
//
// Uso: cd frontend && npm run guia      (requer backend/static buildado: npm run build)
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const PORT = Number(process.env.GUIA_PORT ?? 8061);
const BASE = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.join(ROOT, "deploy", "guia");
const IMG_DIR = path.join(OUT_DIR, "img");
const HTML = path.join(OUT_DIR, "guia.html");
const PDF = path.join(ROOT, "Guia O51NT — Op. Eleições 2026.pdf");
const DATA_DIR = mkdtempSync(path.join(tmpdir(), "o51nt-guia-"));
const DIA = "2026-10-03";

const systemChromium = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"].find(existsSync);
const executablePath = process.env.PW_CHROMIUM ?? (existsSync(path.join(process.env.HOME ?? "", ".cache/ms-playwright")) ? undefined : systemChromium);

const log = (m) => console.log(`[guia] ${m}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(method, p, body, isForm = false) {
  const res = await fetch(BASE + p, {
    method,
    headers: isForm ? {} : { "Content-Type": "application/json" },
    body: isForm ? body : body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${p} → HTTP ${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

// ------------------------------------------------------------------ backend isolado
if (!existsSync(path.join(ROOT, "backend", "static", "index.html"))) {
  console.error("[guia] frontend não buildado: rode `npm run build` antes.");
  process.exit(1);
}
const uvicorn = spawn(path.join(ROOT, ".venv", "bin", "python"), ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(PORT), "--log-level", "warning"], {
  cwd: path.join(ROOT, "backend"),
  env: { ...process.env, O51NT_DATA_DIR: DATA_DIR, O51NT_SCHEDULER_ENABLED: "true", O51NT_SEARXNG_URL: "http://127.0.0.1:9" },
  stdio: "ignore",
});
let encerrado = false;
// Espera o uvicorn sair (ele roda o shutdown do lifespan) antes de apagar o diretório temporário.
async function encerrar() {
  if (encerrado) return;
  encerrado = true;
  if (uvicorn.exitCode === null && !uvicorn.killed) {
    const saiu = new Promise((resolve) => uvicorn.once("exit", resolve));
    uvicorn.kill("SIGTERM");
    const timeout = new Promise((resolve) => setTimeout(resolve, 8000, "timeout"));
    if ((await Promise.race([saiu, timeout])) === "timeout") uvicorn.kill("SIGKILL");
  }
  rmSync(DATA_DIR, { recursive: true, force: true });
}
process.on("exit", () => { try { uvicorn.kill("SIGKILL"); } catch { /* já encerrado */ } });
process.on("SIGINT", () => { void encerrar().then(() => process.exit(130)); });
process.on("uncaughtException", (err) => { console.error(err); void encerrar().then(() => process.exit(1)); });
process.on("unhandledRejection", (err) => { console.error(err); void encerrar().then(() => process.exit(1)); });

for (let i = 0; i < 60; i++) {
  try { if ((await fetch(`${BASE}/api/health`)).ok) break; } catch { /* ainda subindo */ }
  await sleep(500);
  if (i === 59) throw new Error("backend isolado não respondeu");
}
log(`backend isolado em ${BASE} (dados em ${DATA_DIR})`);

// ------------------------------------------------------------------ dados de demonstração (neutros)
const settings = await api("GET", "/api/settings");
settings.tema = { primary: "#0091d5", secondary: "#e8f4fb", background: "#ffffff", foreground: "#111827", accent: "#f2e08a", radius: 0.375 };
settings.tipografia = { fontFamily: "Inter", fontSizeBase: 15 };
await api("PUT", "/api/settings", settings);

const ev1 = await api("POST", "/api/agenda", {
  candidato: "Candidato A", partido: "Partido X", cargo: "presidente", titulo: "Carreata de encerramento", tipo: "carreata",
  data: DIA, hora_inicio: "14:30", hora_fim: "17:00", cidade: "Americana", uf: "SP", local: "Santa Bárbara d'Oeste → Americana",
  rodovias: ["BR-116"], impacto_rodovia: true, fonte_url: "https://exemplo.org/agenda-candidato-a", status: "confirmado",
  descricao: "Trajeto com trecho em rodovia federal.",
});
await api("POST", "/api/agenda", {
  candidato: "Candidato B", partido: "Partido Y", cargo: "presidente", titulo: "Caminhada no centro", tipo: "caminhada",
  data: DIA, hora_inicio: "09:00", cidade: "Goiânia", uf: "GO", local: "Praça Cívica", rodovias: [], impacto_rodovia: false, status: "previsto",
});
await api("POST", "/api/agenda", {
  candidato: "Candidato A", partido: "Partido X", titulo: "Motociata", tipo: "motociata", data: "2026-10-04", hora_inicio: "10:00",
  cidade: "Rio de Janeiro", uf: "RJ", rodovias: ["BR-101"], impacto_rodovia: true, status: "previsto",
});
await api("POST", `/api/agenda/${ev1.id}/monitor`, { cron: "0 */2 * * *" });
await api("POST", "/api/monitors", { nome: "Eleições 2026 (imprensa)", query: "(eleições OR eleição OR eleitoral OR TSE OR urnas OR candidato) -futebol", cron: "0 * * * *" });
await api("POST", "/api/monitors", { nome: "PRF e rodovias", query: '(PRF OR "Polícia Rodoviária Federal" OR rodovia OR BR-116 OR BR-101) (blitz OR bloqueio OR interdição OR acidente OR operação)', cron: "0 * * * *" });
const monitores = await api("GET", "/api/monitors");
if (monitores[0]) await api("POST", `/api/monitors/${monitores[0].id}/run-now`);
log("ciclo real do Radar (feeds públicos)…");
const ciclo = await api("POST", "/api/radar/ciclo");
log(`radar: ${ciclo.itens_novos} itens, ${ciclo.hits_novos} hits`);

for (const [tag, contagem] of [["#Eleicoes2026", 4], ["#eleicoes2026", 2], ["#Brasil2026", 2], ["#VotoConsciente", 1]]) {
  await api("POST", "/api/hashtags", { tag, contagem, fonte: "manual" });
}
await api("POST", "/api/perfis", { rede: "x", handle: "https://x.com/PRFBrasil", rotulo: "PRF Brasil", categoria: "institucional" });
await api("POST", "/api/perfis", { rede: "site", handle: "https://www.justicaeleitoral.jus.br/fato-ou-boato/", rotulo: "TSE — Fato ou Boato", categoria: "institucional" });

const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
const fd = new FormData();
fd.append("arquivo", new Blob([png], { type: "image/png" }), "print_noticia.png");
fd.append("origem_url", "https://exemplo.org/noticia-prf");
fd.append("notas", "Print da notícia usada no boletim de 02/10.");
const evid = await api("POST", "/api/evidence", fd, true);

await api("POST", "/api/boletim/itens", { data: DIA, secao: "noticia", titulo: "PRF promete \"livre deslocamento\" do eleitor no 1º turno", url: "https://exemplo.org/noticia-prf", fonte: "imprensa", resumo: "Nota institucional repercutida pela imprensa.", evidence_id: evid.id });
await api("POST", "/api/boletim/itens", { data: DIA, secao: "fake_news", titulo: "É falso que a PM tenha identificado plano de ataque a embaixadas", url: "https://exemplo.org/checagem", fonte: "agência de checagem", resumo: "Checagem publicada; conteúdo desmentido." });
await api("POST", "/api/boletim/itens", { data: DIA, secao: "imagem_institucional", titulo: "Comentários sobre blitz da PRF seguem em alta no X", fonte: "monitoramento X/TweetDeck", resumo: "Termos \"blitz ilegal\" e \"blitz da PRF\" em crescimento; postagens recentes de cunho informativo." });

// ------------------------------------------------------------------ capturas
mkdirSync(IMG_DIR, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1.5, locale: "pt-BR" });

async function ir(url) {
  await page.goto(BASE + url);
  await page.waitForLoadState("networkidle");
  await sleep(300);
}
async function foto(nome, alvo = page, opts = {}) {
  const p = path.join(IMG_DIR, `${nome}.png`);
  await alvo.screenshot({ path: p, ...opts });
  log(`captura ${nome}.png`);
}
const card = (titulo) => page.locator("h2", { hasText: titulo }).first().locator("..");

// 1) Query Builder: template X do boletim carregado
await ir("/query");
await page.getByRole("button", { name: /X — Mobilidade em rodovias federais/ }).click();
await page.waitForLoadState("networkidle");
await sleep(400);
await foto("01-query-template-x");
await foto("02-query-painel-x", card("X / TweetDeck"));
await page.getByRole("tab", { name: "Scraping ético" }).click();
await sleep(300);
await foto("03-query-scraping-bloqueado");

// 2) Agenda
await ir("/agenda");
await page.getByLabel("Dia", { exact: true }).fill(DIA);
await page.waitForLoadState("networkidle");
await sleep(300);
await foto("04-agenda-dia", page, { fullPage: true });
const cardEv = page.getByRole("listitem").filter({ hasText: "Carreata de encerramento" }).filter({ has: page.getByRole("button", { name: "Queries" }) });
await cardEv.getByRole("button", { name: "Queries" }).click();
await page.waitForLoadState("networkidle");
await sleep(300);
await foto("05-agenda-queries", cardEv);

// 3) Boletim
await ir("/boletim");
await page.getByLabel("Dia do boletim").fill(DIA);
await page.waitForLoadState("networkidle");
await sleep(400);
await foto("06-boletim-dia", page, { fullPage: true });
await page.getByRole("tab", { name: "Perfis vigiados" }).click();
await page.waitForLoadState("networkidle");
await page.getByRole("listitem").filter({ hasText: "PRF Brasil" }).getByRole("button", { name: "Menções" }).click();
await page.waitForLoadState("networkidle");
await sleep(300);
await foto("07-boletim-perfis");
await ir(`/api/boletim/${DIA}/export?formato=html`);
await foto("08-boletim-impressao", page, { fullPage: true });

// 4) Convites
await ir("/invites");
await page.getByLabel("Termo a ser pesquisado").fill("eleições");
await page.waitForLoadState("networkidle");
await sleep(500);
await foto("09-convites-deeplinks");
await page.getByRole("tab", { name: "Scraping ético" }).click();
await sleep(300);
await foto("10-convites-scraping");

// 5) Hashtags
await ir("/hashtags");
await page.getByLabel("Hashtag", { exact: true }).fill("#Eleicoes2026");
await sleep(500);
await foto("11-hashtags", page, { fullPage: true });

// 6) Ferramentas (hub)
await ir("/tools");
const secChecagem = page.locator("section", { has: page.getByRole("heading", { name: "Checagem de fatos" }) });
await secChecagem.scrollIntoViewIfNeeded();
await foto("12-hub-checagem", secChecagem);
const secRedes = page.locator("section", { has: page.getByRole("heading", { name: "Busca em redes" }) });
await secRedes.scrollIntoViewIfNeeded();
await foto("13-hub-redes", secRedes);
const secX = page.locator("section", { has: page.getByRole("heading", { name: "Twitter - X" }) });
await secX.scrollIntoViewIfNeeded();
await foto("14-hub-twitter-x", secX);

// 7) Evidências, Imagens, Monitores, Tema
await ir("/evidence");
await foto("15-evidencias");
await ir("/images");
await foto("16-imagens");
await ir("/monitors");
await foto("17-monitores", page, { fullPage: true });
await foto("19-radar-strip", card("Radar"));
await page.getByRole("tab", { name: /^Resultados/ }).click();
await page.waitForLoadState("networkidle");
await sleep(400);
await foto("20-radar-resultados");
await page.getByRole("tab", { name: "Fontes do radar" }).click();
await page.waitForLoadState("networkidle");
await sleep(300);
await foto("21-radar-fontes", page, { fullPage: true });
await ir("/settings");
await foto("18-tema");

// ------------------------------------------------------------------ HTML do guia
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const fig = (nome, legenda) => `<figure><img src="img/${nome}.png" alt="${esc(legenda)}"><figcaption>${esc(legenda)}</figcaption></figure>`;
const passos = (lista) => `<ol class="passos">${lista.map((p) => `<li>${p}</li>`).join("")}</ol>`;
const code = (s) => `<code>${esc(s)}</code>`;

const secoes = [
  {
    id: "inicio",
    titulo: "0. Início rápido",
    objetivo: "Subir o sistema e abrir no navegador.",
    corpo: `
      ${passos([
        `Dê duplo clique em <strong>O51NT Workbench.desktop</strong> (ou rode ${code("./iniciar.sh")} na pasta do projeto). O backend sobe sozinho e uma aba abre em ${code("http://127.0.0.1:8051/")}.`,
        `No GNOME, se o duplo clique não executar, rode uma vez ${code("./iniciar.sh --instalar")}: o item "O51NT Workbench" passa a aparecer na busca de aplicativos e na área de trabalho.`,
        `Para encerrar: ${code("./stop.sh")}. Para rodar os testes: ${code("./test.sh")}.`,
        `Tudo fica na sua máquina (SQLite em ${code("data/")}). Nada é enviado a serviços externos sem um clique seu.`,
      ])}
      <p class="nota"><strong>Fronteira ética do produto:</strong> o O51NT entrega a <em>query certa</em> e o <em>deeplink certo</em> e deixa a decisão com o analista. Ele não burla CAPTCHA, não faz login e respeita o <code>robots.txt</code> nas páginas que coleta.</p>`,
  },
  {
    id: "hashtags",
    titulo: "1. HASHTAGS",
    objetivo: "Manter a lista de hashtags do boletim (ex.: #Eleicoes2026, #Brasil2026, #VotoConsciente) e acompanhar variantes com e sem acento.",
    recurso: "Aba <strong>Hashtags</strong> + aba <strong>Boletim</strong> (seção HASHTAGS, automática).",
    corpo: `
      ${passos([
        `Abra <strong>Hashtags</strong>, digite a hashtag (com ou sem #) e clique em <strong>Cadastrar manualmente</strong>. Variantes como ${code("#eleicoes2026")} e ${code("#Eleições2026")} são agrupadas (chips "variantes") sem perder a forma original.`,
        `Subaba <strong>Deeplinks</strong>: abre a busca do PDF ${code('(site:facebook.com OR site:instagram.com) #NomeHashTag')} no Google/Bing e os atalhos trends24 / OneMillionTweetMap / Comment Picker.`,
        `Subaba <strong>Scraping ético</strong>: <strong>Coletar agora</strong> conta a hashtag no trends24 (fonte pública permitida) e grava a série temporal; <strong>Rastrear periodicamente</strong> cria um monitor com cron.`,
        `As hashtags com contagem entram automaticamente na seção HASHTAGS do boletim do dia.`,
      ])}
      ${fig("11-hashtags", "Aba Hashtags: tabela com variantes (acento/caixa), gráfico e coleta ética no trends24.")}`,
  },
  {
    id: "noticias",
    titulo: "2. NOTÍCIAS RELEVANTES",
    objetivo: "Registrar as notícias do dia com fonte, link e print, no formato do boletim.",
    recurso: "Aba <strong>Boletim</strong> (seção Notícias relevantes) + aba <strong>Evidências</strong> + hub (Google Notícias / X).",
    corpo: `
      ${passos([
        `Em <strong>Boletim</strong>, escolha o dia e, no bloco <strong>Notícias relevantes</strong>, use o campo de apoio para abrir a busca no <strong>Google Notícias</strong> ou no <strong>X (recentes)</strong>.`,
        `Salve o print da notícia em <strong>Evidências</strong> (upload). O sistema calcula o SHA-256 e registra no manifesto (cadeia de custódia). Anote o número da evidência.`,
        `De volta ao Boletim, em <strong>Adicionar ao boletim</strong>: seção "Notícias relevantes", manchete, URL, fonte, resumo e o nº da evidência. Clique em <strong>Adicionar item</strong>.`,
        `A prévia em Markdown (à direita) mostra o boletim já no formato do documento; <strong>Abrir para imprimir (PDF)</strong> gera a versão para distribuir.`,
      ])}
      ${fig("06-boletim-dia", "Aba Boletim: seções do dia, agenda, grupos, perfis e prévia Markdown.")}
      ${fig("15-evidencias", "Aba Evidências: upload com SHA-256, verificação de integridade, busca por hash e export ZIP com manifesto.")}`,
  },
  {
    id: "fake",
    titulo: "3. FAKE NEWS",
    objetivo: "Checar alegações e registrar os desmentidos (AFP Checamos, Comprova, Lupa, Aos Fatos, TSE…).",
    recurso: "Hub <strong>Ferramentas → Checagem de fatos</strong> + aba <strong>Boletim</strong> (seção Fake news).",
    corpo: `
      ${passos([
        `No bloco <strong>Fake news</strong> do Boletim, digite a alegação e clique em <strong>Fact Check Explorer</strong> (busca checagens já publicadas) ou em uma das agências listadas.`,
        `Também em <strong>Ferramentas → Checagem de fatos</strong>: Comprova, Boatos.org e g1 abrem já com o termo pré-preenchido; as demais abrem na página inicial.`,
        `Registre o desmentido como item da seção "Fake news" (título, URL da checagem, fonte) e, se houver, o print como evidência.`,
      ])}
      ${fig("12-hub-checagem", "Hub: categoria Checagem de fatos.")}`,
  },
  {
    id: "manifestacoes",
    titulo: "4. MANIFESTAÇÕES IDENTIFICADAS (mobilidade em rodovias federais)",
    objetivo: "Varrer bloqueios, carreatas e interdições em BRs (string de 04–05/OUT do boletim) e acompanhar continuamente.",
    recurso: "Aba <strong>Query Builder</strong> (template <em>X — Mobilidade em rodovias federais</em>, painel X/TweetDeck, localidades DNIT) + <strong>Monitores</strong>.",
    corpo: `
      ${passos([
        `Em <strong>Query Builder → Templates</strong>, clique em <strong>X — Mobilidade em rodovias federais</strong> (etiqueta "Op. Eleições"). Ajuste a data em "Substituir 2026-10-04".`,
        `Em <strong>Redes e notícias</strong> clique <strong>X (recentes)</strong>: abre a busca do X ordenada por mais recentes, igual a uma coluna do TweetDeck. Os botões Google/Bing avisam (⚠) que ignoram ${code("since:")} e ${code("-is:retweet")}.`,
        `Para outras rodovias/cidades, use <strong>Localidades (IBGE/DNIT)</strong>: digite "BR-040" ou "Curitiba" e clique — o termo ${code('(BR-040 OR "BR 040" OR BR040)')} entra na query.`,
        `Painel <strong>X / TweetDeck</strong>: ${code("since:")}, ${code("until:")}, ${code("from:")}, ${code("@menções")}, "Excluir retweets", ${code("has:")}, ${code("lang:")}, ${code("min_faves:")}. O validador acusa janela vazia (until ≤ since) e valores inválidos.`,
        `Para acompanhar sem clicar: <strong>Monitores → Novo monitor</strong>, escolha o template, defina o cron (ex.: a cada 30 min) e o alerta (JSONL em ${code("data/alerts/")} ou webhook). Cada execução gera os deeplinks (inclusive X/TikTok/YouTube/Google Notícias) na timeline.`,
        `Subaba <strong>Scraping ético</strong>: com operadores do Google ou do X na query, o botão SearXNG fica desabilitado por design — use o deeplink.`,
        `<strong>Radar (vários monitores pesquisando ao mesmo tempo):</strong> em <strong>Monitores</strong>, a tira "Radar" mostra fontes ativas, itens coletados e hits não lidos; <strong>Rodar ciclo agora</strong> coleta os feeds públicos e casa os itens novos com <em>todos</em> os monitores ativos. Resultados ficam em <strong>Resultados</strong> (filtro por monitor, "marcar lido", <strong>Adicionar ao boletim</strong>) e no cartão de cada monitor.`,
        `<strong>Fontes do radar</strong>: 11 feeds verificados já vêm cadastrados. Para a busca do Google entrar no Radar, crie o alerta em google.com/alerts → "Entregar em: Feed RSS" e cadastre a URL marcando "ignorar robots.txt" (feed pessoal). Hashtags do Mastodon: ${code("https://mastodon.social/tags/<hashtag>.rss")}.`,
      ])}
      ${fig("19-radar-strip", "Radar: todos os monitores ativos pesquisam a cada ciclo; contadores e ciclo manual.")}
      ${fig("20-radar-resultados", "Resultados dos monitores: hits reais com fonte, data, termos casados e envio ao boletim.")}
      ${fig("21-radar-fontes", "Fontes do radar: feeds verificados, teste de URL, modelos (Google Alertas, Mastodon).")}
      ${fig("01-query-template-x", "Query Builder com a string de mobilidade carregada: preview, avisos e deeplinks (Google e X).")}
      ${fig("02-query-painel-x", "Painel X / TweetDeck: operadores do X do boletim.")}
      ${fig("03-query-scraping-bloqueado", "Scraping ético: busca via SearXNG desabilitada quando há operadores exclusivos (Google/X).")}
      ${fig("17-monitores", "Monitores: lista, timeline de execuções e deeplinks por execução.")}`,
  },
  {
    id: "agenda",
    titulo: "5. AGENDA DOS CANDIDATOS",
    objetivo: "Cadastrar os compromissos do dia por candidato e destacar o que pode impactar rodovias federais.",
    recurso: "Aba <strong>Agenda</strong>.",
    corpo: `
      ${passos([
        `Em <strong>Agenda</strong>, escolha o dia e preencha <strong>Novo compromisso</strong>: candidato(a), partido, tipo (carreata, motociata, caminhada…), horário, cidade/UF, local e a fonte.`,
        `Em <strong>Rodovias federais envolvidas</strong>, digite "br 116" (qualquer grafia vira BR-116) ou busque na base DNIT. Marque <strong>Poderá impactar o fluxo viário em rodovia federal</strong> quando for o caso — o evento ganha o selo e entra na lista "Próximos 7 dias com impacto".`,
        `No cartão do evento, <strong>Queries</strong> mostra duas buscas prontas (Google com ${code("after:")} e X com ${code("since:")} + ${code("-is:retweet")}) cruzando candidato, cidade, rodovia e tipo; <strong>Monitorar</strong> cria um monitor com essa query.`,
        `Exporte o dia em <strong>CSV</strong>, <strong>JSON</strong> ou <strong>ICS</strong> (importável em qualquer calendário). A agenda do dia entra automaticamente no Boletim.`,
      ])}
      ${fig("04-agenda-dia", "Agenda do dia agrupada por candidato, com selo de impacto em rodovia e formulário.")}
      ${fig("05-agenda-queries", "Queries de monitoramento do evento (Google e X) com os termos de rodovia da base DNIT.")}`,
  },
  {
    id: "imagem",
    titulo: "6. IMAGEM INSTITUCIONAL",
    objetivo: "Monitorar a imagem da PRF no X/TweetDeck e no TikTok com as strings do boletim e registrar a leitura do dia.",
    recurso: "Templates <em>X — Imagem institucional da PRF</em>, <em>X/TweetDeck — Imagem institucional PRF (AND)</em>, <em>TikTok — Imagem institucional</em> + hub <strong>Busca em redes</strong> + Boletim.",
    corpo: `
      ${passos([
        `No Boletim, bloco <strong>Imagem institucional</strong>, clique <strong>X (recentes)</strong> ao lado de cada string (ou <strong>TikTok</strong> para os termos do TikTok; aplique lá o filtro de data "últimas 24 h").`,
        `Para editar a string, carregue o template no Query Builder: a sintaxe ${code("AND")} explícita, ${code("@PRFBrasil")}, ${code("#PRF")}, ${code("-is:retweet")} e ${code("since:")} são reconhecidas e validadas.`,
        `Para o TweetDeck em si, use <strong>Ferramentas → Twitter - X → TweetDeck (OldTweetDeck)</strong> e cole a string numa coluna de busca.`,
        `Registre a leitura do dia ("tendência de crescimento dos termos blitz ilegal / blitz da PRF…") como item da seção Imagem institucional.`,
      ])}
      ${fig("13-hub-redes", "Hub: categoria Busca em redes (X recentes, TikTok, Instagram por hashtag, YouTube, Facebook, Google Notícias).")}
      ${fig("14-hub-twitter-x", "Hub: ferramentas do documento mestre para o X (TweetDeck, OneMillionTweetMap, trends24).")}`,
  },
  {
    id: "grupos",
    titulo: "7. LINKS DE GRUPOS IDENTIFICADOS",
    objetivo: "Localizar convites de grupos de WhatsApp e Telegram divulgados em redes sociais e guardá-los com data e hash.",
    recurso: "Aba <strong>Convites</strong>.",
    corpo: `
      ${passos([
        `Em <strong>Convites</strong>, digite o termo (ex.: "eleições"). A subaba <strong>Deeplinks</strong> monta as duas queries do documento mestre (chat.whatsapp.com e t.me/joinchat) e abre no Google/Bing/DuckDuckGo/Startpage.`,
        `Clique nos resultados que forem convites e registre-os: a tabela guarda plataforma, URL, termo, primeira/última vez vistos e o hash da página. Exporte em CSV/JSON.`,
        `A subaba <strong>Scraping ético</strong> fica desabilitada para essas queries (usam operadores do Google que os demais motores ignoram) — o deeplink é o caminho confiável.`,
        `Os convites vistos nos últimos 7 dias entram automaticamente na seção LINKS DE GRUPOS do boletim.`,
      ])}
      ${fig("09-convites-deeplinks", "Convites: queries do PDF prontas, por plataforma, com deeplinks.")}
      ${fig("10-convites-scraping", "Convites: regra de desabilitação consistente com o Query Builder.")}
      <p class="nota">Cuidado com dados pessoais: guarde apenas o necessário à investigação (LGPD, art. 7º, IX e art. 11). Nomes, CPFs e telefones de administradores não devem ser copiados para o boletim.</p>`,
  },
  {
    id: "perfis",
    titulo: "8. PERFIS RELEVANTES / PARA ACOMPANHAR",
    objetivo: "Manter a lista de perfis públicos (candidatos, partidos, institucionais, mídia, coletivos) e buscar menções recentes.",
    recurso: "Aba <strong>Boletim → Perfis vigiados</strong>.",
    corpo: `
      ${passos([
        `Em <strong>Boletim → Perfis vigiados</strong>, informe a rede e o usuário <em>ou</em> a URL (ex.: ${code("https://x.com/PRFBrasil")}); o handle é normalizado e duplicatas são recusadas.`,
        `<strong>Menções</strong> mostra duas buscas prontas — X: ${code("(from:usuario OR @usuario) -is:retweet since:…")}; Google: ${code('("Rótulo" OR usuario) after:…')} — com botões para abrir.`,
        `<strong>Monitorar</strong> cria um monitor com a busca do X (para perfis do X) ou do Google. <strong>Desativar</strong> tira o perfil do boletim sem apagar o histórico.`,
        `Os perfis ativos entram automaticamente na seção PERFIS PARA ACOMPANHAR do boletim.`,
      ])}
      ${fig("07-boletim-perfis", "Perfis vigiados: lista, menções (X e Google) e monitoramento.")}`,
  },
  {
    id: "exportar",
    titulo: "9. Fechar e distribuir o boletim do dia",
    objetivo: "Gerar o documento no mesmo formato do Op. Eleições 2026.",
    recurso: "Aba <strong>Boletim</strong> → Markdown / JSON / Abrir para imprimir (PDF).",
    corpo: `
      ${passos([
        `Confira a prévia em Markdown: título "INFORMAÇÕES RELEVANTES - DD MÊS AAAA (dia da semana)" e as seções na ordem do documento (HASHTAGS, NOTÍCIAS, FAKE NEWS, MANIFESTAÇÕES, AGENDA, IMAGEM INSTITUCIONAL, GRUPOS, PERFIS).`,
        `<strong>Markdown</strong> e <strong>JSON</strong> baixam o arquivo; <strong>Abrir para imprimir (PDF)</strong> abre a versão formatada — use Ctrl+P → "Salvar como PDF".`,
        `Para anexar as provas, exporte as evidências do dia em <strong>Evidências → Exportar ZIP</strong> (manifest.json + SHA256SUMS).`,
      ])}
      ${fig("08-boletim-impressao", "Versão imprimível do boletim gerada pelo sistema.")}`,
  },
  {
    id: "imagens",
    titulo: "10. Apoio: busca reversa de imagens e tema",
    objetivo: "Verificar imagens de peças de campanha, prints suspeitos e deepfakes; ajustar o visual.",
    recurso: "Abas <strong>Imagens</strong> e <strong>Tema</strong>.",
    corpo: `
      ${passos([
        `Em <strong>Imagens</strong>, arraste a imagem (vira evidência com SHA-256) e abra Google Lens, TinEye, Yandex, Lenso ou Sensity. Com a URL pública da imagem a busca é direta; sem ela, use "Upload manual" em cada provedor (a imagem local não é enviada automaticamente).`,
        `Em <strong>Tema</strong>, escolha cores (há o preset claro usado neste guia), fonte e tamanho; a preferência de navegador vale para o ${code("iniciar.sh")}.`,
      ])}
      ${fig("16-imagens", "Imagens: dropzone e provedores de busca reversa.")}
      ${fig("18-tema", "Tema: cores, tipografia e preferências persistidas em data/settings.json.")}`,
  },
];

const mapa = [
  ["HASHTAGS", "Hashtags; Boletim (automático)"],
  ["NOTÍCIAS RELEVANTES", "Boletim (itens + apoio Google Notícias/X); Evidências"],
  ["FAKE NEWS", "Ferramentas → Checagem de fatos; Boletim"],
  ["MANIFESTAÇÕES IDENTIFICADAS", "Query Builder (template X — Mobilidade, painel X, localidades DNIT); Monitores + Radar (feeds públicos); Agenda (impacto em rodovia)"],
  ["AGENDA DOS CANDIDATOS", "Agenda (CRUD, queries, monitor, ICS/CSV/JSON)"],
  ["IMAGEM INSTITUCIONAL", "Templates X/TweetDeck e TikTok; Ferramentas → Busca em redes; Boletim"],
  ["LINKS DE GRUPOS IDENTIFICADOS", "Convites; Boletim (últimos 7 dias, automático)"],
  ["PERFIS PARA ACOMPANHAR", "Boletim → Perfis vigiados"],
];

const hoje = new Date().toLocaleDateString("pt-BR");
const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Guia O51NT — Op. Eleições 2026</title>
<style>
  @page { size: A4; margin: 14mm 12mm 16mm 12mm; }
  body { font-family: "DejaVu Sans", Arial, Helvetica, sans-serif; color: #111; font-size: 10.5pt; line-height: 1.45; }
  .capa { height: 250mm; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; page-break-after: always; }
  .capa .logo { background: #0091d5; color: #fff; font-weight: 800; font-size: 28pt; padding: 10px 22px; border-radius: 12px; }
  .capa h1 { font-size: 24pt; margin: 24px 0 6px; } .capa p { color: #444; margin: 4px 0; }
  h2 { font-size: 15pt; color: #0b3d5c; border-bottom: 2px solid #0091d5; padding-bottom: 3px; margin: 0 0 6px; page-break-after: avoid; }
  section { page-break-before: always; } section.sem-quebra { page-break-before: auto; }
  .meta { background: #f1f7fb; border-left: 4px solid #0091d5; padding: 6px 10px; margin: 8px 0 10px; font-size: 10pt; }
  .meta b { color: #0b3d5c; }
  ol.passos { padding-left: 20px; } ol.passos li { margin: 4px 0; }
  code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 9pt; background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
  figure { margin: 10px 0 12px; page-break-inside: avoid; text-align: center; }
  figure img { max-width: 100%; max-height: 225mm; width: auto; border: 1px solid #c8c8c8; border-radius: 4px; }
  figcaption { font-size: 9pt; color: #555; margin-top: 4px; }
  .nota { background: #fff8db; border-left: 4px solid #e0b400; padding: 6px 10px; font-size: 9.5pt; }
  table { border-collapse: collapse; width: 100%; font-size: 9.5pt; } th, td { border: 1px solid #bbb; padding: 4px 6px; text-align: left; vertical-align: top; } th { background: #e8f4fb; }
  ul.sumario { columns: 2; font-size: 10pt; }
</style></head><body>
<div class="capa">
  <div class="logo">O51NT</div>
  <h1>Guia passo a passo<br>Op. Eleições 2026</h1>
  <p>Como usar cada recurso do O51NT Workbench para produzir o boletim<br>"INFORMAÇÕES RELEVANTES" (hashtags, notícias, fake news, manifestações, agenda, imagem institucional, grupos e perfis)</p>
  <p>Versão 1.1 — gerado em ${hoje} — capturas reais do sistema (dados de demonstração)</p>
  <p style="margin-top:30px;font-size:9.5pt;color:#777">Uso local, single-user. Sem login, sem chaves pagas, sem envio automático de dados a terceiros.</p>
</div>
<section class="sem-quebra">
  <h2>Mapa: seção do boletim → recurso do O51NT</h2>
  <table><thead><tr><th>Seção do boletim</th><th>Onde fazer no O51NT</th></tr></thead>
  <tbody>${mapa.map(([a, b]) => `<tr><td><strong>${esc(a)}</strong></td><td>${esc(b)}</td></tr>`).join("")}</tbody></table>
  <h2 style="margin-top:14px">Sumário</h2>
  <ul class="sumario">${secoes.map((s) => `<li>${esc(s.titulo)}</li>`).join("")}</ul>
  <p class="nota" style="margin-top:12px"><strong>Limitações aceitas por design:</strong> os buscadores bloqueiam coleta automatizada (CAPTCHA/robots.txt) e o Google Notícias não libera o RSS no robots.txt — por isso notícias, convites e buscas em redes são <em>assistidos</em> (deeplink + registro manual). O trends24 é a única coleta automática viva, e o OneMillionTweetMap foi encerrado (o HTML público não expõe hashtags).</p>
</section>
${secoes.map((s) => `<section id="${s.id}"><h2>${esc(s.titulo)}</h2>
  <div class="meta"><b>Objetivo no boletim:</b> ${s.objetivo}${s.recurso ? `<br><b>Recurso do O51NT:</b> ${s.recurso}` : ""}</div>${s.corpo}</section>`).join("\n")}
</body></html>`;

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(HTML, html, "utf-8");

const pdfPage = await browser.newPage();
await pdfPage.goto("file://" + HTML);
await pdfPage.waitForLoadState("load");
await sleep(300);
await pdfPage.pdf({
  path: PDF,
  format: "A4",
  printBackground: true,
  margin: { top: "14mm", bottom: "16mm", left: "12mm", right: "12mm" },
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#666;font-family:sans-serif">O51NT Workbench — Guia Op. Eleições 2026 — página <span class="pageNumber"></span> de <span class="totalPages"></span></div>',
});
await browser.close();
log(`PDF gerado: ${PDF}`);
log(`HTML e imagens em ${OUT_DIR}`);
await encerrar();
process.exit(0);
