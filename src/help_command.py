from __future__ import annotations
import inspect
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .bot import Bot, Context


class HelpCommand:
    """
    default help command. shows all commands or details for a specific one.

    disable with: bot = trixc.bot(..., help_command=none)
    """

    def __init__(self, *, name: str = "help", description: str = "Shows this help message."):
        self.name = name
        self.description = description
        self._bot: Optional["Bot"] = None

    def _attach(self, bot: "Bot") -> None:
        self._bot = bot

    async def send_help(self, ctx: "Context", command_name: Optional[str] = None) -> None:
        if command_name:
            await self._send_command_help(ctx, command_name)
        else:
            await self._send_all_help(ctx)

    async def _send_all_help(self, ctx: "Context") -> None:
        bot = self._bot
        prefix = bot.command_prefix
        bot_description = getattr(bot, "description", None)

        plain_lines = []
        html_lines = []

        if bot_description:
            plain_lines.append(f"{bot_description}\n")
            html_lines.append(f"<b>{bot_description}</b>")

        plain_lines.append("Commands:")
        html_lines.append("<b>Commands:</b>")

        for cmd_key in sorted(bot._commands.keys()):
            cmd = bot._commands[cmd_key]
            if cmd_key != cmd.name.lower():
                continue
            if cmd.hidden:
                continue
            doc = cmd.description.splitlines()[0] if cmd.description else "No description."
            plain_lines.append(f"{prefix}{cmd.name} - {doc}")
            html_lines.append(f"<code>{prefix}{cmd.name}</code> - {doc}")

        plain_lines.append(f"{prefix}{self.name} - {self.description}")
        html_lines.append(f"<code>{prefix}{self.name}</code> - {self.description}")

        plain_lines.append(f"\nType {prefix}{self.name} <command> for more info.")
        html_lines.append(f"<br>Type <code>{prefix}{self.name} &lt;command&gt;</code> for more info.")

        await ctx.reply(
            "\n".join(plain_lines),
            html="<br>\n".join(html_lines),
        )

    async def _send_command_help(self, ctx: "Context", command_name: str) -> None:
        bot = self._bot
        prefix = bot.command_prefix

        if command_name == self.name:
            await ctx.reply(
                f"{prefix}{self.name} [command]\n{self.description}",
                html=f"<code>{prefix}{self.name} [command]</code><br>\n{self.description}",
            )
            return

        cmd = bot.get_command(command_name)
        if cmd is None:
            await ctx.reply(
                f"Unknown command: {command_name}",
                html=f"❌ Unknown command: <code>{command_name}</code>",
            )
            return

        doc = (cmd.description or "No description provided.").strip()

        sig = inspect.signature(cmd.callback)
        params = []
        for pname, param in sig.parameters.items():
            if pname in ("ctx", "self"):
                continue
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                params.append(f"[{pname}...]")
            elif param.default is inspect.Parameter.empty:
                params.append(f"&lt;{pname}&gt;")
            else:
                params.append(f"[{pname}]")

        usage_args = " ".join(params)
        usage_plain = f"{prefix}{cmd.name}" + (
            f" {' '.join(p.replace('&lt;','<').replace('&gt;','>') for p in params)}"
            if params else ""
        )
        usage_html = f"<code>{prefix}{cmd.name}{(' ' + usage_args) if params else ''}</code>"

        plain_lines = [
            f"{prefix}{cmd.name}",
            f"Usage: {usage_plain}",
        ]
        html_lines = [
            f"<b>{prefix}{cmd.name}</b>",
            f"Usage: {usage_html}",
        ]

        if cmd.aliases:
            plain_lines.append(f"Aliases: {', '.join(cmd.aliases)}")
            html_lines.append(f"Aliases: <code>{'</code>, <code>'.join(cmd.aliases)}</code>")

        plain_lines.append(f"\n{doc}")
        html_lines.append(f"<br>\n{doc}")

        await ctx.reply(
            "\n".join(plain_lines),
            html="<br>\n".join(html_lines),
        )
