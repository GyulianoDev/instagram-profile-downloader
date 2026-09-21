from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.request import urlopen


PROJECT_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = PROJECT_DIR / ".sessions"
BRAVE_SESSION_FILE = SESSIONS_DIR / "brave.session"
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._]{1,30}")
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)

Logger = Callable[[str], None]
PromptCallback = Callable[[], str]
CheckpointHandler = Callable[[str], None]


@dataclass(frozen=True)
class Configuration:
    profiles: tuple[str, ...]
    output: Path
    login: str | None = None
    browser: str | None = None
    full: bool = False
    update: bool = False


def normalize_profile(value: str) -> str:
    """Accepts @username, username, or the profile URL and returns only the username."""
    profile = value.strip()

    if "://" in profile:
        url = urlparse(profile)
        domain = (url.hostname or "").lower()
        if domain not in {"instagram.com", "www.instagram.com"}:
            raise argparse.ArgumentTypeError("the URL must be from instagram.com")

        parts = [part for part in url.path.split("/") if part]
        if len(parts) != 1:
            raise argparse.ArgumentTypeError("provide a profile URL, not a post URL")
        profile = parts[0]

    profile = profile.removeprefix("@").strip()
    # Accepts names copied from Markdown text, where _ and . may be escaped.
    profile = profile.replace(r"\_", "_").replace(r"\.", ".")
    if not USERNAME_PATTERN.fullmatch(profile):
        raise argparse.ArgumentTypeError(
            "invalid profile; use only letters, numbers, periods, and underscores"
        )
    return profile.lower()


def remove_duplicates(profiles: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(profiles))


def normalize_login(value: str) -> str:
    """Accepts a username, @username, or email used on Instagram."""
    login = value.strip()
    try:
        return normalize_profile(login)
    except argparse.ArgumentTypeError:
        pass

    if len(login) <= 254 and EMAIL_PATTERN.fullmatch(login):
        return login.lower()
    raise argparse.ArgumentTypeError("provide your Instagram username or a valid email address")


def session_file(login: str) -> Path:
    # Prevents exposing the username or email in the local filename.
    identifier = hashlib.sha256(login.encode("utf-8")).hexdigest()[:20]
    return SESSIONS_DIR / f"{identifier}.session"


def extract_checkpoint_url(message: str) -> str | None:
    match = re.search(r"Point your browser to (\S+) - follow", message)
    if not match:
        return None
    url = urljoin("https://www.instagram.com/", match.group(1))
    if (urlparse(url).hostname or "").lower() not in {"instagram.com", "www.instagram.com"}:
        return None
    return url


def instaloader_options(configuration: Configuration) -> dict[str, Any]:
    return {
        "dirname_pattern": str(configuration.output / "{target}"),
        "filename_pattern": "{shortcode}",
        "title_pattern": "{date_utc:%Y-%m-%d_%H-%M-%S}_{typename}",
        "download_pictures": True,
        "download_videos": True,
        "download_video_thumbnails": False,
        "download_comments": False,
        "save_metadata": False,
        "post_metadata_txt_pattern": "",
        "storyitem_metadata_txt_pattern": "",
        "resume_prefix": None,
        "sanitize_paths": True,
        "quiet": True,
    }


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


def _files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False

    def digest(path: Path) -> bytes:
        hasher = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.digest()

    return digest(first) == digest(second)


def _collision_free_destination(source: Path, folder: Path) -> Path:
    destination = folder / source.name
    if not destination.exists() or _files_equal(source, destination):
        return destination
    counter = 2
    while True:
        candidate = folder / f"{source.stem}_{counter}{source.suffix}"
        if not candidate.exists() or _files_equal(source, candidate):
            return candidate
        counter += 1


