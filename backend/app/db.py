from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def _set_sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA cache_size=-4000")  # ~4 MB: baixo consumo de memória
    cur.close()


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        _engine = make_engine(f"sqlite:///{settings.db_path}")
    return _engine


def set_engine(engine: Engine | None) -> None:
    """Usado pelos testes para injetar um banco isolado."""
    global _engine
    _engine = engine


def init_db() -> None:
    import app.models  # noqa: F401  (registra as tabelas)

    SQLModel.metadata.create_all(get_engine())
    _migrar(get_engine())


def _migrar(engine: Engine) -> None:
    """Migrations leves e idempotentes (ALTER TABLE ADD COLUMN se não existir)."""
    from sqlalchemy import text

    with engine.begin() as conn:
        colunas = {row[1] for row in conn.execute(text("PRAGMA table_info(hashtag)"))}
        if "chave_normalizada" not in colunas:
            conn.execute(text("ALTER TABLE hashtag ADD COLUMN chave_normalizada VARCHAR NOT NULL DEFAULT ''"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hashtag_chave_normalizada ON hashtag (chave_normalizada)"))
        # backfill: linhas antigas (ou criadas antes da coluna) recebem a chave
        from app.services.hashtag_tracker import chave_normalizada

        pendentes = conn.execute(text("SELECT id, tag FROM hashtag WHERE chave_normalizada = ''")).all()
        for hid, tag in pendentes:
            conn.execute(text("UPDATE hashtag SET chave_normalizada = :c WHERE id = :i"), {"c": chave_normalizada(tag), "i": hid})
        colunas_monitor = {row[1] for row in conn.execute(text("PRAGMA table_info(monitor)"))}
        if "radar_modo" not in colunas_monitor:
            conn.execute(text("ALTER TABLE monitor ADD COLUMN radar_modo VARCHAR NOT NULL DEFAULT 'termos'"))
        # Convites v2 + mídia nos itens de feed (módulo Convocações)
        _add_colunas(
            conn,
            "invite",
            {
                "fonte_url": "VARCHAR NOT NULL DEFAULT ''",
                "status": "VARCHAR NOT NULL DEFAULT 'desconhecido'",
                "nome_grupo": "VARCHAR",
                "membros": "INTEGER",
                "descricao": "VARCHAR",
                "verificado_em": "DATETIME",
                "evidencia_id": "INTEGER",
                "score_relevancia": "INTEGER NOT NULL DEFAULT 0",
                "http_status": "INTEGER NOT NULL DEFAULT 0",
                "erro_verificacao": "VARCHAR NOT NULL DEFAULT ''",
            },
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_invite_status ON invite (status)"))
        _add_colunas(conn, "fonte_item", {"midias": "VARCHAR NOT NULL DEFAULT '[]'"})


def _add_colunas(conn, tabela: str, colunas: dict[str, str]) -> None:  # noqa: ANN001
    from sqlalchemy import text

    existentes = {row[1] for row in conn.execute(text(f"PRAGMA table_info({tabela})"))}
    for nome, ddl in colunas.items():
        if nome not in existentes:
            conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {nome} {ddl}"))


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
