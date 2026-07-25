"""Adapters for the configured VOSpace Services and the local filesystem."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.local import LocalFileSystem

from canfar.client import HTTPClient
from canfar.exceptions.context import AuthContextError
from canfar.models.config import Configuration

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from fsspec.spec import AbstractFileSystem
    from fsspec_cli import AsyncFilesystemSource
    from pydantic import SecretStr


def _vospace(
    name: str,
    *,
    token: str | SecretStr | None = None,
    certificate: Path | None = None,
) -> AsyncFilesystemSource:
    """Return a fresh authenticated async filesystem source.

    Args:
        name: Storage Name of the configured VOSpace Service.
        token: Runtime bearer token, preferred over any saved credential.
        certificate: Runtime X.509 certificate path.

    Returns:
        AsyncFilesystemSource: Factory yielding one authenticated filesystem.
    """

    @asynccontextmanager
    async def source() -> AsyncIterator[AbstractFileSystem]:
        config = Configuration()  # ty: ignore[missing-argument]
        endpoint, idp = config._resolve_storage(name)  # noqa: SLF001
        try:
            client_kwargs: dict[str, Any] = {
                "config": config,
                "authentication_idp": idp,
                "url": endpoint,
            }
            if token is not None:
                client_kwargs["token"] = token
            if certificate is not None:
                client_kwargs["certificate"] = certificate
            client = HTTPClient(
                **client_kwargs,
            )
            token_value, certfile = await client._materialize_credentials()  # noqa: SLF001
        except (KeyError, OSError, TypeError, ValueError):
            reason = "Credential cannot be used. Run 'canfar login' for this IDP."
            raise AuthContextError(idp, reason) from None

        from vosfs import VOSpaceFileSystem  # noqa: PLC0415

        if token_value is not None:
            filesystem = VOSpaceFileSystem(
                endpoint,
                token=token_value,
                asynchronous=True,
                skip_instance_cache=True,
            )
        else:
            assert certfile is not None
            filesystem = VOSpaceFileSystem(
                endpoint,
                certfile=certfile,
                asynchronous=True,
                skip_instance_cache=True,
            )
        try:
            yield filesystem
        finally:
            await filesystem.aclose()

    return source


@asynccontextmanager
async def _local() -> AsyncIterator[AbstractFileSystem]:
    """Yield a fresh asynchronous wrapper around the local filesystem.

    Yields:
        AbstractFileSystem: An async-wrapped local filesystem.
    """
    yield AsyncFileSystemWrapper(
        LocalFileSystem(skip_instance_cache=True),
        asynchronous=True,
    )


def sources() -> dict[str, AsyncFilesystemSource]:
    """Build the mapped storage sources for one data command invocation.

    Every configured VOSpace Service is mapped by its Storage Name, plus the
    always-available ``local`` filesystem.

    Returns:
        dict[str, AsyncFilesystemSource]: Sources keyed by Storage Name.
    """
    config = Configuration()  # ty: ignore[missing-argument]
    mapped = {
        name: _vospace(name)
        for server in config.servers.values()
        for name in server.storage
    }
    mapped["local"] = _local
    return mapped
