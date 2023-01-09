import pathlib
import shutil
import subprocess

SERVICE_NAME = "com.volkangurel.calendarlight"

CURRENT_DIR = pathlib.Path(__file__).parent
PLIST_TEMPLATE_FILE = CURRENT_DIR / "calendarlight.template.plist"

LAUNCH_AGENTS_DIR = pathlib.Path.home() / "Library" / "LaunchAgents"
INSTALLED_PLIST_FILE = LAUNCH_AGENTS_DIR / f"{SERVICE_NAME}.plist"

LOG_DIRECTORY = pathlib.Path.home() / "Library" / "Logs" / "calendarlight"


def install_launchd_service():
    """
    Install the calendarlight service on macOS.
    """
    print(PLIST_TEMPLATE_FILE)
    with open(PLIST_TEMPLATE_FILE, "r") as f:
        plist_content = f.read()
    plist_content = plist_content.format(
        service_name=SERVICE_NAME,
        executable=shutil.which("calendarlight"),
        log_out_file=LOG_DIRECTORY / "out.log",
        log_err_file=LOG_DIRECTORY / "err.log",
    )

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with open(INSTALLED_PLIST_FILE, "w") as f:
        f.write(plist_content)


def start_launchd_service():
    """
    Start the calendarlight service on macOS.
    """
    subprocess.run(["launchctl", "load", INSTALLED_PLIST_FILE])


def stop_launchd_service():
    """
    Stop the calendarlight service on macOS.
    """
    subprocess.run(["launchctl", "unload", INSTALLED_PLIST_FILE])
