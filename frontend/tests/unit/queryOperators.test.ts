// Teste unitário (Vitest). Rodar: npm run test:unit
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { detectGoogleOperators, detectXOperators, usaOperadoresGoogle, usaOperadoresX } from "@/lib/queryOperators";

const { casos, casos_x, convites } = JSON.parse(readFileSync(new URL("../../../shared/google_operator_cases.json", import.meta.url), "utf-8")) as {
  casos: { query: string; esperado: string[] }[];
  casos_x: { query: string; google: string[]; x: string[] }[];
  convites: { casos: { plataforma: string; query: string; esperado: string[] }[] };
};

// Operadores do X/TweetDeck: mesma string, dois detectores (paridade com operadores_google/operadores_x)
for (const { query, google, x } of casos_x) {
  test(`paridade X: ${query.slice(0, 50)}`, () => {
    expect(detectGoogleOperators(query)).toEqual(google);
    expect(detectXOperators(query)).toEqual(x);
    expect(usaOperadoresX(query)).toBe(x.length > 0);
  });
}

for (const { query, esperado } of casos) {
  test(`paridade com o backend: ${query.slice(0, 50)}`, () => {
    expect(detectGoogleOperators(query)).toEqual(esperado);
  });
}

test("usaOperadoresGoogle", () => {
  expect(usaOperadoresGoogle("PRF blitz")).toBe(false);
  expect(usaOperadoresGoogle("PRF site:gov.br")).toBe(true);
  expect(usaOperadoresGoogle("")).toBe(false);
});

test("string grande (linear)", () => {
  const q = Array.from({ length: 20000 }, (_, i) => `t${i}`).join(" ") + " OR fim";
  expect(detectGoogleOperators(q)).toEqual(["OR"]);
});

// Aba Convites: as queries do PDF sempre usam operadores → botão SearXNG desabilitado (mesma regra do Query Builder)
for (const { plataforma, query, esperado } of convites.casos) {
  test(`convites (${plataforma}) usam operadores do Google`, () => {
    expect(detectGoogleOperators(query)).toEqual(esperado);
    expect(usaOperadoresGoogle(query)).toBe(true);
  });
}
