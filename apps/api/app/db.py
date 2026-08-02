import ssl

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings

settings = get_settings()


def database_connect_args() -> dict[str, object]:
    if settings.database_tls == "disable":
        return {"ssl": False}
    context = ssl.create_default_context(cafile=settings.database_tls_ca_file)
    context.check_hostname = settings.database_tls == "verify-full"
    context.verify_mode = (
        ssl.CERT_REQUIRED if settings.database_tls == "verify-full" else ssl.CERT_NONE
    )
    return {"ssl": context}


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=database_connect_args(),
)
