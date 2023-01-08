import asyncio
import datetime
from typing import List, Tuple

import pydantic
from busylight.color import ColorLookupError, parse_color_string
from busylight.manager import LightManager
from loguru import logger
from yaml import parser, safe_load

from calendarlight.config.manager import ConfigManager
from calendarlight.google.calendar import APICalendarEvent, GoogleCalenderClient

# sync events from Google Calendar every 15 minutes
CALENDAR_SYNC_PERIOD = 15 * 60  # 15 minutes

DEFAULT_COLOR = "red"
OFF_COLOR = (0, 0, 0)

light_manager = LightManager()


class CalenderEventConfig(pydantic.BaseModel):
    action: str = "on"
    color: str = DEFAULT_COLOR
    dim: pydantic.conint(ge=0, le=100) = 100

    @property
    def rgb(self) -> Tuple[int, int, int]:
        return parse_color_string(self.color, self.dim)

    @pydantic.validator("color", pre=True, always=True)
    def validate_color(cls, v, *, values, **kwargs):
        try:
            parse_color_string(v)
            return v
        except ColorLookupError:
            logger.warning(f"Invalid color: {v}. Defaulting to {DEFAULT_COLOR}")
            return DEFAULT_COLOR


class Runner:
    def __init__(
        self, config_manager: ConfigManager, calendar_client: GoogleCalenderClient
    ) -> None:
        self.config_manager = config_manager
        self.calendar_client = calendar_client

        self.upcoming_events: List[APICalendarEvent] = []

    def fetch_calendar_events(self):
        logger.info("Fetching events from configured calendars")
        configured_calendars = self.config_manager.get_calendars()

        all_events = []
        for calendar in configured_calendars:
            logger.debug(f"Fetching events for: {calendar}")
            events = self.calendar_client.get_events(calendar.id)
            all_events.extend(events.items)

        self.upcoming_events = all_events

    async def sync_calendar_loop(self):
        while True:
            await asyncio.sleep(CALENDAR_SYNC_PERIOD)
            self.fetch_calendar_events()

    async def execute_schedule(self) -> int:
        logger.debug("Executing schedule")
        now = datetime.datetime.now(datetime.timezone.utc)

        active_event_config = None

        for event in self.upcoming_events:
            if event.start.dateTime < now and event.end.dateTime > now:
                logger.debug(f"Found active event: {event}")
                try:
                    # retain the last event config as the active one
                    active_event_config = CalenderEventConfig.parse_obj(
                        safe_load(event.description or "") or {}
                    )
                except (pydantic.ValidationError, parser.ParserError):
                    logger.warning(
                        f"Skipping invalid event config: {event.description}"
                    )
                    continue

        if active_event_config is None:
            logger.debug("No active event config found. Turning light off")
            await self.set_light_color(OFF_COLOR)
        else:
            logger.debug(f"Active event config found: {active_event_config}")
            if active_event_config.action == "on":
                await self.set_light_color(active_event_config.rgb)

        delta = datetime.timedelta(minutes=1)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_minute = (now + delta).replace(
            microsecond=0, second=1
        )  # 1 second past the next minute
        wait_seconds = (next_minute - now).seconds
        logger.debug(f"Next schedule execution at: {next_minute}")
        return wait_seconds

    async def set_light_color(self, color: Tuple[int, int, int]):
        await light_manager.on_supervisor(color, light_manager.selected_lights())

    async def execute_schedule_loop(self):
        """
        Loop to keep executing the schedule every minute
        """
        while True:
            sleep_time = await self.execute_schedule()
            await asyncio.sleep(sleep_time)

    async def run(self):
        """
        Check the calendar upon start and then every 15 minutes. Update an internal
        schedule with data from events during this check.
        Then execute the schedule every minute.
        """

        # fetch calendar events to fill the cache, then start the calendar sync task
        self.fetch_calendar_events()
        calendar_sync_task = asyncio.ensure_future(self.sync_calendar_loop())

        # execute the schedule
        await self.execute_schedule_loop()

        # once done, make sure we stop the sync task
        if not calendar_sync_task.cancelled():
            calendar_sync_task.cancel()
