import ssl

from app.config import Settings


def test_database_tls_settings_require_ca_for_verification() -> None:
    try:
        Settings(database_tls="verify-full")
    except ValueError as error:
        assert "DATABASE_TLS_CA_FILE" in str(error)
    else:
        raise AssertionError("verification TLS must require a CA file")


def test_database_connect_args_disable_tls(monkeypatch) -> None:
    import app.db as db

    monkeypatch.setattr(db, "settings", Settings(database_tls="disable"))
    assert db.database_connect_args() == {"ssl": False}


def test_database_connect_args_require_tls(monkeypatch) -> None:
    import app.db as db

    monkeypatch.setattr(db, "settings", Settings(database_tls="require"))
    context = db.database_connect_args()["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
