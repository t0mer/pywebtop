"""
Command-line interface for pywebtop.

Credentials are read from the environment (WEBTOP_USERNAME, WEBTOP_PASSWORD,
WEBTOP_DATA) or prompted for interactively. The password is never accepted as
a command-line argument, since argv is visible to other local users and lands
in shell history.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import getpass
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .client import WebtopClient
from .exceptions import WebtopError


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("pywebtop")
    except Exception:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webtop",
        description="Unofficial CLI for Webtop (SmartSchool). Prints JSON responses to stdout (homework prints text unless --json).",
        epilog="Credentials: set WEBTOP_USERNAME / WEBTOP_PASSWORD / WEBTOP_DATA, or you will be prompted.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    parser.add_argument("-u", "--username", help="Webtop username (default: $WEBTOP_USERNAME)")
    parser.add_argument(
        "--switch-account",
        metavar="STUDENT_ID",
        help="Switch to this linked account (studentId from 'accounts') before running the command",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging to stderr")

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("login", help="Verify credentials and print basic session info")
    p.set_defaults(handler=_cmd_login)

    p = sub.add_parser("accounts", help="List Webtop logins linked to this account (for --switch-account)")
    p.set_defaults(handler=lambda c, a: c.get_linked_students())

    p = sub.add_parser("kids", help="List your children (id, class code/number) from the dashboard")
    p.set_defaults(handler=_cmd_kids)

    p = sub.add_parser("dashboard", help="Get the dashboard (InitDashboard) payload")
    p.set_defaults(handler=lambda c, a: c.get_students())

    p = sub.add_parser("messages", help="Get the messages inbox")
    p.add_argument("--page", type=int, default=1, help="Page number (1-based)")
    p.add_argument("--label", type=int, default=0, help="Label/category id")
    p.add_argument("--unread", action="store_true", help="Only unread messages")
    p.add_argument("--search", default="", help="Free-text search")
    p.set_defaults(
        handler=lambda c, a: c.get_messages_inbox(
            page_id=a.page,
            label_id=a.label,
            has_read=False if a.unread else None,
            search_query=a.search,
        )
    )

    p = sub.add_parser("message", help="Get one inbox message (body, attachments); marks it as read")
    p.add_argument("message_id", help="messageId from the `messages` command")
    p.set_defaults(handler=lambda c, a: c.get_message(message_id=a.message_id))

    p = sub.add_parser("notifications", help="Get a preview of unread notifications")
    p.set_defaults(handler=lambda c, a: c.get_preview_unread_notifications())

    p = sub.add_parser("notification-settings", help="Get notification settings")
    p.add_argument("--student-id", required=True, help="Encrypted student id")
    p.set_defaults(handler=lambda c, a: c.get_notification_settings(encrypted_student_id=a.student_id))

    p = sub.add_parser(
        "homework",
        help="Show homework for all kids: today, yesterday, tomorrow, week, or a date (YYYY-MM-DD)",
    )
    p.add_argument(
        "when",
        nargs="?",
        default="today",
        help="today (default), yesterday, tomorrow, week, or YYYY-MM-DD",
    )
    p.add_argument("--kid", help="Only this kid (matches part of the name)")
    filters = p.add_mutually_exclusive_group()
    filters.add_argument("--hw-only", action="store_true", help="Only lessons with homework or attached files")
    filters.add_argument("--all", action="store_true", help="Every lesson, including ones with no topic or homework")
    p.add_argument("--json", action="store_true", help="Print JSON instead of text")
    p.set_defaults(handler=_cmd_homework)

    p = sub.add_parser("discipline", help="Get discipline (behavior) events")
    p.add_argument("--student-id", required=True, help="Encrypted student id")
    p.add_argument("--class-code", type=int, required=True)
    p.set_defaults(
        handler=lambda c, a: c.get_discipline_events(
            encrypted_student_id=a.student_id,
            class_code=a.class_code,
        )
    )

    p = sub.add_parser("schedule", help="Get the weekly timetable")
    p.add_argument("--student-id", required=True, help="Encrypted student id")
    p.add_argument("--class-code", type=int, required=True)
    p.add_argument("--year", type=int, required=True, help="Study year, e.g. 2026")
    p.add_argument("--week", type=int, default=0, help="Week offset (0 = current week)")
    p.set_defaults(
        handler=lambda c, a: c.get_pupil_schedule(
            encrypted_student_id=a.student_id,
            class_code=a.class_code,
            study_year=a.year,
            week_index=a.week,
        )
    )

    return parser


async def _cmd_login(client: WebtopClient, args: argparse.Namespace) -> Dict[str, Any]:
    s = client.session
    return {
        "user_id": s.user_id,
        "student_id": s.student_id,
        "school_id": s.school_id,
        "school_name": s.school_name,
        "first_name": s.first_name,
        "last_name": s.last_name,
    }


async def _get_kids(client: WebtopClient) -> List[Dict[str, Any]]:
    dashboard = await client.get_students()
    data = dashboard.get("data") if isinstance(dashboard, dict) else None
    children = data.get("childrens") if isinstance(data, dict) else None
    return [
        {
            "name": f"{child.get('firstName', '')} {child.get('lastName', '')}".strip(),
            "id": child.get("id"),
            "class_code": child.get("classCode"),
            "class_number": child.get("classNum"),
        }
        for child in children or []
    ]


async def _cmd_kids(client: WebtopClient, args: argparse.Namespace) -> List[Dict[str, Any]]:
    return await _get_kids(client)


def _parse_when(when: str, today: dt.date) -> List[dt.date]:
    """Turn the homework WHEN argument into the list of dates to show."""
    keyword = when.lower()
    if keyword == "today":
        return [today]
    if keyword == "yesterday":
        return [today - dt.timedelta(days=1)]
    if keyword == "tomorrow":
        return [today + dt.timedelta(days=1)]
    if keyword == "week":
        sunday = _week_start(today)
        return [sunday + dt.timedelta(days=i) for i in range(6)]  # Sunday-Friday
    try:
        return [dt.date.fromisoformat(when)]
    except ValueError:
        raise ValueError(f"invalid date {when!r}: use today, yesterday, tomorrow, week or YYYY-MM-DD") from None


def _school_today() -> dt.date:
    """Today in Israel, where the school is, whatever the computer's time zone."""
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+

        return dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    except Exception:  # Python 3.8, or no tz database (e.g. Windows without tzdata)
        return dt.date.today()


