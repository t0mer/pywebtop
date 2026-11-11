from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from .crypto import encrypt_login_data
from .exceptions import WebtopLoginError, WebtopRequestError
from .models import WebtopSession

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://webtopserver.smartschool.co.il"


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
        data: Optional[str] = None,
        remember_me: bool = False,
        biometric_login: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        auto_login: bool = True,
    ):
        logger.info(f"Initializing WebtopClient for user: {username}, base_url: {base_url}")
        self._username = username
        self._password = password
        self._data = data
        self._remember_me = remember_me
        self._biometric_login = biometric_login

        self._base_url = base_url.rstrip("/")
        self._auto_login = auto_login

        try:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                headers={"Content-Type": "application/json; charset=utf-8"},
                follow_redirects=True,
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

    async def login(self) -> WebtopSession:
        """
        Perform ONLY the login call.
        """
        logger.info(f"Attempting to login as user: {self._username}")
        
        try:
            resp = await self._http.post(
                "/server/api/user/LoginByUserNameAndPassword",
                json={
                    "UserName": self._username,
                    "Password": self._password,
                    "Data": self._data if self._data is not None else encrypt_login_data(self._username),
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
            logger.error(f"Login failed with status {resp.status_code}: {resp.text}")
            raise WebtopLoginError(f"Login failed ({resp.status_code}): {resp.text}")

        try:
            body = resp.json()
        except Exception as e:
            logger.error(f"Failed to parse login response as JSON: {e}")
            raise WebtopLoginError(f"Login response is not JSON: {e}") from e

        if body.get("status") is not True:
            error_desc = body.get('errorDescription')
            error_id = body.get('errorId')
            logger.error(f"Login status is false. errorDescription={error_desc}, errorId={error_id}")
            raise WebtopLoginError(
                f"Login returned status=false. "
                f"errorDescription={error_desc!r}, errorId={error_id!r}"
            )

        data = body.get("data") or {}
        token = data.get("token")
        if not token:
            logger.error("Login response missing token in data")
            raise WebtopLoginError("Login succeeded but data.token is missing")

        # ✅ Webtop requires token as cookie: webToken=<token>
        self._http.cookies.set("webToken", token)
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
        logger.info(f"Login successful for user: {self._session.first_name} {self._session.last_name} (school: {self._session.school_name})")
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
        logger.info(f"Switching to student_id: {student_id[:10]}...")
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
            
            if resp.status_code >= 400:
                logger.error(f"Switch student failed: {resp.status_code} {resp.text}")
                raise WebtopLoginError(f"Switch student failed: {resp.text}")

            data = resp.json()
            if data.get("status") is not True:
                 logger.error(f"Switch student returned status=false: {data}")
                 raise WebtopLoginError(f"Switch student failed: {data}")
                 
            new_data = data.get("data")
            if not new_data:
                raise WebtopLoginError("Switch student succeeded but returned no data")

            # Update session
            token = new_data.get("token")
            # Update cookie if token changed
            if token:
                self._http.cookies.set("webToken", token)
            
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
            logger.info(f"Switched successfully to: {self._session.first_name} {self._session.last_name}")
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
            logger.error(f"{method} {path} failed with status {resp.status_code}: {resp.text}")
            raise WebtopRequestError(f"{method} {path} failed ({resp.status_code}): {resp.text}")

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
                logger.error(f"Failed to get linked students: {data}")
                raise WebtopRequestError(f"Failed to get linked students: {data}")
            
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
        logger.info(f"Fetching messages inbox (page={page_id}, label={label_id}, has_read={has_read}, query='{search_query}')")
        try:
            resp = await self.request(
                "POST",
                "/server/api/messageBox/GetMessagesInbox",
                json={
                    "PageId": page_id,
                    "LabelId": label_id,
                    "HasRead": has_read,
                    "SearchQuery": search_query,
                },
            )
            data = resp.json()
            logger.info(f"Messages inbox fetched successfully (page={page_id})")
            return data
        except Exception as e:
            logger.error(f"Failed to get messages inbox (page={page_id}): {e}")
            raise

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
