import datetime
from typing import List

import pydantic
from googleapiclient.discovery import build
from loguru import logger

from calendarlight.config.manager import ConfigManager


class APICalendar(pydantic.BaseModel):
    kind: str
    id: str
    summary: str
    timeZone: str
    selected: bool = False
    primary: bool = False
    deleted: bool = False

    def __str__(self) -> str:
        return f"{self.summary} ({self.id})"


class APICalendarsResponse(pydantic.BaseModel):
    kind: str
    etag: str
    nextSyncToken: str
    items: List[APICalendar]


class APICalendarEventDateTime(pydantic.BaseModel):
    dateTime: datetime.datetime | None
    timeZone: str | None


class APICalendarEvent(pydantic.BaseModel):
    kind: str
    etag: str
    id: str
    status: str
    htmlLink: str
    created: str
    updated: str
    summary: str | None
    description: str | None
    start: APICalendarEventDateTime
    end: APICalendarEventDateTime


class APICalendarEventsResponse(pydantic.BaseModel):
    kind: str
    etag: str
    nextPageToken: str | None
    items: List[APICalendarEvent]


class GoogleCalenderClient:
    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager

    def get_service(self):
        creds = self.config_manager.get_credentials()
        service = build("calendar", "v3", credentials=creds)
        return service

    def list_calendars(self):
        service = self.get_service()
        response = service.calendarList().list().execute()

        return APICalendarsResponse.parse_obj(response)

    def get_events(self, calendar_id: str = "primary"):
        service = self.get_service()
        logger.debug(f"Getting the upcoming 10 events for {calendar_id}")
        now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return APICalendarEventsResponse.parse_obj(response)
