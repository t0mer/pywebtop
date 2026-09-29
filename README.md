# pywebtop


[![PyPI version](https://badge.fury.io/py/pywebtop.svg)](https://badge.fury.io/py/pywebtop)
[![Python Versions](https://img.shields.io/pypi/pyversions/pywebtop.svg)](https://pypi.org/project/pywebtop/)
[![License](https://img.shields.io/github/license/t0mer/pywebtop.svg)](https://github.com/t0mer/pywebtop/blob/main/LICENSE)

An unofficial async Python API wrapper for **Webtop** (the SmartSchool educational platform used by Israeli schools). This library gives you easy access to Webtop's student portal API endpoints for retrieving the student dashboard, homework, schedules, messages, notifications, discipline events, and more.

> **Unofficial project.** pywebtop is not affiliated with, endorsed by, or supported by SmartSchool or Webtop. It talks to the same private web API that the Webtop site uses, which can change without notice. Use it only with your own account or your own children's accounts. See [Security & Privacy](#security--privacy).

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Error Handling](#error-handling)
- [Authentication Details](#authentication-details)
- [Endpoints Used](#endpoints-used)
- [Configuration](#configuration)
- [Logging](#logging)
- [Security & Privacy](#security--privacy)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

## Features

- 🔐 **Async/Await Support** - Built on `httpx` for modern async Python
- 📚 **Student Portal Access** - Log in and retrieve the student dashboard
- 📖 **Homework & Assignments** - Get homework details by class
- 📅 **Schedule/Timetable** - Retrieve pupil schedules for any week
- 💬 **Messaging System** - Access the message inbox with paging, read-status filter, and search
- 🔔 **Notifications** - Get unread notifications and notification settings
- 📊 **Discipline Events** - Retrieve behavior/discipline records
- 👥 **Multi-Student Support** - Discover and switch between siblings/linked accounts
- 🧰 **Raw Request Helper** - Call any other Webtop endpoint with the authenticated `request()` method
- ⚙️ **Configurable** - Custom base URL, timeout, and auto-login support

## Installation

Install via pip:

```bash
pip install pywebtop
```

Or from source:

```bash
git clone https://github.com/t0mer/pywebtop.git
cd pywebtop
pip install -e .
```

The package is installed as `pywebtop`, but it is imported as `webtop`:

```python
from webtop import WebtopClient
```

### Requirements

- Python 3.8+
- `httpx>=0.25,<1.0` (the only runtime dependency)
- A Webtop (SmartSchool) username and password

## Quick Start

### Basic Usage

```python
import asyncio
from webtop import WebtopClient

async def main():
    # Create the client; the connection is closed when the block exits
    async with WebtopClient(username="your_username", password="your_password") as client:
        # With auto_login=True (the default) the first API call logs in for you.
        # Calling login() explicitly gives you the session object right away.
        session = await client.login()
        print(f"Logged in as: {session.first_name} {session.last_name}")

        # Get the student dashboard (raw JSON)
        dashboard = await client.get_students()
        print(dashboard)

asyncio.run(main())
```

### Without Auto-Login

If you prefer to control login manually:

```python
async with WebtopClient(
    username="your_username",
    password="your_password",
    auto_login=False
) as client:
    # Manually call login; any API call before this raises WebtopLoginError
    session = await client.login()

    # Now make requests
    dashboard = await client.get_students()
```

## API Reference

All methods are coroutines (`await` them). Apart from `login()`, `switch_student()`, `get_linked_students()`, and `request()`, every endpoint method returns the **parsed JSON response as-is** (usually a `dict` with `status`, `data`, and error fields). The library does not model the response contents, so inspect the returned data for the fields your school returns.

The parameters of the data endpoint methods (`get_homework()`, `get_discipline_events()`, `get_notification_settings()`, `get_messages_inbox()`, `get_pupil_schedule()`) are **keyword-only**. `switch_student()` also accepts positional arguments.

### Client Initialization

```python
WebtopClient(
    username: str,
    password: str,
    *,
    data: str = "+Aabe7FAdVluG6Lu+0ibrA==",
    remember_me: bool = False,
    biometric_login: str = "",
    base_url: str = "https://webtopserver.smartschool.co.il",
    timeout: float = 20.0,
    auto_login: bool = True,
)
```

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `username` | (required) | Webtop username |
| `password` | (required) | Webtop password |
| `data` | `"+Aabe7FAdVluG6Lu+0ibrA=="` | Value sent as the `Data` field of the login request (see [Obtaining the `data` Parameter](#obtaining-the-data-parameter)) |
| `remember_me` | `False` | Sent as the `RememberMe` field of the login request |
| `biometric_login` | `""` | Sent as the `BiometricLogin` field of the login request |
| `base_url` | `"https://webtopserver.smartschool.co.il"` | Webtop server URL (a trailing `/` is stripped) |
| `timeout` | `20.0` | Request timeout in seconds |
| `auto_login` | `True` | Log in automatically before the first authenticated request |

### Methods

#### Authentication

##### `login()`
Perform login and establish the session. Returns a `WebtopSession`.

```python
session = await client.login()
# session.token - auth token
# session.user_id - user ID
# session.student_id - student ID
# session.school_id - school ID
# session.school_name - school name
# session.first_name, session.last_name - user names
# session.raw_login_data - the full "data" object from the login response
```

Calling `login()` again performs a fresh login and replaces the token.

##### `ensure_logged_in()`
Log in only if there is no session yet. Raises `WebtopLoginError` if there is no session and `auto_login=False`. The endpoint methods call this for you.

```python
await client.ensure_logged_in()
```

#### Managing Multiple Students

If a parent account is linked to multiple students (e.g., siblings, possibly in different schools), you can discover and switch between them.

##### `get_linked_students()`
Get a list of all students linked to the current account. Returns the `data` list from the response, and raises `WebtopRequestError` if the response has `status` other than `true`.

```python
students = await client.get_linked_students()
for student in students:
    print(f"Login: {student.get('studentLogin')}, ID: {student.get('studentId')}")
```

##### `switch_student()`
Switch the active session to a specific student. This replaces `client.session` (and the `webToken` cookie, if a new token is returned) for all subsequent requests. Returns the new `WebtopSession`.

```python
# Switch to a student using the studentId from get_linked_students()
new_session = await client.switch_student(student_id="<student-id>")
print(f"Switched to school: {new_session.school_name}")
```

**Parameters:**
- `student_id` - The `studentId` value of a linked student (string)
- `saved_user` - Optional, sent as `savedUser` (default: `""`)

`switch_student()` does not log in on its own, so call it after `login()` (or after any other API call). It raises `WebtopLoginError` when the server returns HTTP 400 or higher, a `status` that is not `true`, or no `data`. Timeouts, network errors, and non-JSON responses are not wrapped: they surface as the raw `httpx` or JSON decoding exception. After a switch, `session.student_id` is taken from the `id` field of the switch response.

#### Dashboard & Students

##### `get_students()`
Get the student dashboard (`InitDashboard`). Returns the raw JSON response. Depending on the account, `data` may be a list or a dictionary (for example, the multi-student example reads the child's name from `data["childrens"]`).

```python
dashboard = await client.get_students()
```

#### Homework & Assignments

##### `get_homework()`
Get homework for a specific class.

```python
homework = await client.get_homework(
    encrypted_student_id="<encrypted-student-id>",
    class_code=3,
    class_number=3,
)
```

**Parameters:**
- `encrypted_student_id` - Encrypted student ID (the `id` field of the login data, i.e. `client.session.raw_login_data["id"]`)
- `class_code` - Class code (int)
- `class_number` - Class number (int)

#### Schedule & Timetable

##### `get_pupil_schedule()`
Get the student schedule/timetable for a specific week.

```python
schedule = await client.get_pupil_schedule(
    week_index=0,           # 0 = current week
    view_type=0,            # schedule view type
    study_year=2026,        # school year (required)
    encrypted_student_id="<encrypted-student-id>",
    class_code=3,
    module_id=10,
)
```

**Parameters:**
- `week_index` - Week offset (0 = current week, 1 = next week, etc.; default: 0)
- `view_type` - Schedule view type (usually 0; default: 0)
- `study_year` - School year, e.g. 2026 (required)
- `encrypted_student_id` - Encrypted student ID from the login data (required)
- `class_code` - Class code (required)
- `module_id` - Module ID (default: 10)

#### Messaging

##### `get_messages_inbox()`
Get messages from the inbox with pagination and filtering.

```python
messages = await client.get_messages_inbox(
    page_id=1,
    label_id=0,
    has_read=None,          # None, True, or False to filter
    search_query="",
)
```

**Parameters:**
- `page_id` - Page number (1-based, default: 1)
- `label_id` - Message label/category (default: 0)
- `has_read` - Filter by read status: `True`, `False`, or `None` for all (default: `None`)
- `search_query` - Free-text search (default: `""`)

#### Notifications

##### `get_preview_unread_notifications()`
Get a preview of unread notifications.

```python
notifications = await client.get_preview_unread_notifications()
```

##### `get_notification_settings()`
Get notification settings for the user.

```python
settings = await client.get_notification_settings(
    encrypted_student_id="<encrypted-student-id>",
)
```

**Parameters:**
- `encrypted_student_id` - Encrypted student ID from the login data

#### Discipline & Behavior

##### `get_discipline_events()`
Get student behavior/discipline events.

```python
discipline = await client.get_discipline_events(
    encrypted_student_id="<encrypted-student-id>",
    class_code=3,
)
```

**Parameters:**
- `encrypted_student_id` - Encrypted student ID from the login data
- `class_code` - Class code

#### Low-Level Requests

##### `request()`
Send an authenticated request to any Webtop path. It logs in first if needed (see `auto_login`), raises `WebtopRequestError` on timeouts, network errors, and HTTP status codes of 400 or higher, and returns the `httpx.Response`.

```python
resp = await client.request("POST", "/server/api/dashboard/InitDashboard", json={})
print(resp.json())
```

**Parameters:**
- `method` - HTTP method, e.g. `"POST"`
- `path` - Path relative to `base_url`
- `headers` - Optional extra headers (keyword-only)
- `**kwargs` - Passed to `httpx.AsyncClient.request()` (e.g. `json=`, `params=`)

### Session Properties

After login, access session information via `client.session` (a frozen `WebtopSession` dataclass). Accessing `client.session` before logging in raises `WebtopLoginError`.

```python
session = client.session
print(session.token)           # Auth token
print(session.user_id)         # User ID
print(session.student_id)      # Student ID
print(session.school_id)       # School ID
print(session.school_name)     # School name
print(session.first_name)      # First name
print(session.last_name)       # Last name
print(session.raw_login_data)  # Raw login response data
```

### Connection Management

#### Check Login Status

```python
if client.is_logged_in:
    print("Already logged in")
```

#### Manual Close

```python
await client.close()  # or use 'async with' for auto-close
```

## Examples

The `class_code` and `class_number` values below are placeholders. Where they come from depends on your school's data, so inspect `client.session.raw_login_data` and the `get_students()` response to find them. <!-- TODO: verify which login/dashboard fields hold ClassCode and ClassNumber -->

### Complete Example: Get Homework

```python
import asyncio
from webtop import WebtopClient

async def get_homework_example():
    async with WebtopClient(
        username="your_username",
        password="your_password"
    ) as client:
        session = await client.login()
        # The encrypted student ID is the "id" field of the login data
        encrypted_id = session.raw_login_data["id"]

        # Get homework
        homework = await client.get_homework(
            encrypted_student_id=encrypted_id,
            class_code=3,
            class_number=3,
        )
        print(homework)

asyncio.run(get_homework_example())
```

### Complete Example: Check Schedule

```python
import asyncio
from datetime import datetime
from webtop import WebtopClient

async def check_schedule():
    async with WebtopClient(
        username="your_username",
        password="your_password"
    ) as client:
        session = await client.login()

        # Get this week's schedule
        schedule = await client.get_pupil_schedule(
            week_index=0,
            study_year=2026,
            encrypted_student_id=session.raw_login_data["id"],
            class_code=3,
        )

        print(f"Schedule for week {datetime.now().isocalendar()[1]}:")
        print(schedule)

asyncio.run(check_schedule())
```

### Complete Example: Get Messages

```python
import asyncio
from webtop import WebtopClient

async def check_messages():
    async with WebtopClient(
        username="your_username",
        password="your_password"
    ) as client:
        # Get unread messages
        messages = await client.get_messages_inbox(
            page_id=1,
            has_read=False,  # Only unread
        )

        items = messages.get("data") or []
        print(f"Found {len(items)} unread messages")
        for msg in items:
            # Field names as used in examples/multi_student_messages.py
            sender = msg.get("senderName") or "Unknown"
            print(f"  - {sender}: {msg.get('subject')}")

asyncio.run(check_messages())
```

### Multi-Student Example Script

[`examples/multi_student_messages.py`](https://github.com/t0mer/pywebtop/blob/main/examples/multi_student_messages.py) logs in, lists every linked student with `get_linked_students()`, switches to each one with `switch_student()`, reads the child's name from the dashboard, and prints up to 20 inbox messages per student.

To run it from a clone, replace the `<username>`, `<password>`, and `<data>` placeholders in the script, then:

```bash
python examples/multi_student_messages.py
```

The script prints student names and message subjects to the terminal.

## Error Handling

The library provides specific exceptions for error handling:

```python
import asyncio
from webtop import WebtopClient, WebtopLoginError, WebtopRequestError

async def main():
    try:
        async with WebtopClient(username="your_username", password="your_password") as client:
            dashboard = await client.get_students()
    except WebtopLoginError as e:
        print(f"Login failed: {e}")
    except WebtopRequestError as e:
        print(f"API request failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

asyncio.run(main())
```

**Exception Types:**
- `WebtopError` - Base exception class
- `WebtopLoginError` - Raised when login fails (including timeouts, network errors, and a login response that is not JSON), when the login response has no token, when you are not logged in and `auto_login=False`, when `client.session` is read before login, and when `switch_student()` gets HTTP 400 or higher, a `status` that is not `true`, or no `data`
- `WebtopRequestError` - Raised when an API request times out, fails at the network level, or returns HTTP 400 or higher; also raised by `get_linked_students()` when the response `status` is not `true`

Good to know:
- Apart from `get_linked_students()`, the endpoint methods do **not** check the `status` field of the JSON body. A response with `"status": false` and HTTP 200 is returned to you as-is, so check `status` yourself.
- `login()` wraps a non-JSON response in `WebtopLoginError`. `switch_student()` and the endpoint methods do not: a non-JSON body raises the underlying JSON decoding error, and `switch_student()` also lets `httpx` timeout and network errors through unwrapped.
- Exception messages can include the raw server response body.

## Authentication Details

### How Authentication Works

1. **Login Request** - `POST /server/api/user/LoginByUserNameAndPassword` with `UserName`, `Password`, `Data`, `RememberMe`, and `BiometricLogin`
2. **Status Check** - The response must have `"status": true`; otherwise `WebtopLoginError` is raised with the server's `errorDescription` and `errorId`
3. **Token Response** - The server returns `data.token` in the response
4. **Cookie-Based Auth** - The token is set as a cookie: `webToken=<token>`
5. **Subsequent Requests** - All API calls automatically include the `webToken` cookie

Only username/password login is implemented. There is no captcha, 2FA, or SSO handling, and the token is not refreshed automatically. If the token expires, requests may fail with `WebtopRequestError`, or they may return a `"status": false` body without raising an exception; in either case call `await client.login()` again or create a new client. <!-- TODO: verify token lifetime and the status code Webtop returns for an expired token -->

### Cookie Management

Authentication is handled automatically via httpx's cookie jar. The token is stored as a cookie and included in all subsequent requests. Every request is also sent with `Content-Type: application/json; charset=utf-8`, and redirects are followed.

### Obtaining the `data` Parameter

The `data` parameter is an opaque value that the Webtop login page sends in the `Data` field of the login request. To find your specific `data` value:

1. **Use Browser DevTools:**
   - Open your browser and navigate to the Webtop login page
   - Open Developer Tools (F12)
   - Go to the Network tab
   - Log in to Webtop
   - Find the `LoginByUserNameAndPassword` request
   - Check the request payload - the `Data` field contains the value to use

2. **Default Value:**
   - `+Aabe7FAdVluG6Lu+0ibrA==` is the library's default value
   - If login fails, capture your own `data` value using the method above

**Note:** The `data` parameter appears to be institution-specific. Once you find the correct value for your school, it should remain constant. <!-- TODO: verify what the Data field represents and whether it is institution-specific -->

## Endpoints Used

All requests go to `base_url` (default `https://webtopserver.smartschool.co.il`) and use `POST` with a JSON body.

| Method | Path | Request body |
|--------|------|--------------|
| `login()` | `/server/api/user/LoginByUserNameAndPassword` | `UserName`, `Password`, `Data`, `RememberMe`, `BiometricLogin` |
| `switch_student()` | `/server/api/user/ChangeUser` | `StudentId`, `institutionCode` (null), `savedUser`, `userType` (null) |
| `get_linked_students()` | `/server/api/user/GetMultipleUsersForUser` | `{}` |
| `get_students()` | `/server/api/dashboard/InitDashboard` | `{}` |
| `get_homework()` | `/server/api/dashboard/GetHomeWork` | `id`, `ClassCode`, `ClassNumber` |
| `get_discipline_events()` | `/server/api/dashboard/GetPupilDiciplineEvents` | `id`, `ClassCode` |
| `get_preview_unread_notifications()` | `/server/api/Menu/GetPreviewUnreadNotifications` | `{}` |
| `get_notification_settings()` | `/server/api/Notification/GetNotificationsSettings` | `id` |
| `get_messages_inbox()` | `/server/api/messageBox/GetMessagesInbox` | `PageId`, `LabelId`, `HasRead`, `SearchQuery` |
| `get_pupil_schedule()` | `/server/api/PupilCard/GetPupilScheduale` | `weekIndex`, `viewType`, `studyYear`, `studentID`, `classCode`, `moduleID` |

The spellings `GetPupilDiciplineEvents` and `GetPupilScheduale` are the server's own endpoint names.

## Configuration

pywebtop reads no environment variables or config files. Everything is set through the `WebtopClient` constructor (see [Client Initialization](#client-initialization)).

### Custom Base URL

If you use a custom Webtop server (it must expose the same `/server/api/...` paths):

```python
async with WebtopClient(
    username="your_username",
    password="your_password",
    base_url="https://custom-webtop-server.example.com"
) as client:
    # Use custom server
    dashboard = await client.get_students()
```

### Timeout Configuration

Adjust the request timeout:

```python
async with WebtopClient(
    username="your_username",
    password="your_password",
    timeout=30.0  # 30 seconds
) as client:
    dashboard = await client.get_students()
```

### Remember Me

Enable remember-me login:

```python
async with WebtopClient(
    username="your_username",
    password="your_password",
    remember_me=True
) as client:
    await client.login()
```

## Logging

pywebtop logs through the standard `logging` module under the `webtop.client` logger and does not configure any handlers itself. To see its output:

```python
import logging
logging.basicConfig(level=logging.INFO)
# or only this library:
logging.getLogger("webtop").setLevel(logging.DEBUG)
```

> **Warning: the logs contain personal data.** At `INFO` level the library logs the username, the logged-in user's first and last name and school name, the names after a student switch, and inbox search queries. `switch_student()` also logs the first characters of the student ID at `INFO`. At `ERROR` level it logs raw server response bodies and full `ChangeUser` / `GetMultipleUsersForUser` responses. Passwords and the token are not logged. Keep the `webtop` logger at `WARNING` or higher in production, and don't ship these logs to shared or third-party log services.

```python
logging.getLogger("webtop").setLevel(logging.WARNING)
```

## Security & Privacy

Webtop holds data about students, most of whom are minors: names, schools, class details, schedules, homework, messages, and behavior records. Treat everything this library returns as sensitive personal data.

- **Responsible use:** only use pywebtop with your own account or your own children's accounts. Don't use it to access other people's data, and follow your school's and SmartSchool's terms of use.
- **Credentials:** don't hard-code usernames and passwords in scripts you commit. Load them from environment variables or a secrets manager instead.
- **Token:** `session.token` (and `raw_login_data`) grants access to the account until it expires. Don't print, log, or store it.
- **Stored data:** if you save responses (for example, to feed a bot or a dashboard), keep them private, limit who can read them, and delete them when you no longer need them.
- **Logs and errors:** see [Logging](#logging). Exception messages can include raw response bodies too.
- **Request volume:** poll at a modest rate. The API is private and not meant for heavy automated use.

## Troubleshooting

- **`WebtopLoginError: Login returned status=false ...`** - The server rejected the login. Check the username and password; if they are correct, capture your school's `data` value (see [Obtaining the `data` Parameter](#obtaining-the-data-parameter)).
- **`WebtopLoginError: Not logged in and auto_login=False`** - Call `await client.login()` before other methods, or leave `auto_login=True`.
- **Methods return `"status": false`** - The endpoint methods return the JSON body as-is. Check the `errorDescription` in the response and the parameters you passed (for example, `encrypted_student_id` must be the encrypted `id` from the login data, not `studentId`).
- **Requests start failing after a while** - The session token may have expired. Call `await client.login()` again.
- **Empty or unexpected dashboard data** - `get_students()` can return `data` as a list or a dictionary depending on the account. Inspect the raw response.

## Project Structure

```
pywebtop/
├── webtop/
│   ├── __init__.py           # Package exports
│   ├── client.py             # Main WebtopClient class
│   ├── models.py             # Data models (WebtopSession)
│   └── exceptions.py         # Custom exceptions
├── examples/
│   └── multi_student_messages.py  # Linked-student discovery and messages
├── .github/workflows/
│   └── python-publish.yml    # Builds and publishes to PyPI
├── setup.py                  # Package setup
├── LICENSE                   # License text
└── README.md                 # This file
```

## Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/t0mer/pywebtop.git
cd pywebtop

# Install in development mode
pip install -e .
```

### Running Tests

The repository does not include an automated test suite yet. To check changes by hand, run the example script against your own account (see [Multi-Student Example Script](#multi-student-example-script)).

### Building and Publishing

```bash
pip install build
python -m build   # creates dist/*.tar.gz and dist/*.whl
```

The [Publish pypi package](https://github.com/t0mer/pywebtop/blob/main/.github/workflows/python-publish.yml) workflow builds the package and uploads it to PyPI when a GitHub release is published, or when it is started manually. It uses the `PYPI_API_TOKEN` repository secret. The version is set in `setup.py`.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](https://github.com/t0mer/pywebtop/blob/main/LICENSE) file for details.

> **Note:** the package metadata on PyPI (from `setup.py`) declares the MIT license, while the LICENSE file in this repository is Apache License 2.0.
<!-- TODO: verify license: LICENSE is Apache 2.0, but setup.py (and therefore PyPI) declares MIT -->

## Author

**Tomer Klein** - [GitHub](https://github.com/t0mer) - tomer.klein@gmail.com

## Disclaimer

This is an **unofficial** wrapper for the Webtop API. It is not affiliated with or endorsed by SmartSchool or Webtop. The API it uses is private and undocumented and may change or stop working at any time. Use at your own risk, only with accounts you are entitled to access, and ensure compliance with Webtop's Terms of Service.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Don't include real credentials, tokens, student IDs, or captured responses containing personal data in issues, PRs, or examples.

## Support

For issues, feature requests, or questions:
- Open an issue on [GitHub Issues](https://github.com/t0mer/pywebtop/issues)
- Contact the author

## Changelog

### Version 0.0.2
- Linked-student discovery (`get_linked_students()`)
- Student switching (`switch_student()`)
- `get_students()` handles both list and dictionary dashboard payloads
- Multi-student example script

### Version 0.0.1
- Initial release
- Login functionality
- Dashboard access
- Homework retrieval
- Schedule/timetable access
- Messaging system
- Notifications
- Discipline events tracking

## Related Projects

- [pymashov](https://github.com/t0mer/pymashov) - Async Python wrapper for Mashov, another Israeli school portal

---

**Last Updated:** September 2026
