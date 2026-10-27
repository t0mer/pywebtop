from __future__ import annotations

import logging
from http.cookiejar import Cookie, DefaultCookiePolicy
from typing import Any, Dict, Optional

import httpx

from .exceptions import WebtopLoginError, WebtopRequestError
from .models import WebtopSession

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://webtopserver.smartschool.co.il"

# Max chars of a server response body echoed into logs / exception messages.
_MAX_BODY_SNIPPET = 200


def _snippet(text: str) -> str:
    """Truncate a response body so it can't flood logs or leak whole payloads."""
    if len(text) <= _MAX_BODY_SNIPPET:
        return text
    return text[:_MAX_BODY_SNIPPET] + "...[truncated]"


class WebtopClient:
    """
    Async client for Webtop (SmartSchool).

    Auth model:
      - Login returns JSON with data.token
      - Token must be sent as cookie: webToken=<token>
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        data: str = "+Aabe7FAdVluG6Lu+0ibrA==",
        remember_me: bool = False,
        biometric_login: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        auto_login: bool = True,
    ):
        base_url_obj = httpx.URL(base_url)
        if base_url_obj.scheme != "https":
            raise ValueError(f"base_url must use https, got: {base_url!r}")

        logger.info(f"Initializing WebtopClient, base_url: {base_url}")
        self._username = username
        self._password = password
        self._data = data
        self._remember_me = remember_me
        self._biometric_login = biometric_login

        self._base_url = base_url.rstrip("/")
        self._host = base_url_obj.host
        self._auto_login = auto_login

        try:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                headers={"Content-Type": "application/json; charset=utf-8"},
                follow_redirects=True,
            )
            # The default policy also sends a host-only cookie (webToken) to subdomains,
            # e.g. after a redirect; require an exact host match instead.
            self._http.cookies.jar.set_policy(
                DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain)
            )
            logger.debug(f"HTTP client created with timeout={timeout}s")
        except Exception as e:
            logger.error(f"Failed to create HTTP client: {e}")
            raise

        self._session: Optional[WebtopSession] = None

    async def __aenter__(self) -> "WebtopClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client connection."""
        try:
            logger.debug("Closing HTTP client connection")
            await self._http.aclose()
            logger.info("HTTP client connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing HTTP client: {e}")
            raise

    @property
    def is_logged_in(self) -> bool:
        return self._session is not None

    @property
    def session(self) -> WebtopSession:
        if not self._session:
            raise WebtopLoginError("Not logged in. Call await client.login() first.")
        return self._session

    def _set_token_cookie(self, token: str) -> None:
        """
        Store the auth token as the webToken cookie, scoped to the API host only
        and marked secure, so it is never sent to other hosts (e.g. on redirect)
        or over plain HTTP.
        """
        self._http.cookies.jar.set_cookie(
            Cookie(
                version=0,
                name="webToken",
                value=token,
                port=None,
                port_specified=False,
                domain=self._host,
                domain_specified=False,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
        )

    async def login(self) -> WebtopSession:
        """
        Perform ONLY the login call.
        """
        logger.info("Attempting to login")
        
        try:
            resp = await self._http.post(
                "/server/api/user/LoginByUserNameAndPassword",
                json={
                    "UserName": self._username,
                    "Password": self._password,
                    "Data": self._data,
                    "RememberMe": self._remember_me,
                    "BiometricLogin": self._biometric_login,
                },
            )
            logger.debug(f"Login request completed with status code: {resp.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"Login request timed out: {e}")
            raise WebtopLoginError(f"Login request timed out: {e}") from e
        except httpx.RequestError as e:
            logger.error(f"Login request failed: {e}")
            raise WebtopLoginError(f"Login request failed: {e}") from e

        if resp.status_code >= 400:
            body_snippet = _snippet(resp.text)
            logger.error(f"Login failed with status {resp.status_code}: {body_snippet}")
            raise WebtopLoginError(f"Login failed ({resp.status_code}): {body_snippet}")

        try:
            body = resp.json()
        except Exception as e:
            logger.error(f"Failed to parse login response as JSON: {e}")
            raise WebtopLoginError(f"Login response is not JSON: {e}") from e

        if body.get("status") is not True:
            error_desc = body.get('errorDescription')
            error_id = body.get('errorId')
            if error_desc is None and error_id is None:
                hint = (
                    " The server gave no reason; check the username/password and"
                    " the `data` value for your school (README: Obtaining the `data` Parameter)."
                )
            else:
                hint = ""
            logger.error(f"Login status is false. errorDescription={error_desc}, errorId={error_id}")
            raise WebtopLoginError(
                f"Login returned status=false. "
                f"errorDescription={error_desc!r}, errorId={error_id!r}.{hint}"
            )

        data = body.get("data") or {}
        token = data.get("token")
        if not token:
            logger.error("Login response missing token in data")
            raise WebtopLoginError("Login succeeded but data.token is missing")

        # ✅ Webtop requires token as cookie: webToken=<token>
        self._set_token_cookie(token)
        logger.debug("Authentication token set as cookie")

        self._session = WebtopSession(
            token=token,
            user_id=data.get("userId"),
            student_id=data.get("studentId"),
            school_id=data.get("schoolId"),
            school_name=data.get("schoolName"),
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
            raw_login_data=data,
        )
        logger.info(f"Login successful (school_id: {self._session.school_id})")
        return self._session

    async def ensure_logged_in(self) -> None:
        """Ensure user is logged in, auto-login if enabled."""
        if self._session:
            logger.debug("Already logged in, session exists")
            return
        if not self._auto_login:
            logger.warning("Not logged in and auto_login is disabled")
            raise WebtopLoginError("Not logged in and auto_login=False. Call await client.login().")
        logger.info("Auto-login triggered")
        await self.login()

    async def switch_student(self, student_id: str, saved_user: str = "") -> WebtopSession:
        """
        Switch the active student context (e.g. for siblings in different schools).
        
        POST /server/api/user/ChangeUser
        """
        logger.info("Switching student")
        try:
            try:
                resp = await self._http.post(
                    "/server/api/user/ChangeUser",
                    json={
                        "StudentId": student_id,
                        "institutionCode": None,
                        "savedUser": saved_user,
                        "userType": None
                    },
                )
            except httpx.TimeoutException as e:
                raise WebtopLoginError(f"Switch student request timed out: {e}") from e
            except httpx.RequestError as e:
                raise WebtopLoginError(f"Switch student request failed: {e}") from e
            
            if resp.status_code >= 400:
                body_snippet = _snippet(resp.text)
                logger.error(f"Switch student failed: {resp.status_code} {body_snippet}")
                raise WebtopLoginError(f"Switch student failed ({resp.status_code}): {body_snippet}")

            data = resp.json()
            if data.get("status") is not True:
                error_desc = data.get("errorDescription")
                error_id = data.get("errorId")
                logger.error(f"Switch student returned status=false. errorDescription={error_desc}, errorId={error_id}")
                raise WebtopLoginError(
                    f"Switch student returned status=false. "
                    f"errorDescription={error_desc!r}, errorId={error_id!r}"
                )
                 
            new_data = data.get("data")
            if not new_data:
                raise WebtopLoginError("Switch student succeeded but returned no data")

            # Update session
            token = new_data.get("token")
            # Update cookie if token changed
            if token:
                self._set_token_cookie(token)
            
            self._session = WebtopSession(
                token=token,
                user_id=new_data.get("userId"),
                student_id=new_data.get("id"), # Note: response uses 'id', request uses 'StudentId'
                school_id=new_data.get("schoolId"),
                school_name=new_data.get("schoolName"),
                first_name=new_data.get("firstName"),
                last_name=new_data.get("lastName"),
                raw_login_data=new_data,
            )
            logger.info(f"Switched student successfully (school_id: {self._session.school_id})")
            return self._session

        except Exception as e:
            logger.error(f"Failed to switch student: {e}")
            raise

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Authenticated request helper.
        Since auth is cookie-based (webToken), we only ensure login here.
        """
        logger.debug(f"Making {method} request to {path}")

        # Only relative paths: an absolute URL would bypass base_url and
        # could send the request (and anything in it) to another host.
        if not httpx.URL(path).is_relative_url or path.startswith("//"):
            raise ValueError(f"path must be relative to base_url, got: {path!r}")
        
        try:
            await self.ensure_logged_in()
        except WebtopLoginError as e:
            logger.error(f"Failed to ensure login before request: {e}")
            raise

        final_headers: Dict[str, str] = {}
        if headers:
            final_headers.update(headers)

        try:
            resp = await self._http.request(method, path, headers=final_headers, **kwargs)
            logger.debug(f"{method} {path} completed with status {resp.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"{method} {path} timed out: {e}")
            raise WebtopRequestError(f"{method} {path} timed out: {e}") from e
        except httpx.RequestError as e:
            logger.error(f"{method} {path} request error: {e}")
            raise WebtopRequestError(f"{method} {path} request error: {e}") from e

        if resp.status_code >= 400:
            body_snippet = _snippet(resp.text)
            logger.error(f"{method} {path} failed with status {resp.status_code}: {body_snippet}")
            raise WebtopRequestError(f"{method} {path} failed ({resp.status_code}): {body_snippet}")

        return resp

    async def get_linked_students(self) -> list[Dict[str, Any]]:
        """
        Get all students linked to this account (e.g. siblings in different schools).
        
        POST /server/api/user/GetMultipleUsersForUser
        """
        logger.info("Fetching linked students...")
        try:
            resp = await self.request(
                "POST", 
                "/server/api/user/GetMultipleUsersForUser", 
                json={}
            )
            data = resp.json()
            if data.get("status") is not True:
                error_desc = data.get("errorDescription")
                error_id = data.get("errorId")
                logger.error(f"Failed to get linked students. errorDescription={error_desc}, errorId={error_id}")
                raise WebtopRequestError(
                    f"Failed to get linked students. "
                    f"errorDescription={error_desc!r}, errorId={error_id!r}"
                )
            
            students = data.get("data", [])
            logger.info(f"Found {len(students)} linked students")
            return students
        except Exception as e:
            logger.error(f"Failed to get linked students: {e}")
            raise

    # -----------------------------
    # Endpoints
    # -----------------------------
    async def get_students(self) -> Any:
        """
        POST /server/api/dashboard/InitDashboard
        Body: {}
        Auth: cookie webToken
        """
        logger.info("Fetching students dashboard")
        try:
            resp = await self.request(
                "POST",
                "/server/api/dashboard/InitDashboard",
                json={},
            )
            data = resp.json()
            if isinstance(data, dict) and 'data' in data:
                 # Check if 'data' is the new structure (dict) or old (list)
                 payload = data['data']
                 if isinstance(payload, dict):
                     # New format: It returns a config object. The actual students might be in
                     # specific apps or the structure completely changed.
                     # For now, return the raw payload so the user can parse it,
                     # but log the structure for debugging.
                     logger.info(f"Dashboard returned dictionary payload with keys: {payload.keys()}")
                 elif isinstance(payload, list):
                     logger.info(f"Dashboard returned list of {len(payload)} students")
            
            return data
        except Exception as e:
            logger.error(f"Failed to get students: {e}")
            raise

    async def get_homework(
        self,
        *,
        encrypted_student_id: str,
        class_code: int,
        class_number: int,
    ) -> Any:
        """
        Get homework from Webtop.

        POST /server/api/dashboard/GetHomeWork

        Auth:
          - Cookie: webToken=<token>

        Params:
          encrypted_student_id: value from login data['id']
          class_code: ClassCode
          class_number: ClassNumber
        """
        logger.info(f"Fetching homework for class {class_code}-{class_number}")
        try:
            resp = await self.request(
                "POST",
                "/server/api/dashboard/GetHomeWork",
                json={
                    "id": encrypted_student_id,
                    "ClassCode": class_code,
                    "ClassNumber": class_number,
                },
            )
            data = resp.json()
            logger.info(f"Homework fetched successfully for class {class_code}-{class_number}")
            return data
        except Exception as e:
            logger.error(f"Failed to get homework for class {class_code}-{class_number}: {e}")
            raise

    async def get_discipline_events(
        self,
        *,
        encrypted_student_id: str,
        class_code: int,
    ) -> Any:
        """
        Get pupil discipline (behavior) events.

        POST /server/api/dashboard/GetPupilDiciplineEvents

        Auth:
          - Cookie: webToken=<token>

        Params:
          encrypted_student_id: value from login data['id']
          class_code: ClassCode
        """
        logger.info(f"Fetching discipline events for class {class_code}")
        try:
            resp = await self.request(
                "POST",
                "/server/api/dashboard/GetPupilDiciplineEvents",
                json={
                    "id": encrypted_student_id,
                    "ClassCode": class_code,
                },
            )
            data = resp.json()
            logger.info(f"Discipline events fetched successfully for class {class_code}")
            return data
        except Exception as e:
            logger.error(f"Failed to get discipline events for class {class_code}: {e}")
            raise
    
    async def get_preview_unread_notifications(self) -> Any:
        """
        Get preview of unread notifications.

        POST /server/api/Menu/GetPreviewUnreadNotifications

        Auth:
          - Cookie: webToken=<token>
        """
        logger.info("Fetching preview of unread notifications")
        try:
            resp = await self.request(
                "POST",
                "/server/api/Menu/GetPreviewUnreadNotifications",
                json={},  # empty body
            )
            data = resp.json()
            logger.info("Unread notifications preview fetched successfully")
            return data
        except Exception as e:
            logger.error(f"Failed to get unread notifications preview: {e}")
            raise
    
    async def get_notification_settings(
        self,
        *,
        encrypted_student_id: str,
    ) -> Any:
        """
        Get notification settings for the user.

        POST /server/api/Notification/GetNotificationsSettings

        Auth:
          - Cookie: webToken=<token>

        Params:
          encrypted_student_id: value from login data['id']
        """
        logger.info("Fetching notification settings")
        try:
            resp = await self.request(
                "POST",
                "/server/api/Notification/GetNotificationsSettings",
                json={
                    "id": encrypted_student_id,
                },
            )
            data = resp.json()
            logger.info("Notification settings fetched successfully")
            return data
        except Exception as e:
            logger.error(f"Failed to get notification settings: {e}")
            raise

    async def get_messages_inbox(
        self,
        *,
        page_id: int = 1,
        label_id: int = 0,
        has_read: Optional[bool] = None,
        search_query: str = "",
    ) -> Any:
        """
        Get messages inbox.

        POST /server/api/messageBox/GetMessagesInbox

        Auth:
          - Cookie: webToken=<token>

        Params:
          page_id: page number (1-based)
          label_id: message label/category
          has_read: filter by read status (True / False / None)
          search_query: free-text search
        """
        logger.info(f"Fetching messages inbox (page={page_id}, label={label_id}, has_read={has_read})")
        try:
            resp = await self.request(
                "POST",
                "/server/api/messageBox/GetMessagesInbox",
                json={
                    "PageId": page_id,
                    "LabelId": label_id,
                    # The server wants 0 / 1; JSON true / false is rejected with HTTP 400.
                    "HasRead": None if has_read is None else int(has_read),
                    "SearchQuery": search_query,
                },
            )
            data = resp.json()
            logger.info(f"Messages inbox fetched successfully (page={page_id})")
            return data
        except Exception as e:
            logger.error(f"Failed to get messages inbox (page={page_id}): {e}")
            raise

    async def get_message(self, *, message_id: str) -> Any:
        """
        Get one inbox message: its HTML body, attachments, recipients, and any
        signature / survey the parent is asked to fill in.

        POST /server/api/messageBox/GetMessagesInboxData

        Auth:
          - Cookie: webToken=<token>

        Params:
          message_id: `messageId` from get_messages_inbox() (stable across logins)

        Note: like opening it on the site, this marks the message as read.
        """
        logger.info("Fetching message")
        try:
            resp = await self.request(
                "POST",
                "/server/api/messageBox/GetMessagesInboxData",
                json={"MessageId": message_id, "FilterId": 0, "IsInbox": True, "hasRead": None},
            )
            data = resp.json()
            logger.info("Message fetched successfully")
            return data
        except Exception as e:
            logger.error(f"Failed to get message: {e}")
            raise

    async def download_file(self, *, file_url: str) -> bytes:
        """
        Download an attachment, e.g. a `fileUrl` from get_message()'s `filesList`.

        GET /server/api/stream/GetFile?token=<token>

        Auth:
          - Cookie: webToken=<token>

        Params:
          file_url: the attachment's `fileUrl`; only its `token` is used, so the
                    request always goes to base_url

        The token comes with the message, so download in the same session.
        """
        token = httpx.URL(file_url).params.get("token")
        if not token:
            raise ValueError("file_url has no token")
        logger.info("Downloading file")
        try:
            resp = await self.request("GET", "/server/api/stream/GetFile", params={"token": token})
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise
        if len(resp.content) <= 1:  # the site treats a 1-byte answer as "file not found"
            raise WebtopRequestError("GET /server/api/stream/GetFile: file not found")
        logger.info(f"File downloaded ({len(resp.content)} bytes)")
        return resp.content

    async def get_pupil_schedule(
        self,
        *,
        week_index: int = 0,
        view_type: int = 0,
        study_year: int,
        encrypted_student_id: str,
        class_code: int,
        module_id: int = 10,
    ) -> Any:
        """
        Get pupil schedule (timetable).

        POST /server/api/PupilCard/GetPupilScheduale

        Auth:
          - Cookie: webToken=<token>

        Params:
          week_index: week offset (0 = current week)
          view_type: schedule view type (usually 0)
          study_year: school year (e.g. 2026)
          encrypted_student_id: value from login data['id']
          class_code: ClassCode
          module_id: module identifier (usually 10)
        """
        logger.info(f"Fetching pupil schedule (year={study_year}, week={week_index}, class={class_code})")
        try:
            resp = await self.request(
                "POST",
                "/server/api/PupilCard/GetPupilScheduale",
                json={
                    "weekIndex": week_index,
                    "viewType": view_type,
                    "studyYear": study_year,
                    "studentID": encrypted_student_id,
                    "classCode": class_code,
                    "moduleID": module_id,
                },
            )
            data = resp.json()
            logger.info(f"Pupil schedule fetched successfully (year={study_year}, week={week_index})")
            return data
        except Exception as e:
            logger.error(f"Failed to get pupil schedule (year={study_year}, week={week_index}): {e}")
            raise

    async def get_lessons_and_homework(
        self,
        *,
        week_index: int = 0,
        view_type: int = 0,
        study_year: int,
        encrypted_student_id: str,
        class_code: int,
        module_id: int = 10,
    ) -> Any:
        """
        Get a week of lessons with their topic and homework (Sunday-Friday).
        Unlike get_homework(), which only covers today, this works for any week.

        POST /server/api/PupilCard/GetPupilLessonsAndHomework

        Auth:
          - Cookie: webToken=<token>

        Params:
          week_index: week offset (0 = current week, -1 = previous week)
          view_type: view type (usually 0)
          study_year: school year, named by the year it ends (2025-2026 -> 2026)
          encrypted_student_id: the child's encrypted id (dashboard data['childrens'][i]['id'])
          class_code: ClassCode
          module_id: module identifier (usually 10)
        """
        logger.info(f"Fetching lessons and homework (year={study_year}, week={week_index}, class={class_code})")
        try:
            resp = await self.request(
                "POST",
                "/server/api/PupilCard/GetPupilLessonsAndHomework",
                json={
                    "weekIndex": week_index,
                    "viewType": view_type,
                    "studyYear": study_year,
                    "studentID": encrypted_student_id,
                    "classCode": class_code,
                    "moduleID": module_id,
                },
            )
            data = resp.json()
            logger.info(f"Lessons and homework fetched successfully (year={study_year}, week={week_index})")
            return data
        except Exception as e:
            logger.error(f"Failed to get lessons and homework (year={study_year}, week={week_index}): {e}")
            raise
