import asyncio
from dataclasses import dataclass
from typing import List, TypeVar

import typer
from busylight.color import ColorLookupError, parse_color_string
from loguru import logger
from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from calendarlight.config.manager import (
    CalendarLightConfig,
    ConfigManager,
    UserConfigCalendar,
)
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
    debug_busylight: bool = typer.Option(
        False,
        "--debug-busylight",
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

    (logger.enable if debug_busylight else logger.disable)("busylight")
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


Calendar = TypeVar("Calendar", APICalendar, UserConfigCalendar)


def print_calendars(calendars: List[Calendar]) -> Calendar:
    if not calendars:
        console.print("No calendars configured")
        return
    for index, calendar in enumerate(calendars):
        console.print(f"[{index}] {calendar}")


def prompt_for_calendar(prompt: str, calendars: List[Calendar]) -> Calendar:
    print_calendars(calendars)

    choice = None
    while choice is None:
        choice_index = IntPrompt.ask(prompt, default=0)
        if choice_index < 0 or choice_index >= len(calendars):
            console.print(f"Invalid choice: {choice}")
        else:
            choice = calendars[choice_index]

    return choice


def prompt_for_light_config() -> CalendarLightConfig | None:
    have_config = Prompt.ask(
        "Would you like to configure default colors for all meetings on this calendar?",
        default="y",
        choices=["y", "n"],
    )
    if have_config == "n":
        return None
    while True:
        color = Prompt.ask("What color should be used when an event is on?", default="red")
        try:
            parse_color_string(color)
            break
        except ColorLookupError:
            console.print(f"Invalid color: {color}, try again")
            continue
    return CalendarLightConfig(color=color)


@config_app.command(name="list")
def config_list():
    configured_calendars = config_manager.get_calendars()
    print_calendars(configured_calendars)


@config_app.command(name="add")
def config_add():
    available_calendars = calendar_client.list_calendars()
    configured_calendars = config_manager.get_calendars()

    new_calendars: List[APICalendar] = []
    for calendar in available_calendars.items:
        if calendar.id not in [c.id for c in configured_calendars]:
            new_calendars.append(calendar)

    calendar = prompt_for_calendar("Select a calendar to add", new_calendars)
    light_config = prompt_for_light_config()

    config_manager.add_calendar(UserConfigCalendar(id=calendar.id, summary=calendar.summary, light_config=light_config))


@config_app.command(name="edit")
def config_edit():
    configured_calendars = config_manager.get_calendars()
    calendar = prompt_for_calendar("Select a calendar to edit", configured_calendars)
    calendar.light_config = prompt_for_light_config()
    config_manager.edit_calendar(calendar)


@config_app.command(name="remove")
def config_remove():
    configured_calendars = config_manager.get_calendars()
    calendar = prompt_for_calendar("Select a calendar to remove", configured_calendars)

    config_manager.remove_calendar(calendar.id)


@app.command()
def run():
    asyncio.run(Runner(config_manager, calendar_client).run())


if __name__ == "__main__":
    app()
