/**
 * Detecção de operadores de busca numa query (Google e X/TweetDeck).
 *
 * Espelha `backend/app/services/operators.py` (`operadores_google` / `operadores_x`): mesmo
 * tokenizador de uma passada, O(n). Os dois lados são testados contra
 * `shared/google_operator_cases.json` ("casos" e "casos_x").
 *
 * - Operadores do Google desabilitam a busca via SearXNG (os motores não os respeitam).
 * - Operadores do X só funcionam no X/TweetDeck; também desabilitam o SearXNG.
 */

export const OPERADORES_CHAVE: ReadonlySet<string> = new Set(["before", "after", "site", "filetype", "inurl", "intitle", "intext"]);
export const OPERADORES_X_CHAVE: ReadonlySet<string> = new Set([
  "since", "until", "is", "has", "from", "to", "lang", "filter", "min_faves", "min_retweets", "min_replies", "near", "within",
]);

export const MOTIVO_SEM_SEARXNG = "Operadores do Google não são respeitados por outros motores. Use o deeplink.";
export const MOTIVO_SEM_SEARXNG_X = "Operadores do X/Twitter só funcionam no X. Use o deeplink do X.";

const isSpace = (c: string): boolean => /\s/.test(c);

interface Deteccao {
  google: string[];
  x: string[];
}

/** Uma passada; devolve os rótulos Google e X na ordem da 1ª ocorrência. */
function scan(q: string): Deteccao {
  const google: string[] = [];
  const x: string[] = [];
  const add = (lista: string[], r: string) => {
    if (!lista.includes(r)) lista.push(r);
  };
  const n = q.length;
  let i = 0;
  while (i < n) {
    const c = q[i];
    if (isSpace(c)) {
      i++;
      continue;
    }
    if (c === "(" || c === ")") {
      add(google, "()");
      i++;
      continue;
    }
    let negado = false;
    let k = i;
    if (q[k] === "-" && k + 1 < n && !isSpace(q[k + 1])) {
      negado = true;
      k++;
    }
    if (q[k] === '"') {
      const fim = q.indexOf('"', k + 1);
      if (fim === -1) break; // aspas desbalanceadas: não conta (query inválida para o backend)
      add(google, '""');
      i = fim + 1;
      continue;
    }
    // palavra ou chave:valor
    let j = k;
    while (j < n && !isSpace(q[j]) && !'()"'.includes(q[j]) && q[j] !== ":") j++;
    const palavra = q.slice(k, j);
    const chave = palavra.toLowerCase();
    if (j < n && q[j] === ":" && (OPERADORES_CHAVE.has(chave) || OPERADORES_X_CHAVE.has(chave))) {
      add(OPERADORES_CHAVE.has(chave) ? google : x, `${negado ? "-" : ""}${chave}:`);
      j++;
      if (q[j] === '"') {
        const fim = q.indexOf('"', j + 1);
        j = fim === -1 ? n : fim + 1;
      } else {
        while (j < n && !isSpace(q[j]) && !"()".includes(q[j])) j++;
      }
      i = j;
      continue;
    }
    while (j < n && !isSpace(q[j]) && !'()"'.includes(q[j])) j++;
    const token = q.slice(k, j);
    if (!negado && token === "OR") add(google, "OR");
    else if (!negado && token === "AND") add(x, "AND");
    else if (token.startsWith("@") && token.length > 1) add(x, "@");
    i = j;
  }
  return { google, x };
}

/** Rótulos do Google: "site:", "-site:", ..., "OR", '""', "()". */
export function detectGoogleOperators(q: string): string[] {
  return scan(q).google;
}

/** Rótulos do X/TweetDeck: "since:", "until:", "is:", "-is:", "from:", ..., "@", "AND". */
export function detectXOperators(q: string): string[] {
  return scan(q).x;
}

export function usaOperadoresGoogle(q: string): boolean {
  return detectGoogleOperators(q).length > 0;
}

export function usaOperadoresX(q: string): boolean {
  return detectXOperators(q).length > 0;
}
