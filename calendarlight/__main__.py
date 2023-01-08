import asyncio
from dataclasses import dataclass
from typing import List

import typer
from loguru import logger
from rich.console import Console
from rich.prompt import IntPrompt

from calendarlight.config.manager import ConfigManager, UserConfigCalendar
from calendarlight.google.calendar import APICalendar, GoogleCalenderClient
from calendarlight.runner.runner import Runner

from . import __version__

app = typer.Typer()
config_app = typer.Typer()
app.add_typer(config_app, name="config")

config_manager = ConfigManager()
calendar_client = GoogleCalenderClient(config_manager)

console = Console()


@dataclass
class GlobalOptions:
    debug: bool = False


def report_version(value: bool) -> None:
    """typer.Option callback: prints the version string and exits."""
    if value:
        typer.secho(__version__, fg="blue")
        raise typer.Exit()


@app.callback(invoke_without_command=True, no_args_is_help=True)
def precommand_callback(
    ctx: typer.Context,
    debug: bool = typer.Option(
        False,
        "--debug",
        "-D",
        is_flag=True,
        help="Enable debugging output.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        is_flag=True,
        is_eager=True,
        callback=report_version,
    ),
) -> None:
    """Control USB connected presense lights via Google Calendar."""

    (logger.enable if debug else logger.disable)("calendarlight")

    options = ctx.ensure_object(GlobalOptions)

    options.debug = debug

    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit(code=1)

    logger.info(f"version {__version__}")
    logger.info(f"    cmd={ctx.invoked_subcommand!r}")


@app.command()
def login():
    config_manager.login()


@config_app.command(name="list")
def config_list():
    configured_calendars = config_manager.get_calendars()
    if not configured_calendars:
        console.print("No calendars configured")
        return

    for index, calendar in enumerate(configured_calendars):
        console.print(f"[{index}] {calendar}")


@config_app.command(name="add")
def config_add():
    available_calendars = calendar_client.list_calendars()
    configured_calendars = config_manager.get_calendars()

    new_calendars: List[APICalendar] = []
    for calendar in available_calendars.items:
        if calendar.id not in [c.id for c in configured_calendars]:
            new_calendars.append(calendar)

    for index, calendar in enumerate(new_calendars):
        console.print(f"[{index}] {calendar}")

    choice = None
    while choice is None:
        choice_index = IntPrompt.ask("Select a calendar to add", default=0)
        if choice_index < 0 or choice_index >= len(available_calendars.items):
            console.print(f"Invalid choice: {choice}")
        else:
            choice = available_calendars.items[choice_index]

    config_manager.add_calendar(
        UserConfigCalendar(id=choice.id, summary=choice.summary)
    )


@config_app.command(name="remove")
def config_remove():
    configured_calendars = config_manager.get_calendars()
    if not configured_calendars:
        console.print("No calendars configured")
        return

    for index, calendar in enumerate(configured_calendars):
        console.print(f"[{index}] {calendar}")

    choice = None
    while choice is None:
        choice_index = IntPrompt.ask("Select a calendar to remove", default=0)
        if choice_index < 0 or choice_index >= len(configured_calendars):
            console.print(f"Invalid choice: {choice}")
        else:
            choice = configured_calendars[choice_index]

    config_manager.remove_calendar(choice.id)


@app.command()
def run():
    asyncio.run(Runner(config_manager, calendar_client).run())


if __name__ == "__main__":
    app()
