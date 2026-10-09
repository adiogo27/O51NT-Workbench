"""Login por e-mail + código, porteiro da API, anti-CSRF, limites/bloqueio e administração de usuários."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import config
from app.services import auth as svc

pytestmark = pytest.mark.integration
ADMIN = "adiogo27@gmail.com"
CSRF = {"X-Requested-With": "O51NT"}


@pytest.fixture
def codigos(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Captura os códigos em vez de enviar e-mail."""
    capturados: list[tuple[str, str]] = []

    async def fake(usuario, codigo, ip):  # noqa: ANN001
        capturados.append((usuario.email, codigo))
        return svc.Entrega("email", True)

    monkeypatch.setattr(svc, "entregar_codigo", fake)
    return capturados


@pytest.fixture
def cliente_auth(data_dir, fake_scraper, fake_searxng, monkeypatch: pytest.MonkeyPatch, codigos) -> Iterator[TestClient]:  # noqa: ANN001
    monkeypatch.setenv("O51NT_ADMIN_EMAIL", ADMIN)
    monkeypatch.setenv("O51NT_AUTH_COOKIE_SECURE", "false")  # TestClient fala http://testserver
    config.get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    config.get_settings.cache_clear()


def entrar(c: TestClient, codigos: list[tuple[str, str]], email: str) -> None:
    assert c.post("/api/auth/solicitar", json={"email": email}).status_code == 200
    codigo = next(cod for em, cod in reversed(codigos) if em == email)
    r = c.post("/api/auth/verificar", json={"email": email, "codigo": codigo})
    assert r.status_code == 200, r.text
    assert "o51nt_sessao" in c.cookies


def test_sem_sessao_api_fechada_mas_health_e_spa_abertos(cliente_auth: TestClient) -> None:
    c = cliente_auth
    assert c.get("/api/health").status_code == 200
    r = c.get("/api/monitors")
    assert r.status_code == 401 and r.json() == {"detail": "não autenticado", "auth": True}
    assert c.post("/api/monitors", json={"nome": "x", "query": "y"}, headers=CSRF).status_code == 401
    e = c.get("/api/auth/estado").json()
    assert e["ativo"] is True and e["autenticado"] is False and e["usuario"] is None and e["canal"] == "journal"
    assert c.get("/api/auth/eu").status_code == 401


