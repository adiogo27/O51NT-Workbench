"""Valida fontes do Radar ao vivo e roda um ciclo real com a query de teste do projeto.

Uso (na raiz do repositório, com a venv e com rede):
    cd backend && ../.venv/bin/python scripts/validar_fontes.py [--query "manifestação OR manifestantes"] [--saida relatorio.json]

O que faz, com o mesmo código do app (scraper ético + parser do Radar), num banco temporário:
1. para cada fonte padrão (app/seed.py) e cada candidata (scripts/fontes_candidatas.json): robots.txt, HTTP, é feed?,
   quantos itens, data do mais recente; se a URL for HTML, tenta o RSS anunciado em <link rel="alternate">;
2. cadastra as que passaram, cria um monitor com a query de teste e roda `radar.ciclo` de verdade;
3. imprime o relatório (Markdown no stdout e em $GITHUB_STEP_SUMMARY, JSON em --saida).

Este contêiner de desenvolvimento não tem saída para a internet; o workflow .github/workflows/fontes.yml roda este
script num runner do GitHub Actions, que tem.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _preparar_ambiente() -> None:
    os.environ.setdefault("O51NT_DATA_DIR", tempfile.mkdtemp(prefix="o51nt-fontes-"))
    os.environ["O51NT_SCHEDULER_ENABLED"] = "false"
    os.environ.setdefault("O51NT_SEARXNG_URL", "http://127.0.0.1:9")


async def _validar(scraper: Any, radar: Any, nome: str, url: str, respeitar_robots: bool, tipo: str) -> dict[str, Any]:
    r: dict[str, Any] = {"nome": nome, "url": url, "ok": False, "status": 0, "robots_permite": None, "tipo": tipo, "itens": 0, "mais_recente": None, "feed_descoberto": None, "erro": ""}
    try:
        r["robots_permite"] = await scraper.robots.permitido(url)
        res = await scraper.buscar(url, respeitar_robots=respeitar_robots)
        r["status"] = res.status
        if not res.ok:
            r["erro"] = res.erro or f"HTTP {res.status}"
            return r
        itens = radar.parse_feed(res.html) if tipo == "feed" else []
        if not itens and tipo == "feed":
            alvo = radar.descobrir_feed(res.html, url)
            if alvo and alvo != url:
                r["feed_descoberto"] = alvo
                res2 = await scraper.buscar(alvo, respeitar_robots=respeitar_robots)
                r["status"] = res2.status
                if res2.ok:
                    itens = radar.parse_feed(res2.html)
                    r["url_final"] = alvo
            if not itens:
                itens = radar.parse_pagina(res.html, url)
                if itens:
                    r["tipo"] = "pagina"
        if tipo == "pagina":
            itens = radar.parse_pagina(res.html, url)
        r["itens"] = len(itens)
        datas = [i.publicado_em for i in itens if getattr(i, "publicado_em", None)]
        if datas:
            r["mais_recente"] = max(datas).isoformat()
        r["ok"] = bool(itens)
        if not itens:
            r["erro"] = "sem itens reconhecíveis (nem feed, nem links de matéria)"
    except Exception as exc:  # noqa: BLE001 — relatório, não falha
        r["erro"] = f"{type(exc).__name__}: {exc}"[:200]
    return r


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", default="manifestação OR manifestantes", help="query do monitor de teste")
    ap.add_argument("--candidatas", default=str(Path(__file__).with_name("fontes_candidatas.json")))
    ap.add_argument("--saida", default="relatorio_fontes.json")
    ap.add_argument("--so-padrao", action="store_true", help="valida só as fontes já semeadas")
    args = ap.parse_args()
    _preparar_ambiente()

    from sqlmodel import Session, select

    from app import db, seed
    from app.models import Fonte, Monitor, MonitorHit
    from app.services import radar
    from app.services.scraper import get_scraper

    db.init_db()
    scraper = get_scraper()
    candidatas: list[dict[str, Any]] = [{"nome": n, "url": u, "categoria": c, "padrao": True} for n, u, c, _a in seed.FONTES_PADRAO]
    if not args.so_padrao:
        candidatas += json.loads(Path(args.candidatas).read_text(encoding="utf-8"))["candidatas"]

    print(f"validando {len(candidatas)} fontes (query de teste: {args.query!r})", flush=True)
    resultados = await asyncio.gather(*(_validar(scraper, radar, c["nome"], c["url"], bool(c.get("respeitar_robots", True)), c.get("tipo", "feed")) for c in candidatas))
    for c, r in zip(candidatas, resultados, strict=True):
        r.update({"categoria": c.get("categoria", "imprensa"), "uf": c.get("uf"), "padrao": bool(c.get("padrao")), "respeitar_robots": bool(c.get("respeitar_robots", True))})

    # ciclo real com as fontes que passaram
    with Session(db.get_engine()) as s:
        existentes = {f.url for f in s.exec(select(Fonte)).all()}
        for r in resultados:
            if not r["ok"]:
                continue
            u = r.get("url_final") or r["url"]
            if u in existentes:
                continue
            s.add(Fonte(nome=r["nome"], url=u, categoria=r["categoria"], ativa=True, respeitar_robots=r["respeitar_robots"], tipo=r["tipo"]))
            existentes.add(u)
        for f in s.exec(select(Fonte)).all():  # fontes padrão que falharam ficam fora do ciclo
            f.ativa = any((x.get("url_final") or x["url"]) == f.url and x["ok"] for x in resultados)
            s.add(f)
        mon = Monitor(nome="teste manifestação", query=args.query, canal_alerta="jsonl")
        mon2 = Monitor(nome="teste curinga", query="manifesta*", canal_alerta="jsonl")
        s.add_all([mon, mon2])
        s.commit()
        ciclo = await radar.ciclo(s, scraper)
        hits = {m.id: s.exec(select(MonitorHit).where(MonitorHit.monitor_id == m.id)).all() for m in (mon, mon2)}
        amostra = {m.nome: [radar.hit_resumo(h) for h in hits[m.id][:40]] for m in (mon, mon2)}

    ok = [r for r in resultados if r["ok"]]
    relatorio = {
        "executado_em": datetime.now(UTC).isoformat(),
        "query": args.query,
        "total": len(resultados),
        "ok": len(ok),
        "fontes": resultados,
        "ciclo": {k: v for k, v in ciclo.items() if k != "fontes"},
        "hits": {nome: len(lista) for nome, lista in amostra.items()},
        "amostra_hits": amostra,
    }
    Path(args.saida).write_text(json.dumps(relatorio, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    linhas = [f"## Fontes do Radar — validação ao vivo ({relatorio['executado_em'][:16]} UTC)", "", f"{len(ok)}/{len(resultados)} fontes OK · query de teste: `{args.query}` · itens novos no ciclo: {ciclo['itens_novos']} · hits: {relatorio['hits']}", "", "| OK | Fonte | Categoria | UF | HTTP | robots | tipo | itens | mais recente | observação |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(resultados, key=lambda x: (not x["ok"], x["categoria"], x["nome"])):
        obs = r["erro"] or (f"feed descoberto: {r['feed_descoberto']}" if r.get("feed_descoberto") else "")
        linhas.append(f"| {'✅' if r['ok'] else '❌'} | {r['nome']} | {r['categoria']} | {r.get('uf') or ''} | {r['status']} | {'sim' if r['robots_permite'] else 'NÃO' if r['robots_permite'] is False else '?'} | {r['tipo']} | {r['itens']} | {(r['mais_recente'] or '')[:16]} | {obs} |")
    linhas += ["", f"### Hits do monitor `{args.query}` (amostra)", ""]
    for h in amostra.get("teste manifestação", [])[:25]:
        linhas.append(f"- [{h.get('fonte_nome')}] {h.get('titulo')} — casou: `{h.get('termos')}` — {h.get('url')}")
    linhas += ["", f"Monitor `manifesta*` (curinga de prefixo): {relatorio['hits'].get('teste curinga', 0)} hits"]
    texto = "\n".join(linhas)
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        Path(resumo).write_text(texto + "\n", encoding="utf-8")
    from app.services.scraper import shutdown_scraper

    await shutdown_scraper()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