def _week_start(day: dt.date) -> dt.date:
    """The Sunday that starts the school week containing `day`."""
    return day - dt.timedelta(days=(day.weekday() + 1) % 7)


def _study_year(day: dt.date) -> int:
    """Israeli school years run September-June and are named by the year they end."""
    return day.year + 1 if day.month >= 9 else day.year


def _lessons_for_day(week: Any, day: dt.date) -> List[Dict[str, Any]]:
    days = week.get("data") if isinstance(week, dict) else None
    for entry in days or []:
        if str(entry.get("date", ""))[:10] != day.isoformat():
            continue
        return [
            {
                "hour": item.get("hour_no"),
                "subject": item.get("subject_name"),
                "teacher": item.get("teacher"),
                "topic": item.get("descClass"),
                "homework": item.get("homeWork"),
                "files": item.get("files") or [],
            }
            for hour in entry.get("hoursData") or []
            for item in hour.get("scheduale") or []
        ]
    return []


async def _cmd_homework(client: WebtopClient, args: argparse.Namespace) -> Any:
    today = _school_today()
    days = _parse_when(args.when, today)

    kids = await _get_kids(client)
    if args.kid:
        kids = [k for k in kids if args.kid in k["name"]]
        if not kids:
            raise ValueError(f"no kid matches {args.kid!r} (see 'webtop kids')")

    result = []
    for kid in kids:
        # Keyed by study year too: a week from late August into September spans two years.
        weeks: Dict[Tuple[dt.date, int], Any] = {}
        kid_days = []
        for day in days:
            key = (_week_start(day), _study_year(day))
            if key not in weeks:
                weeks[key] = await client.get_lessons_and_homework(
                    week_index=(key[0] - _week_start(today)).days // 7,
                    study_year=key[1],
                    encrypted_student_id=kid["id"],
                    class_code=kid["class_code"],
                )
            lessons = _lessons_for_day(weeks[key], day)
            # Default: lessons with a topic or homework. Topics often hold the
            # assignment too (e.g. "work in the yellow book pp. 6-7").
            if args.hw_only:
                lessons = [lesson for lesson in lessons if lesson["homework"] or lesson["files"]]
            elif not args.all:
                lessons = [lesson for lesson in lessons if lesson["topic"] or lesson["homework"] or lesson["files"]]
            kid_days.append({"date": day.isoformat(), "lessons": lessons})
        result.append(
            {"name": kid["name"], "class": f"{kid['class_code']}-{kid['class_number']}", "days": kid_days}
        )

    return result if args.json else _format_homework(result)


def _format_homework(result: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for kid in result:
        lines.append(f"{kid['name']} ({kid['class']})")
        for day in kid["days"]:
            date = dt.date.fromisoformat(day["date"])
            header = f"  {date:%a %Y-%m-%d}"
            if not day["lessons"]:
                lines.append(f"{header}: nothing")
                continue
            lines.append(f"{header}:")
            for lesson in day["lessons"]:
                text = f"    {lesson['hour']}. {lesson['subject']}"
                if lesson["topic"]:
                    text += f" - {lesson['topic']}"
                if lesson["homework"]:
                    text += f" | HW: {lesson['homework']}"
                if lesson["files"]:
                    text += f" [{len(lesson['files'])} file(s)]"
                lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip()


def _read_credentials(args: argparse.Namespace) -> Dict[str, str]:
    username = args.username or os.environ.get("WEBTOP_USERNAME") or input("Webtop username: ")
    password = os.environ.get("WEBTOP_PASSWORD") or getpass.getpass("Webtop password: ")
    creds = {"username": username, "password": password}
    data = os.environ.get("WEBTOP_DATA")
    if data:
        creds["data"] = data
    return creds


async def _run(args: argparse.Namespace) -> Any:
    async with WebtopClient(**_read_credentials(args)) as client:
        await client.login()
        if args.switch_account:
            await client.switch_student(args.switch_account)
        return await args.handler(client, args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    # Without -v, errors are reported once via the "error:" line below,
    # so the library's own ERROR log lines would just duplicate them.
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.CRITICAL,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        result = asyncio.run(_run(args))
    except (WebtopError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130

    if isinstance(result, str):
        print(result)
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
