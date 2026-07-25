"""Adapters for the configured VOSpace Services and the local filesystem."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fsspec.asyn import get_loop, sync
from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.local import LocalFileSystem

from canfar.client import HTTPClient
from canfar.exceptions.context import AuthContextError
from canfar.models.config import Configuration

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fsspec.spec import AbstractFileSystem
    from fsspec_cli import AsyncFilesystemSource
    from pydantic import SecretStr


LOCAL = "local"
"""Reserved Storage Identifier for the machine where the code runs."""

_LISTINGS_EXPIRY_SECONDS = 30
"""Seconds a cached directory listing stays valid within one command."""

_LISTINGS_MAX_PATHS = 1000
"""Maximum directory listings retained by one filesystem."""


def _vospace(
    name: str,
    *,
    token: str | SecretStr | None = None,
    certificate: Path | None = None,
) -> AsyncFilesystemSource:
    """Return a fresh authenticated async filesystem source.

    Args:
        name: Storage Identifier of the configured VOSpace Service.
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
                use_listings_cache=True,
                listings_expiry_time=_LISTINGS_EXPIRY_SECONDS,
                max_paths=_LISTINGS_MAX_PATHS,
            )
        else:
            assert certfile is not None
            filesystem = VOSpaceFileSystem(
                endpoint,
                certfile=certfile,
                asynchronous=True,
                skip_instance_cache=True,
                use_listings_cache=True,
                listings_expiry_time=_LISTINGS_EXPIRY_SECONDS,
                max_paths=_LISTINGS_MAX_PATHS,
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

    Every configured VOSpace Service is mapped by its Storage Identifier, plus the
    always-available ``local`` filesystem.

    Returns:
        dict[str, AsyncFilesystemSource]: Sources keyed by Storage Identifier.
    """
    config = Configuration()  # ty: ignore[missing-argument]
    mapped = {
        name: _vospace(name)
        for server in config.servers.values()
        for name in server.storage
    }
    mapped[LOCAL] = _local
    return mapped


def identifiers() -> list[str]:
    """Return every Storage Identifier this configuration can address.

    Returns:
        list[str]: Configured Storage Identifiers plus the reserved ``local``.
    """
    config = Configuration()  # ty: ignore[missing-argument]
    names = {name for server in config.servers.values() for name in server.storage}
    return [*sorted(names), LOCAL]


def filesystem(
    identifier: str,
    *,
    token: str | SecretStr | None = None,
    certificate: Path | str | None = None,
) -> AbstractFileSystem:
    """Return a synchronous filesystem for one Storage Identifier.

    Args:
        identifier: Storage Identifier, or ``local`` for the running machine.
        token: Runtime bearer token, preferred over any saved credential.
        certificate: Runtime X.509 certificate path.

    Returns:
        AbstractFileSystem: A ready, authenticated filesystem.

    Raises:
        KeyError: If ``identifier`` is not configured.
        AuthContextError: If the saved credential cannot be used.
    """
    if identifier == LOCAL:
        return LocalFileSystem()

    config = Configuration()  # ty: ignore[missing-argument]
    endpoint, idp = config._resolve_storage(identifier)  # noqa: SLF001
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
        client = HTTPClient(**client_kwargs)
        # fsspec's background loop, so this works inside a running loop too.
        token_value, certfile = sync(
            get_loop(),
            client._materialize_credentials,  # noqa: SLF001
        )
    except (KeyError, OSError, TypeError, ValueError):
        reason = "Credential cannot be used. Run 'canfar login' for this IDP."
        raise AuthContextError(idp, reason) from None

    from vosfs import VOSpaceFileSystem  # noqa: PLC0415

    credential: dict[str, Any] = (
        {"token": token_value} if token_value is not None else {"certfile": certfile}
    )
    return VOSpaceFileSystem(
        endpoint,
        **credential,
        skip_instance_cache=True,
        use_listings_cache=True,
        listings_expiry_time=_LISTINGS_EXPIRY_SECONDS,
        max_paths=_LISTINGS_MAX_PATHS,
    )


def fetch(identifier: str, path: str, destination: Path | str | None = None) -> Path:
    """Copy one remote object to local disk and return its path.

    Args:
        identifier: Storage Identifier holding ``path``.
        path: Absolute path of the object within that Storage Service.
        destination: Local path to write. Defaults to the object's name in the
            current working directory.

    Returns:
        Path: The local path now holding the object.
    """
    target = Path(destination) if destination is not None else Path(path).name
    target = Path(target)
    if target.is_dir():
        target = target / Path(path).name
    filesystem(identifier).get_file(path, str(target))
    return target


def __getattr__(name: str) -> AbstractFileSystem:
    """Return a filesystem for a Storage Identifier accessed as an attribute.

    Makes ``from canfar.storage import vault`` resolve to a ready filesystem for
    the ``vault`` Storage Identifier.

    Args:
        name: Attribute name, treated as a Storage Identifier.

    Returns:
        AbstractFileSystem: A ready, authenticated filesystem.

    Raises:
        AttributeError: If ``name`` is not a configured Storage Identifier.
    """
    if name.startswith("_"):
        message = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(message)
    known = identifiers()
    if name not in known:
        message = (
            f"module {__name__!r} has no attribute {name!r}; "
            f"configured Storage Identifiers are: {', '.join(known)}"
        )
        raise AttributeError(message)
    # Build outside the membership check so a failure to authenticate surfaces
    # as itself rather than as a missing attribute.
    return filesystem(name)


def __dir__() -> list[str]:
    """List the module's own names plus every Storage Identifier.

    Returns:
        list[str]: Names available on this module, for tab completion.
    """
    static = ["fetch", "filesystem", "identifiers", "sources", LOCAL]
    try:
        return sorted({*static, *identifiers()})
    except (OSError, ValueError):  # pragma: no cover - unreadable configuration
        return sorted(static)
