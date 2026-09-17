from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import readiness


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_host_database_url_uses_async_driver(scheme):
    settings = Settings(_env_file=None, database_url=f"{scheme}://user:pass@database/plateful")
    assert settings.database_url == "postgresql+asyncpg://user:pass@database/plateful"


@pytest.mark.asyncio
async def test_readiness_checks_database():
    session = AsyncMock()
    assert await readiness(session) == {"status": "ok", "database": "ok"}
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_reports_database_failure_without_credentials():
    session = AsyncMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("private details"))
    with pytest.raises(HTTPException) as error:
        await readiness(session)
    assert error.value.status_code == 503
    assert error.value.detail == "Database unavailable"
