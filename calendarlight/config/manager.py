import pathlib
from typing import List, Tuple

import pydantic
from busylight.color import ColorLookupError, parse_color_string
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger
from yaml import safe_dump, safe_load

MANAGER_DIRECTORY = pathlib.Path(__file__).parent
CONFIG_DIRECTORY = pathlib.Path.home() / ".calendarlight"


# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

DEFAULT_COLOR = "red"


class CalendarLightConfig(pydantic.BaseModel):
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


class UserConfigCalendar(pydantic.BaseModel):
    id: str
    summary: str

    light_config: CalendarLightConfig | None = None

    def __str__(self) -> str:
        return f"{self.summary} ({self.id})"


class UserConfig(pydantic.BaseModel):
    calendars: List[UserConfigCalendar] = []


class ConfigManager:
    def __init__(self):
        self.credentials_path = MANAGER_DIRECTORY / "credentials.json"

        # token
        self.token_path = CONFIG_DIRECTORY / "token.json"
        self.auth_flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)

        # token
        self.user_config_path = CONFIG_DIRECTORY / "config.yaml"
        self.user_config_path.touch(exist_ok=True)
        with open(self.user_config_path, "r") as f:
            self.user_config = UserConfig.parse_obj(safe_load(f) or {})

    def login(self):
        logger.info("Logging in to Google Calendar API")
        creds = self.auth_flow.run_local_server(port=0)
        # Save the credentials to the config directory
        CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        with open(self.token_path, "w") as token:
            token.write(creds.to_json())

    def get_credentials(self):
        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise Exception("Please log in with `calendarlight login`")
        return creds

    def get_calendars(self):
        return self.user_config.calendars

    def add_calendar(self, calendar: UserConfigCalendar):
        self.user_config.calendars.append(calendar)
        self.flush_user_config()

    def edit_calendar(self, calendar: UserConfigCalendar):
        self.user_config.calendars = [calendar if c.id == calendar.id else c for c in self.user_config.calendars]
        self.flush_user_config()

    def remove_calendar(self, calendar_id: str):
        self.user_config.calendars = [c for c in self.user_config.calendars if c.id != calendar_id]
        self.flush_user_config()

    def flush_user_config(self):
        with open(self.user_config_path, "w") as f:
            safe_dump(self.user_config.dict(exclude_none=True), f)
