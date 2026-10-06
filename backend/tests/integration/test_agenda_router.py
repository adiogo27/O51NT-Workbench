from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

BASE = {
    "candidato": "Candidato A",
    "partido": "XYZ",
    "titulo": "Carreata",
    "tipo": "carreata",
    "data": "2026-10-03",
    "hora_inicio": "14:30",
    "cidade": "Americana",
    "uf": "sp",
    "rodovias": ["br 116", "BR-116", "BR040"],
    "impacto_rodovia": True,
    "fonte_url": "https://exemplo.org/agenda",
}


def test_crud_completo(client: TestClient) -> None:
    r = client.post("/api/agenda", json=BASE)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["uf"] == "SP" and ev["rodovias"] == ["BR-116", "BR-040"] and ev["dia_semana"] == "sábado"
    eid = ev["id"]
    assert client.get(f"/api/agenda/{eid}").json()["titulo"] == "Carreata"
    r = client.patch(f"/api/agenda/{eid}", json={"status": "confirmado", "rodovias": ["BR-381"], "hora_fim": "16:00"})
    assert r.json()["status"] == "confirmado" and r.json()["rodovias"] == ["BR-381"] and r.json()["hora_fim"] == "16:00"
    assert client.delete(f"/api/agenda/{eid}").status_code == 204
    assert client.get(f"/api/agenda/{eid}").status_code == 404
    assert client.delete(f"/api/agenda/{eid}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {**BASE, "uf": "XX"},
        {**BASE, "hora_inicio": "25:00"},
        {**BASE, "tipo": "festa"},
        {**BASE, "rodovias": ["Rodovia dos Bandeirantes"]},
        {**BASE, "fonte_url": "exemplo.org"},
        {**BASE, "status": "talvez"},
        {k: v for k, v in BASE.items() if k != "data"},
    ],
)
def test_validacoes_422(client: TestClient, payload: dict) -> None:
    assert client.post("/api/agenda", json=payload).status_code == 422


def test_filtros_e_dia(client: TestClient) -> None:
    client.post("/api/agenda", json=BASE)
    client.post("/api/agenda", json={**BASE, "candidato": "Candidato B", "uf": "GO", "cidade": "Goiânia", "rodovias": [], "impacto_rodovia": False, "hora_inicio": None})
    client.post("/api/agenda", json={**BASE, "data": "2026-10-04", "titulo": "Outro dia"})
    assert len(client.get("/api/agenda").json()) == 3
    assert len(client.get("/api/agenda", params={"data": "2026-10-03"}).json()) == 2
    assert len(client.get("/api/agenda", params={"uf": "go"}).json()) == 1
    assert len(client.get("/api/agenda", params={"candidato": "candidato b"}).json()) == 1
    assert len(client.get("/api/agenda", params={"impacto_rodovia": "true"}).json()) == 2
    assert len(client.get("/api/agenda", params={"de": "2026-10-04", "ate": "2026-10-31"}).json()) == 1
    dia = client.get("/api/agenda/dia/2026-10-03").json()
    assert dia["dia_semana"] == "sábado" and dia["total"] == 2 and dia["com_impacto_rodovia"] == 1
    assert list(dia["por_candidato"]) == ["Candidato A", "Candidato B"]
    # eventos com hora vêm antes dos sem hora no mesmo dia
    assert [e["candidato"] for e in dia["eventos"]] == ["Candidato A", "Candidato B"]


def test_export_csv_json_ics(client: TestClient) -> None:
    client.post("/api/agenda", json=BASE)
    csv_r = client.get("/api/agenda/export", params={"formato": "csv", "data": "2026-10-03"})
    assert csv_r.headers["content-type"].startswith("text/csv") and "Candidato A" in csv_r.text
    assert 'filename="agenda_2026-10-03.csv"' in csv_r.headers["content-disposition"]
    js = client.get("/api/agenda/export", params={"formato": "json"}).json()
    assert js[0]["rodovias"] == ["BR-116", "BR-040"]
    ics = client.get("/api/agenda/export", params={"formato": "ics"})
    assert ics.headers["content-type"].startswith("text/calendar") and "BEGIN:VEVENT" in ics.text
    assert client.get("/api/agenda/export", params={"formato": "pdf"}).status_code == 422


def test_queries_do_evento(client: TestClient) -> None:
    eid = client.post("/api/agenda", json=BASE).json()["id"]
    r = client.get(f"/api/agenda/{eid}/queries").json()
    assert r["query"].startswith('"Candidato A" (Americana OR (BR-116 OR "BR 116" OR BR116) OR (BR-040')
    assert r["query"].endswith("after:2026-10-02") and r["query_x"].endswith("-is:retweet since:2026-10-02")
    assert set(r["deeplinks"]) == {"google", "bing", "duckduckgo", "startpage"}
    assert r["deeplinks_x"]["x"].startswith("https://x.com/search?q=") and "google_news" in r["deeplinks_x"]
    assert r["termos_rodovia"] == ['(BR-116 OR "BR 116" OR BR116)', '(BR-040 OR "BR 040" OR BR040)']
    assert client.get("/api/agenda/9999/queries").status_code == 404


def test_monitorar_evento_cria_monitor(client: TestClient) -> None:
    eid = client.post("/api/agenda", json=BASE).json()["id"]
    r = client.post(f"/api/agenda/{eid}/monitor", json={"cron": "*/30 * * * *", "usar_x": True})
    assert r.status_code == 201, r.text
    mon = r.json()
    assert mon["tipo"] == "query" and mon["query"].endswith("since:2026-10-02") and mon["nome"].startswith("Agenda: Candidato A")
    assert client.get(f"/api/agenda/{eid}").json()["monitor_id"] == mon["id"]
    assert client.get(f"/api/monitors/{mon['id']}").status_code == 200
    run = client.post(f"/api/monitors/{mon['id']}/run-now").json()
    assert run["status"] == "ok" and "x" in run["deeplinks"]
    assert client.post(f"/api/agenda/{eid}/monitor", json={"cron": "bad"}).status_code == 422
    assert client.post(f"/api/agenda/{eid}/monitor", json={"canal_alerta": "webhook"}).status_code == 422
