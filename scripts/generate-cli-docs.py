"""Generate docs/cli.md from Click help output.

Usage:
    python scripts/generate-cli-docs.py

Run this after changing CLI commands/options to keep the docs in sync.
"""

from __future__ import annotations

import click
import cartoload.cli


def _format_opt_label(param: click.Option) -> str:
    """Format option switches with type hint, e.g. `-S, --sources PATH`."""
    parts = list(param.opts)
    if param.secondary_opts:
        parts.extend(param.secondary_opts)
    label = ", ".join(parts)
    if not param.is_flag:
        if isinstance(param.type, click.Choice):
            metavar = "{" + ",".join(param.type.choices) + "}"
        else:
            metavar = param.type.name.upper()
        if param.multiple:
            metavar += " ..."
        label += f" {metavar}"
    return f"`{label}`"


def _format_opt_desc(param: click.Option) -> str:
    """Format option description with default if non-trivial."""
    desc = param.help or ""
    default = param.default
    if default is not None and not isinstance(default, bool):
        val = str(default)
        if val not in ("Sentinel.UNSET", "None") and val not in desc:
            desc += f" (default: `{val}`)"
    return desc


def _format_usage(cmd: click.BaseCommand, full_path: str) -> str:
    """Build a usage line from the command's parameters."""
    parts = [full_path]
    has_opts = any(isinstance(p, click.Option) for p in cmd.params)
    any(isinstance(p, click.Argument) for p in cmd.params)
    if has_opts:
        parts.append("[OPTIONS]")
    for p in cmd.params:
        if isinstance(p, click.Argument):
            if p.required:
                parts.append(p.name.upper())
            else:
                parts.append(f"[{p.name.upper()}]")
    if hasattr(cmd, "commands") and cmd.commands:
        parts.append("COMMAND")
        parts.append("[ARGS]")
    return " ".join(parts)


def _format_command(cmd: click.BaseCommand, full_path: str) -> str:
    """Format a single command as markdown with definition lists."""
    md = f"### `{full_path}`\n\n"
    md += f"{cmd.help}\n\n"
    md += f"**Usage:** `{_format_usage(cmd, full_path)}`\n"

    # Arguments
    args = [p for p in cmd.params if isinstance(p, click.Argument)]
    if args:
        md += "\n**Arguments:**\n\n"
        for arg in args:
            md += f"`{arg.name.upper()}`\n"
            md += f":   {arg.type.name.capitalize()}\n\n"

    # Options
    opts = [
        p for p in cmd.params if isinstance(p, click.Option) and p.opts != ["--help"]
    ]
    if opts:
        md += "\n**Options:**\n\n"
        for opt in opts:
            md += f"{_format_opt_label(opt)}\n"
            md += f":   {_format_opt_desc(opt)}\n\n"

    # Subcommands
    if hasattr(cmd, "commands") and cmd.commands:
        md += "\n**Subcommands:**\n\n"
        for subname, subcmd in cmd.commands.items():
            md += f"`{subname}`\n"
            md += f":   {subcmd.help}\n\n"

    return md


def _walk_commands(cmd: click.BaseCommand, full_path: str) -> str:
    """Recursively format a command and all its subcommands."""
    md = _format_command(cmd, full_path)
    if hasattr(cmd, "commands") and cmd.commands:
        for subname, subcmd in cmd.commands.items():
            md += _walk_commands(subcmd, f"{full_path} {subname}")
    return md


def generate() -> str:
    main = cartoload.cli.main
    md = "# CLI Reference\n\n"
    md += f"{main.help}\n\n"
    md += f"**Usage:** `{_format_usage(main, 'cartoload')}`\n"

    # Top-level subcommands
    md += "\n**Subcommands:**\n\n"
    for name, cmd in main.commands.items():
        md += f"`{name}`\n"
        md += f":   {cmd.help}\n\n"

    # Detail sections — recurse into all commands and their subcommands
    for name, cmd in main.commands.items():
        md += "---\n\n"
        md += _walk_commands(cmd, f"cartoload {name}")

    return md + "\n"


if __name__ == "__main__":
    from pathlib import Path

    out = Path(__file__).resolve().parent.parent / "docs" / "cli.md"
    out.write_text(generate())
    print(f"Generated {out}")
