from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = "postgresql+psycopg://lawfocus:lawfocus_dev_password@localhost:5432/lawfocus_test"


@pytest.fixture(scope="session")
def engine():
    return create_engine(TEST_DATABASE_URL, future=True)


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Each test runs inside an outer transaction + SAVEPOINT, rolled back
    afterwards so tests never leak state or require reseeding the schema.

    A plain `connection.begin()` breaks the moment a test triggers an
    IntegrityError (e.g. asserting a CHECK/UNIQUE constraint): Postgres
    aborts that transaction, and the *session's own* implicit rollback
    deassociates it from our outer transaction handle. Using a SAVEPOINT
    (begin_nested) and restarting it on every commit/rollback survives that.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True, join_transaction_mode="create_savepoint")
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session) -> Generator[TestClient, None, None]:
    """A TestClient whose `get_db` dependency is overridden to the same
    transactional `db_session`, so API-level tests see what the test set up
    and roll back the same way — no separate connection/pool involved."""
    from app.api.v1.deps import get_db
    from app.main import app

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
