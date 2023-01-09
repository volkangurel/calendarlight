import asyncio
import datetime
from typing import List, Tuple

import pydantic
from busylight.lights import NoLightsFound
from busylight.manager import LightManager
from loguru import logger
from yaml import parser, safe_load

from calendarlight.config.manager import (
    CalendarLightConfig,
    ConfigManager,
    UserConfigCalendar,
)
from calendarlight.google.calendar import APICalendarEvent, GoogleCalenderClient

# sync events from Google Calendar every 15 minutes
CALENDAR_SYNC_PERIOD = 1 * 60  # 1 minutes

OFF_COLOR = (0, 0, 0)

light_manager = LightManager()


@pydantic.dataclasses.dataclass
class LightEvent:
    calendar: UserConfigCalendar
    event: APICalendarEvent


class Runner:
    def __init__(self, config_manager: ConfigManager, calendar_client: GoogleCalenderClient) -> None:
        self.config_manager = config_manager
        self.calendar_client = calendar_client

        self.upcoming_events: List[LightEvent] = []

        self.last_color = None

    def fetch_calendar_events(self):
        logger.info("Fetching events from configured calendars")
        configured_calendars = self.config_manager.get_calendars()

        all_events = []
        for calendar in configured_calendars:
            logger.debug(f"Fetching events for: {calendar}")
            events = self.calendar_client.get_events(calendar.id)
            all_events.extend([LightEvent(calendar=calendar, event=event) for event in events.items])

        self.upcoming_events = all_events

    async def sync_calendar_loop(self):
        while True:
            await asyncio.sleep(CALENDAR_SYNC_PERIOD)
            self.fetch_calendar_events()

    async def execute_schedule(self) -> float:
        logger.debug("Executing schedule")
        now = datetime.datetime.now(datetime.timezone.utc)

        active_event_config = None

        for light_event in self.upcoming_events:
            logger.debug(f"Checking event: {light_event}")
            if light_event.event.start.dateTime < now and light_event.event.end.dateTime > now:
                logger.debug(f"Found active event: {light_event}")
                if light_event.calendar.light_config is None:
                    try:
                        # retain the last event config as the active one
                        active_event_config = CalendarLightConfig.parse_obj(
                            safe_load(light_event.event.description or "") or {}
                        )
                    except (pydantic.ValidationError, parser.ParserError):
                        logger.warning(f"Skipping invalid event config: {light_event.event.description}")
                        continue
                else:
                    active_event_config = light_event.calendar.light_config

        if active_event_config is None:
            logger.debug("No active event config found. Turning light off")
            await self.set_light_color(OFF_COLOR)
        else:
            logger.debug(f"Active event config found: {active_event_config}")
            if active_event_config.action == "on":
                await self.set_light_color(active_event_config.rgb)

        delta = datetime.timedelta(minutes=1)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_minute = (now + delta).replace(microsecond=0, second=1)  # 1 seconds past the next minute
        time_until_next_minute = next_minute - now
        wait_seconds = time_until_next_minute.seconds + (next_minute - now).microseconds / 1e6
        logger.debug(f"Next execution scheduled at: {next_minute}, waiting {wait_seconds} seconds")
        return wait_seconds

    async def set_light_color(self, color: Tuple[int, int, int]):
        if self.last_color == color:
            logger.debug(f"Skipping light color update to {color}, color is the same")
            return
        logger.debug(f"Setting light color to: {color}")
        try:
            selected_lights = light_manager.selected_lights()
        except NoLightsFound:
            logger.warning("No lights found. Skipping")
            return
        await light_manager.on_supervisor(color, selected_lights)
        self.last_color = color

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
