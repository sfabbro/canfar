"""Mount the upstream data command application."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from fsspec_cli import App
from typer.core import TyperGroup
from typer.main import get_group

from canfar.storages import sources

if TYPE_CHECKING:
    from typer._click.core import Command, Context

_DATA_GROUP_META_KEY = "canfar.data_group"


def _upstream_group() -> TyperGroup:
    """Build the released upstream application with CANFAR policy.

    Returns:
        TyperGroup: The upstream command group bound to configured sources.
    """
    return get_group(
        App(
            sources(),
            capabilities={"recursion": {"copy": True, "remove": False}},
        ).typer_app
    )


class _DataGroup(TyperGroup):
    """Resolve the embedded app lazily so imports perform no configuration I/O."""

    @staticmethod
    def _delegate(ctx: Context) -> TyperGroup:
        group = ctx.meta.get(_DATA_GROUP_META_KEY)
        if group is None:
            group = _upstream_group()
            ctx.meta[_DATA_GROUP_META_KEY] = group
        assert isinstance(group, TyperGroup)
        return group

    def list_commands(self, ctx: Context) -> list[str]:
        """List the unchanged upstream commands."""
        return self._delegate(ctx).list_commands(ctx)

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Resolve an unchanged upstream command."""
        return self._delegate(ctx).get_command(ctx, cmd_name)


data = typer.Typer(
    cls=_DataGroup,
    help="Operate on configured data sources.",
    add_completion=False,
    no_args_is_help=True,
)
