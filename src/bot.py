from __future__ import annotations

import asyncio
import inspect
import logging
import shlex
from typing import Any, Callable, Dict, List, Optional

from .client import MatrixClient
from .errors import CommandError, CheckFailure, CommandOnCooldown, CommandNotFound
from .help_command import HelpCommand

log = logging.getLogger("trixc.bot")


class Command:
    """a registered bot command."""

    def __init__(self, callback: Callable, name: str, *, aliases: Optional[List[str]] = None,
                 description: str = "", hidden: bool = False, **kwargs):
        self.callback = callback
        self.name = name
        self.aliases: List[str] = aliases or []
        self.description = description or inspect.getdoc(callback) or ""
        self.hidden = hidden
        self.checks: List[Callable] = getattr(callback, "__checks__", [])

    async def invoke(self, ctx) -> Any:
        for check_fn in self.checks:
            result = check_fn(ctx)
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise CheckFailure(f"Check failed for '{self.name}'")

        sig = inspect.signature(self.callback)
        params = [
            p for p in sig.parameters.values()
            if p.name not in ("ctx", "self")
        ]

        if not params:
            return await self.callback(ctx)

        kinds = {p.kind for p in params}
        has_var_positional = inspect.Parameter.VAR_POSITIONAL in kinds

        if has_var_positional:
            return await self.callback(ctx, *ctx.args, **ctx.kwargs)

        positional = [
            p for p in params
            if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        if ctx.args and len(ctx.args) > len(positional):
            fixed = list(ctx.args[:len(positional) - 1])
            fixed.append(" ".join(ctx.args[len(positional) - 1:]))
            return await self.callback(ctx, *fixed, **ctx.kwargs)

        return await self.callback(ctx, *ctx.args, **ctx.kwargs)

    def __repr__(self) -> str:
        return f"<Command name={self.name!r} aliases={self.aliases}>"


class Bot(MatrixClient):

    def __init__(self, homeserver: str, *, command_prefix: str = "!",
                 case_insensitive: bool = True, description: str = "",
                 help_command: Optional[HelpCommand] = ..., **options):
        super().__init__(homeserver, **options)
        self.command_prefix = command_prefix
        self.case_insensitive = case_insensitive
        self.description = description
        self._commands: Dict[str, Command] = {}
        self._cogs: Dict[str, Any] = {}
        self._pending_cog_loads: List[Any] = []

        self.add_listener("message", self._process_commands)

        if help_command is ...:
            help_command = HelpCommand()

        self._help_command: Optional[HelpCommand] = help_command
        if self._help_command is not None:
            self._help_command._attach(self)


    def command(self, name: Optional[str] = None, *, aliases: Optional[List[str]] = None,
                hidden: bool = False, **kwargs):
        
        def decorator(func: Callable) -> Command:
            cmd_name = name or func.__name__
            cmd = Command(func, cmd_name, aliases=aliases or [], hidden=hidden, **kwargs)
            self.add_command(cmd)
            return cmd
        return decorator

    def add_command(self, cmd: Command) -> None:
        """register a command object."""
        key = cmd.name.lower() if self.case_insensitive else cmd.name
        self._commands[key] = cmd
        for alias in cmd.aliases:
            self._commands[alias.lower() if self.case_insensitive else alias] = cmd

    def remove_command(self, name: str) -> Optional[Command]:
        """remove a command by name. returns the removed command or none."""
        key = name.lower() if self.case_insensitive else name
        cmd = self._commands.pop(key, None)
        if cmd:
            for alias in cmd.aliases:
                self._commands.pop(alias.lower() if self.case_insensitive else alias, None)
        return cmd

    def get_command(self, name: str) -> Optional[Command]:
        """get a command by name or alias."""
        key = name.lower() if self.case_insensitive else name
        return self._commands.get(key)

    @property
    def commands(self) -> List[Command]:
        """list of unique registered commands"""
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return result


    def listen(self, event: str):
        def decorator(func: Callable) -> Callable:
            self.add_listener(event, func)
            return func
        return decorator

    def event(self, func: Callable) -> Callable:
        name = func.__name__
        if name.startswith("on_"):
            name = name[3:]
        self.add_listener(name, func)
        return func


    def add_cog(self, cog: Any) -> None:
        cog_name = type(cog).__name__
        self._cogs[cog_name] = cog
        cog._bot = self

        for attr_name in dir(type(cog)):
            method = getattr(cog, attr_name, None)
            if method is None or not callable(method):
                continue
            if getattr(method, "__is_command__", False):
                cmd_name = getattr(method, "__command_name__", attr_name)
                attrs = getattr(method, "__command_attrs__", {})
                cmd = Command(method, cmd_name, **attrs)
                self.add_command(cmd)
            elif getattr(method, "__trixc_listener__", None):
                event = method.__trixc_listener__
                self.add_listener(event, method)

        if hasattr(cog, "cog_load"):
            self._pending_cog_loads.append(cog)

        log.info("Cog loaded: %s", cog_name)

    def remove_cog(self, name: str) -> Optional[Any]:
        """unload a cog by class name"""
        cog = self._cogs.pop(name, None)
        return cog

    async def remove_cog_async(self, name: str) -> Optional[Any]:
        """async version of remove_cog - also calls cog_unload()"""
        cog = self._cogs.pop(name, None)
        if cog and hasattr(cog, "cog_unload"):
            await cog.cog_unload()
        return cog

    def get_cog(self, name: str) -> Optional[Any]:
        return self._cogs.get(name)


    async def _process_commands(self, message) -> None:
        if not self.user or message.author.id == self.user.id:
            return

        content = message.content
        prefix = self.command_prefix

        if not content.startswith(prefix):
            return

        raw = content[len(prefix):]
        try:
            tokens = shlex.split(raw)
        except ValueError:
            tokens = raw.split()

        if not tokens:
            return

        cmd_name_raw = tokens[0]
        cmd_name = cmd_name_raw.lower() if self.case_insensitive else cmd_name_raw
        args = tokens[1:]
        if (
            self._help_command is not None
            and cmd_name == self._help_command.name.lower()
        ):
            from .context import Context
            ctx = Context(self, message, command_name=cmd_name_raw, prefix=prefix, args=args)
            arg = args[0] if args else None
            await self._help_command.send_help(ctx, arg)
            return

        cmd = self.get_command(cmd_name)
        if cmd is None:
            log.warning(
                "Command not found: '%s%s' (room=%s author=%s)",
                prefix, cmd_name_raw, message.room.id, message.author.id,
            )
            await self._dispatch("command_not_found", cmd_name_raw, message)
            return

        from .context import Context
        ctx = Context(self, message, command_name=cmd_name_raw, prefix=prefix, args=args)

        try:
            await self._dispatch("command", ctx)
            await cmd.invoke(ctx)
            await self._dispatch("command_completion", ctx)
        except CommandError as e:
            log.warning(
                "Command error '%s%s' (author=%s): %s",
                prefix, cmd_name_raw, message.author.id, e,
            )
            await self._dispatch("command_error", ctx, e)
        except Exception as e:
            log.error(
                "Unhandled exception in '%s%s' (author=%s)",
                prefix, cmd_name_raw, message.author.id,
                exc_info=True,
            )
            await self._dispatch("error", e, "command")


    def run(self, username: str, password: str) -> None:
        asyncio.run(self._run(username, password))

    async def start(self, username: str, password: str) -> None:
        await self._flush_pending_cog_loads()
        await self.login(username, password)
        await self._sync_forever()

    async def _flush_pending_cog_loads(self) -> None:
        for cog in self._pending_cog_loads:
            try:
                await cog.cog_load()
            except Exception as e:
                log.error("cog_load() failed for %s: %s", type(cog).__name__, e, exc_info=True)
        self._pending_cog_loads.clear()

    async def _run(self, username: str, password: str) -> None:
        await self._flush_pending_cog_loads()
        await self.login(username, password)
        try:
            await self._sync_forever()
        finally:
            await self.close()