def organize_profile_folder(profile_folder: Path) -> tuple[int, int]:
    """Keeps only images, videos, and profile_data.txt in the profile folder."""
    images_folder = profile_folder / "images"
    videos_folder = profile_folder / "videos"
    images_folder.mkdir(parents=True, exist_ok=True)
    videos_folder.mkdir(parents=True, exist_ok=True)
    for file in list(profile_folder.rglob("*")):
        if not file.is_file():
            continue
        if file == profile_folder / "profile_data.txt":
            continue

        extension = file.suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            destination_folder = images_folder
        elif extension in VIDEO_EXTENSIONS:
            destination_folder = videos_folder
        elif extension in {".json", ".xz", ".txt", ".part", ".tmp"} or file.name == "id":
            file.unlink()
            continue
        else:
            continue

        if file.parent == destination_folder:
            continue

        destination = _collision_free_destination(file, destination_folder)
        if destination.exists() and _files_equal(file, destination):
            file.unlink()
        else:
            file.replace(destination)

    for folder in sorted(
        (item for item in profile_folder.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        if folder in {images_folder, videos_folder}:
            continue
        try:
            folder.rmdir()
        except OSError:
            pass

    image_count = sum(1 for item in images_folder.iterdir() if item.is_file())
    video_count = sum(1 for item in videos_folder.iterdir() if item.is_file())
    return image_count, video_count


def save_profile_data(profile: Any, profile_folder: Path) -> Path:
    profile._obtain_metadata()
    node = dict(getattr(profile, "_node", {}))
    address = node.get("business_address_json") or {}
    if isinstance(address, str):
        try:
            address = json.loads(address)
        except json.JSONDecodeError:
            address = {}
    if not isinstance(address, dict):
        address = {}

    city = node.get("city_name") or address.get("city_name") or address.get("city")
    state = node.get("region_name") or address.get("region_name") or address.get("region")
    location = ", ".join(str(value) for value in (city, state) if value)
    street = node.get("address_street") or address.get("street_address") or address.get("street")

    def display(value: Any) -> str:
        return str(value).strip() if value not in (None, "") else "Not provided"

    def attribute(name: str, default: Any = None) -> Any:
        try:
            return getattr(profile, name)
        except (AttributeError, KeyError):
            return default

    lines = [
        "PROFILE DATA",
        "",
        f"Username: @{attribute('username', 'desconhecido')}",
        f"Name: {display(attribute('full_name'))}",
        f"City: {display(location)}",
        f"Public address: {display(street)}",
        f"Category: {display(node.get('business_category_name') or node.get('category'))}",
        f"Website: {display(attribute('external_url'))}",
        f"Public email: {display(node.get('public_email'))}",
        f"Public phone: {display(node.get('public_phone_number'))}",
        f"Followers: {display(attribute('followers'))}",
        f"Following: {display(attribute('followees'))}",
        f"Posts: {display(attribute('mediacount'))}",
        f"Private profile: {'Yes' if attribute('is_private', False) else 'No'}",
        f"Verified profile: {'Yes' if attribute('is_verified', False) else 'No'}",
        "",
        "Biography:",
        display(attribute('biography')),
        "",
    ]
    profile_folder.mkdir(parents=True, exist_ok=True)
    destination = profile_folder / "profile_data.txt"
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def profile_download_options(configuration: Configuration) -> dict[str, bool]:
    return {
        "profile_pic": True,
        "posts": True,
        "tagged": configuration.full,
        "igtv": configuration.full,
        "highlights": configuration.full,
        "stories": configuration.full,
        "fast_update": configuration.update,
        "raise_errors": True,
        # The dedicated Reels endpoint often returns 401 without a session.
        "reels": configuration.full,
    }


def _connect_logs(loader: Any, logger: Logger) -> None:
    context = loader.context

    def log_text(*messages: object, sep: str = "", end: str = "\n", flush: bool = False) -> None:
        del flush
        text = sep.join(str(message) for message in messages)
        if end and text:
            text += end.rstrip("\n")
        if text:
            logger(text)

    def error(message: object, repeat_at_end: bool = True) -> None:
        text = str(message)
        logger(f"ERROR: {text}")
        if repeat_at_end:
            context.error_log.append(text)

    context.log_text = log_text
    context.error = error


def _create_loader(module: Any, configuration: Configuration, logger: Logger) -> Any:
    loader = module.Instaloader(**instaloader_options(configuration))
    _connect_logs(loader, logger)
    return loader


def _protect_session(session_file: Path) -> None:
    if not session_file.exists():
        return
    try:
        os.chmod(session_file, 0o600)
    except OSError:
        pass


def _authenticate(
    module: Any,
    loader: Any,
    configuration: Configuration,
    password: str | None,
    get_password: PromptCallback,
    get_2fa_code: PromptCallback,
    logger: Logger,
) -> Any:
    assert configuration.login is not None
    user = configuration.login
    SESSIONS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    session_path = session_file(user)

    if session_path.exists():
        try:
            loader.load_session_from_file(user, filename=str(session_path))
            usuario_da_sessao = loader.test_login()
            if usuario_da_sessao:
                logger(f"Session for @{usuario_da_sessao} loaded securely.")
                return loader
            logger("The saved session has expired; you will need to log in again.")
        except module.exceptions.InstaloaderException as error:
            logger(f"Could not reuse the saved session: {error}")

        loader.close()
        loader = _create_loader(module, configuration, logger)

    current_password = password or get_password()
    if not current_password:
        raise module.exceptions.LoginException("provide the password to log in")

    logger(f"Logging in as @{user}...")
    try:
        loader.login(user, current_password)
    except module.exceptions.TwoFactorAuthRequiredException:
        code = get_2fa_code().strip()
        if not code:
            raise module.exceptions.LoginException("authentication code not provided")
        loader.two_factor_login(code)

    loader.save_session_to_file(filename=str(session_path))
    _protect_session(session_path)
    logger("Login completed; only the session cookie was saved.")
    return loader


def _authenticate_with_browser(
    module: Any,
    loader: Any,
    browser: str,
    logger: Logger,
) -> Any:
    if browser == "brave":
        if _load_saved_brave_session(module, loader, logger):
            return loader
        instagram_cookies = _open_brave_login(module, logger)
    else:
        try:
            browser_cookie3 = importlib.import_module("browser_cookie3")
        except ImportError as error:
            raise module.exceptions.LoginException(
                "install browser-cookie3 to use the browser session"
            ) from error

        browsers = {
            "chrome": browser_cookie3.chrome,
            "edge": browser_cookie3.edge,
            "firefox": browser_cookie3.firefox,
        }
        reader = browsers.get(browser)
        if reader is None:
            raise module.exceptions.LoginException("unsupported browser")

        logger(f"Reading the Instagram session from {browser.title()}...")
        try:
            instagram_cookies = {
                cookie.name: cookie.value
                for cookie in reader(domain_name="instagram.com")
                if "instagram" in cookie.domain.lower()
            }
        except Exception as error:
            raise module.exceptions.LoginException(
                f"could not read the cookies from {browser.title()}; "
                "close the browser and try again"
            ) from error

    if not instagram_cookies:
        raise module.exceptions.LoginException(
            f"no Instagram session was found in {browser.title()}; "
            "log in to instagram.com in that browser first"
        )

    loader.context.update_cookies(instagram_cookies)
    user = loader.test_login()
    if not user:
        raise module.exceptions.LoginException(
            f"the Instagram session in {browser.title()} is not valid"
        )

    loader.context.username = user
    SESSIONS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    session_path = session_file(user)
    loader.save_session_to_file(filename=str(session_path))
    _protect_session(session_path)
    if browser == "brave":
        loader.save_session_to_file(filename=str(BRAVE_SESSION_FILE))
        _protect_session(BRAVE_SESSION_FILE)
    logger(f"Session for @{user} imported from {browser.title()} successfully.")
    return loader


def _load_saved_brave_session(
    module: Any,
    loader: Any,
    logger: Logger,
) -> bool:
    if BRAVE_SESSION_FILE.exists():
        candidate = BRAVE_SESSION_FILE
    elif SESSIONS_DIR.exists():
        sessions = [
            path
            for path in SESSIONS_DIR.glob("*.session")
            if path != BRAVE_SESSION_FILE
        ]
        if len(sessions) != 1:
            return False
        candidate = sessions[0]
    else:
        return False

    logger("Checking the previously saved Brave session...")
    try:
        loader.load_session_from_file("brave", filename=str(candidate))
        user = loader.test_login()
    except module.exceptions.InstaloaderException as error:
        logger(f"The saved session could not be reused: {error}")
        return False

    if not user:
        logger("The saved session has expired; you will need to log in again.")
        return False

    loader.context.username = user
    if candidate != BRAVE_SESSION_FILE:
        loader.save_session_to_file(filename=str(BRAVE_SESSION_FILE))
        _protect_session(BRAVE_SESSION_FILE)
    logger(f"Session for @{user} reused successfully.")
    return True


def _find_brave() -> Path | None:
    candidates: list[Path] = []
    for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        root_path = os.environ.get(variable)
        if root_path:
            candidates.append(
                Path(root_path) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
            )
    return next((path for path in candidates if path.exists()), None)


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _wait_for_brave_websocket(process: Any, port: int, seconds: int = 30) -> str:
    deadline = time.monotonic() + seconds
    url = f"http://127.0.0.1:{port}/json/version"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Brave closed during startup")
        try:
            with urlopen(url, timeout=1) as response:
                data = json.loads(response.read().decode("utf-8"))
            websocket_url = data.get("webSocketDebuggerUrl")
            if websocket_url:
                return str(websocket_url)
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    raise TimeoutError("Brave did not finish starting within 30 seconds")


def _execute_cdp_command(
    connection: Any,
    identifier: int,
    method: str,
) -> dict[str, Any]:
    connection.send(json.dumps({"id": identifier, "method": method, "params": {}}))
    while True:
        message = json.loads(connection.recv())
        if message.get("id") != identifier:
            continue
        if "error" in message:
            detail = message["error"].get("message", "unknown error")
            raise RuntimeError(f"CDP: {detail}")
        return dict(message.get("result", {}))


def _close_isolated_brave(process: Any, connection: Any | None) -> None:
    if connection is not None:
        try:
            connection.send(json.dumps({"id": 999999, "method": "Browser.close", "params": {}}))
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        process.terminate()


def _open_brave_login(
    module: Any,
    logger: Logger,
) -> dict[str, str]:
    brave_path = _find_brave()
    if brave_path is None:
        raise module.exceptions.LoginException("Brave was not found on this computer")

    try:
        websocket = importlib.import_module("websocket")
    except ImportError as error:
        raise module.exceptions.LoginException(
            "install websocket-client to use secure Brave login"
        ) from error

    temporary_dir = Path(tempfile.mkdtemp(prefix="ig_brave_"))
    port = _free_local_port()
    process = None
    connection = None
    logger("Opening an isolated Brave window for Instagram...")
    try:
        process = subprocess.Popen(
            [
                str(brave_path),
                f"--user-data-dir={temporary_dir}",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={port}",
                "--new-window",
                "--disable-background-mode",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.instagram.com/accounts/login/",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        websocket_url = _wait_for_brave_websocket(process, port)
        connection = websocket.create_connection(
            websocket_url,
            timeout=3,
            suppress_origin=True,
        )
        logger(
            "Log in in this window. It will close automatically when "
            "the session is recognized."
        )

        deadline = time.monotonic() + 600
        identifier = 1
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("the window was closed before login was completed")
            result = _execute_cdp_command(
                connection,
                identifier,
                "Storage.getCookies",
            )
            identifier += 1
            instagram_cookies = {
                str(cookie["name"]): str(cookie["value"])
                for cookie in result.get("cookies", [])
                if "instagram" in str(cookie.get("domain", "")).lower()
            }
            if instagram_cookies.get("sessionid"):
                logger("Login recognized; closing only the isolated Brave window...")
                return instagram_cookies
            time.sleep(1)

        raise TimeoutError("timed out waiting for login in Brave")
    except module.exceptions.InstaloaderException:
        raise
    except Exception as error:
        raise module.exceptions.LoginException(
            f"could not obtain the session through the isolated Brave window: {error}"
        ) from error
    finally:
        _close_isolated_brave(process, connection)
        shutil.rmtree(temporary_dir, ignore_errors=True)


def get_compatible_profile(
    module: Any,
    context: Any,
    profile_name: str,
    logger: Logger,
) -> Any:
    """Works around the recent removal of a schema used by web_profile_info."""
    def find_exact() -> Any:
        results = module.TopSearchResults(context, profile_name)
        for found_profile in results.get_profiles():
            if found_profile.username.lower() == profile_name.lower():
                return found_profile
        raise module.exceptions.ProfileNotExistsException(
            f"Profile @{profile_name} was not found through the fallback route."
        )

    # When logged in, the search route followed by the ID lookup avoids the schema
    # removed from the web_profile_info endpoint.
    if context.is_logged_in:
        logger("Locating the profile through the compatible Instagram route...")
        return find_exact()

    try:
        return module.Profile.from_username(context, profile_name)
    except module.exceptions.InstaloaderException as error:
        if "ig_business_category_subvertical" not in str(error):
            raise

    logger(
        "Instagram removed a field used by the default lookup; "
        "trying the compatible route..."
    )
    return find_exact()


def run(
    configuration: Configuration,
    *,
    password: str | None = None,
    get_password: PromptCallback | None = None,
    get_2fa_code: PromptCallback | None = None,
    on_checkpoint: CheckpointHandler | None = None,
    logger: Logger = print,
) -> int:
    """Runs the download; the provided password is used only in memory."""
    has_authentication = bool(configuration.login or configuration.browser)
    if configuration.full and not has_authentication:
        logger("ERROR: full content requires login or a browser session.")
        return 2

    if importlib.util.find_spec("instaloader") is None:
        logger(
            "ERROR: Instaloader is not installed. Run "
            "python -m pip install -r requirements.txt"
        )
        return 2

    module = importlib.import_module("instaloader")
    configuration.output.mkdir(parents=True, exist_ok=True)
    loader: Any | None = None

    try:
        loader = _create_loader(module, configuration, logger)
        if configuration.browser:
            loader = _authenticate_with_browser(
                module,
                loader,
                configuration.browser,
                logger,
            )
        elif configuration.login:
            loader = _authenticate(
                module,
                loader,
                configuration,
                password,
                get_password or (lambda: getpass.getpass("Instagram password: ")),
                get_2fa_code or (lambda: input("Two-factor authentication code: ")),
                logger,
            )

        logger(f"Destination: {configuration.output}")
        logger(f"Profiles: {', '.join(configuration.profiles)}")
        if not has_authentication:
            logger(
                "Public mode: downloading visible posts. For dedicated Reels, "
                "stories and highlights, enable login and full content."
            )

        for profile_name in configuration.profiles:
            logger(f"Preparing @{profile_name}...")
            profile = get_compatible_profile(
                module,
                loader.context,
                profile_name,
                logger,
            )
            profile_folder = configuration.output / profile.username
            save_profile_data(profile, profile_folder)
            try:
                loader.download_profiles({profile}, **profile_download_options(configuration))
            finally:
                images, videos = organize_profile_folder(profile_folder)
                logger(
                    f"Folder organized: {images} image(s), {videos} video(s), "
                    "e profile_data.txt."
                )

        if loader.context.has_stored_errors:
            logger("The download finished with warnings or errors; check the messages above.")
            return 1

        logger("Download completed.")
        return 0
    except KeyboardInterrupt:
        logger("Download interrupted; progress was preserved.")
        return 130
    except module.exceptions.LoginException as error:
        url_checkpoint = extract_checkpoint_url(str(error))
        if url_checkpoint:
            logger(
                "ERROR: Instagram requires a security confirmation in the browser."
            )
            if on_checkpoint:
                on_checkpoint(url_checkpoint)
            else:
                logger(f"Open it, confirm the login, and try again: {url_checkpoint}")
            return 3
        logger(f"LOGIN ERROR: {error}")
        return 1
    except (module.exceptions.InstaloaderException, OSError) as error:
        logger(f"ERROR: {error}")
        logger("Do not retry rapidly if Instagram is rate-limiting access.")
        return 1
    except Exception as error:  # prevents the interface from closing without explaining the reason
        logger(f"UNEXPECTED ERROR: {error}")
        return 1
    finally:
        if loader is not None:
            loader.close()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Downloads Instagram profile content and organizes it only into "
            "images, videos, and profile data."
        )
    )
    parser.add_argument(
        "profiles",
        nargs="+",
        type=normalize_profile,
        help="one or more profiles: username, @username, or profile URL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "downloads",
        help="destination folder (default: ./downloads)",
    )
    parser.add_argument(
        "--login",
        type=normalize_login,
        help="your Instagram username or email; the password will be requested securely",
    )
    parser.add_argument(
        "--browser",
        choices=("brave", "chrome", "edge", "firefox"),
        help="reuses a session already open in the browser instead of asking for a password",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="includes Reels, current stories, highlights, tagged posts, and IGTV; requires --login",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="stops when already downloaded content is found, making updates faster",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.login and args.browser:
        parser.error("use only --login or --browser")
    if args.full and not (args.login or args.browser):
        parser.error("--full requires --login or --browser")
    configuration = Configuration(
        profiles=remove_duplicates(args.profiles),
        output=args.output.expanduser().resolve(),
        login=args.login,
        browser=args.browser,
        full=args.full,
        update=args.update,
    )
    return run(configuration)


if __name__ == "__main__":
    raise SystemExit(main())
