import { describe, expect, it } from "vitest";
import { cn, contrastText, dataBR, formatDate, hojeISO, somarDias } from "@/lib/utils";

// Funções puras de src/lib/utils.ts (sem navegador): complementam o E2E do Playwright, não o substituem.
describe("utils", () => {
  it("cn mescla classes do Tailwind sem duplicar conflitos", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", false && "hidden", "font-bold")).toBe("text-sm font-bold");
  });

  it("formatDate: vazio vira travessão, inválido volta como veio, válido vira pt-BR", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("")).toBe("—");
    expect(formatDate("não é data")).toBe("não é data");
    expect(formatDate("2026-10-12T12:00:00Z")).toMatch(/2026/);
  });

  it("hojeISO e somarDias trabalham em AAAA-MM-DD na data local", () => {
    expect(hojeISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(somarDias("2026-10-31", 1)).toBe("2026-11-01");
    expect(somarDias("2026-01-01", -1)).toBe("2025-12-31");
    expect(somarDias("2026-02-28", 1)).toBe("2026-03-01");
  });

  it("dataBR inverte para DD/MM/AAAA", () => {
    expect(dataBR("2026-10-12")).toBe("12/10/2026");
  });

  it("contrastText escolhe preto sobre claro e branco sobre escuro", () => {
    expect(contrastText("#ffffff")).toBe("#111111");
    expect(contrastText("#0b1220")).toBe("#ffffff");
    expect(contrastText("#0091d5")).toBe("#111111"); // azul primário: o preto contrasta mais (WCAG)
    expect(contrastText("inválido")).toBe("#ffffff");
  });
});
