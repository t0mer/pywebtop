from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class WebtopSession:
    """
    Auth session returned from login.

    token:
      - value from login response data.token
      - used as cookie: webToken=<token>
    """
    token: str = field(repr=False)
    user_id: Optional[str] = None
    student_id: Optional[int] = None
    school_id: Optional[int] = None
    school_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    raw_login_data: Optional[Dict[str, Any]] = field(default=None, repr=False)
