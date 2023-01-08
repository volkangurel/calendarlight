"""
Control USB Attached Lights with Google Calendar!
"""
try:
    from importlib.metadata import distribution
except ModuleNotFoundError:
    from importlib_metadata import distribution

__version__ = distribution("calendarlight").version