def test_fluxo_completo_de_login(cliente_auth: TestClient, codigos: list[tuple[str, str]]) -> None:
    c = cliente_auth
    # e-mail desconhecido: resposta idêntica, nenhum código gerado
    r = c.post("/api/auth/solicitar", json={"email": "intruso@exemplo.com"})
    assert r.status_code == 200 and r.json()["mensagem"] == svc.MENSAGEM_GENERICA and codigos == []
    assert c.post("/api/auth/solicitar", json={"email": "sem-arroba"}).status_code == 422
    # admin pede código
    r = c.post("/api/auth/solicitar", json={"email": ADMIN.upper()})
    assert r.status_code == 200 and r.json()["canal"] == "email" and len(codigos) == 1
    email, codigo = codigos[0]
    assert email == ADMIN and len(codigo) == 6 and codigo.isdigit()
    # código errado → 401 genérico, sem cookie
    r = c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": "000000" if codigo != "000000" else "111111"})
    assert r.status_code == 401 and "o51nt_sessao" not in c.cookies
    # certo → cookie HttpOnly/SameSite=Strict
    r = c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": codigo})
    assert r.status_code == 200 and r.json()["usuario"]["papel"] == "admin"
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc and "path=/" in sc
    # código é de uso único
    assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": codigo}).status_code == 401
    # com sessão: GET passa; mutação sem cabeçalho anti-CSRF é recusada; com cabeçalho passa
    assert c.get("/api/monitors").status_code == 200
    assert c.post("/api/monitors", json={"nome": "m", "query": "PRF"}).status_code == 403
    assert c.post("/api/monitors", json={"nome": "m", "query": "PRF"}, headers=CSRF).status_code == 201
    assert c.post("/api/monitors", json={"nome": "m2", "query": "PRF"}, headers={**CSRF, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    eu = c.get("/api/auth/eu").json()
    assert eu["email"] == ADMIN and eu["ultimo_login"] is not None
    assert c.get("/api/auth/estado").json()["autenticado"] is True
    sess = c.get("/api/auth/sessoes").json()
    assert len(sess) == 1 and sess[0]["atual"] is True
    # sair → sessão revogada
    assert c.post("/api/auth/sair", headers=CSRF).json() == {"ok": True}
    assert c.get("/api/monitors").status_code == 401
    eventos = {e["evento"] for e in _eventos(c, codigos)}
    assert {"codigo_recusado", "codigo_solicitado", "login_falha", "login_ok", "logout"} <= eventos


def _eventos(c: TestClient, codigos: list[tuple[str, str]]) -> list[dict]:
    entrar(c, codigos, ADMIN)
    return c.get("/api/auth/eventos").json()


def test_admin_gerencia_usuarios_e_analista_nao(cliente_auth: TestClient, codigos: list[tuple[str, str]]) -> None:
    c = cliente_auth
    entrar(c, codigos, ADMIN)
    lista = c.get("/api/auth/usuarios").json()
    assert [u["email"] for u in lista] == [ADMIN] and lista[0]["criado_por"] == "sistema"
    r = c.post("/api/auth/usuarios", json={"email": "Analista@PRF.gov.br", "nome": "Ana", "papel": "analista"}, headers=CSRF)
    assert r.status_code == 201 and r.json()["email"] == "analista@prf.gov.br"
    uid = r.json()["id"]
    assert c.post("/api/auth/usuarios", json={"email": "analista@prf.gov.br"}, headers=CSRF).status_code == 409
    assert c.post("/api/auth/usuarios", json={"email": "x@y.z", "papel": "deus"}, headers=CSRF).status_code == 422
    admin_id = lista[0]["id"]
    # não pode se rebaixar/desativar nem remover a si (é o único admin)
    assert c.patch(f"/api/auth/usuarios/{admin_id}", json={"ativo": False}, headers=CSRF).status_code == 409
    assert c.patch(f"/api/auth/usuarios/{admin_id}", json={"papel": "analista"}, headers=CSRF).status_code == 409
    assert c.delete(f"/api/auth/usuarios/{admin_id}", headers=CSRF).status_code == 409
    # desativar o analista impede o login dele
    assert c.patch(f"/api/auth/usuarios/{uid}", json={"ativo": False}, headers=CSRF).json()["ativo"] is False
    n = len(codigos)
    assert c.post("/api/auth/solicitar", json={"email": "analista@prf.gov.br"}).status_code == 200 and len(codigos) == n
    assert c.patch(f"/api/auth/usuarios/{uid}", json={"ativo": True, "nome": "Ana Paula"}, headers=CSRF).json()["nome"] == "Ana Paula"
    c.post("/api/auth/sair", headers=CSRF)
    # analista entra, mas não administra
    entrar(c, codigos, "analista@prf.gov.br")
    assert c.get("/api/monitors").status_code == 200
    assert c.get("/api/auth/usuarios").status_code == 403
    assert c.post("/api/auth/usuarios", json={"email": "outro@x.y"}, headers=CSRF).status_code == 403
    assert c.get("/api/auth/eventos").status_code == 403
    c.post("/api/auth/sair", headers=CSRF)
    entrar(c, codigos, ADMIN)
    assert c.delete(f"/api/auth/usuarios/{uid}", headers=CSRF).status_code == 204
    assert [u["email"] for u in c.get("/api/auth/usuarios").json()] == [ADMIN]


def test_limites_tentativas_e_bloqueio(cliente_auth: TestClient, codigos: list[tuple[str, str]]) -> None:
    c = cliente_auth
    s = config.get_settings()
    # limite de pedidos por 15 min
    for _ in range(s.auth_pedidos_por_15min + 2):
        assert c.post("/api/auth/solicitar", json={"email": ADMIN}).status_code == 200
    assert len(codigos) == s.auth_pedidos_por_15min
    codigo = codigos[-1][1]
    errado = "000000" if codigo != "000000" else "111111"
    # falhas até o bloqueio (5) → 429 mesmo com o código certo
    for _ in range(s.auth_falhas_bloqueio):
        assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": errado}).status_code == 401
    r = c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": codigo})
    assert r.status_code == 429 and "aguarde" in r.json()["detail"]
    # pedir novo código durante o bloqueio não gera código
    n = len(codigos)
    assert c.post("/api/auth/solicitar", json={"email": ADMIN}).status_code == 200 and len(codigos) == n


def test_codigo_queimado_apos_tentativas(cliente_auth: TestClient, codigos: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    c = cliente_auth
    monkeypatch.setattr(config.get_settings(), "auth_falhas_bloqueio", 100)  # isola a regra do código
    monkeypatch.setattr(config.get_settings(), "auth_codigo_tentativas", 3)
    c.post("/api/auth/solicitar", json={"email": ADMIN})
    codigo = codigos[-1][1]
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(3):
        c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": errado})
    assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": codigo}).status_code == 401  # queimado
    c.post("/api/auth/solicitar", json={"email": ADMIN})
    assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": codigos[-1][1]}).status_code == 200


def test_novo_pedido_invalida_codigo_anterior(cliente_auth: TestClient, codigos: list[tuple[str, str]]) -> None:
    c = cliente_auth
    c.post("/api/auth/solicitar", json={"email": ADMIN})
    c.post("/api/auth/solicitar", json={"email": ADMIN})
    antigo, novo = codigos[-2][1], codigos[-1][1]
    if antigo != novo:
        assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": antigo}).status_code == 401
    assert c.post("/api/auth/verificar", json={"email": ADMIN, "codigo": novo}).status_code == 200


def test_auth_desativada_mantem_contrato_local(client: TestClient) -> None:
    e = client.get("/api/auth/estado").json()
    assert e["ativo"] is False and e["autenticado"] is True
    assert client.post("/api/auth/solicitar", json={"email": ADMIN}).status_code == 404
    assert client.get("/api/monitors").status_code == 200
    assert client.post("/api/monitors", json={"nome": "m", "query": "PRF"}).status_code == 201  # sem cabeçalho anti-CSRF
    assert client.get("/api/auth/usuarios").json() == []  # acesso local age como admin
    assert client.post("/api/auth/usuarios", json={"email": "a@b.c"}).status_code == 201
