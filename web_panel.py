from __future__ import annotations

import asyncio
import ast
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import validators
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware

from Bot import sheets as bot_sheets
from Bot.utils import calcage, calcdateofbirth, formatedtotts, formatts, plural_word
from config import ADMIN, FRACTIONS, LEADERS_TIME_LEFT, ROLES, STRUCTURES, SUPPORT_ROLES, TOKEN
from db import (
    Forms,
    InactiveRequests,
    Inactives,
    Objectives,
    PunishmentEntries,
    PunishmentsRequests,
    Removed,
    Reports,
    Settings_a,
    Settings_l,
    Settings_s,
    Sheets,
    SpecialAccesses,
    Users,
    WebCredentials,
    dbhandle,
    init_db,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "storage" / "uploads"
SESSION_DAYS = 30
SESSION_MAX_AGE = SESSION_DAYS * 24 * 60 * 60
SECRET_KEY = os.getenv("FASTAPI_SECRET_KEY") or TOKEN or "fastapi-dev-secret"
USER_LIST_PAGE_SIZE = 25
ADMIN_LIST_PAGE_SIZE = 100

TOP_MANAGER_ROLES = (
    "Главный администратор",
    "Основной ЗГА",
    "Заместитель ГА",
)
ADMIN_MANAGER_ROLES = TOP_MANAGER_ROLES + (
    "Куратор администрации",
    "Заместитель КА",
    "Заместитель куратора администрации",
)
SUPPORT_MANAGER_ROLES = TOP_MANAGER_ROLES + (
    "Главный АП",
    "Главный за АП",
    "Куратор агентов поддержки",
    "Заместитель КАП",
)
LEADER_MANAGER_ROLES = TOP_MANAGER_ROLES + (
    "Главный за лидерами",
    "Куратор организации",
    "Заместитель КО",
)
GENERAL_SEARCH_ROLES = TOP_MANAGER_ROLES + (
    "Куратор администрации",
    "Заместитель КА",
    "Заместитель куратора администрации",
)
SCOPE_TITLES = {
    "leaders": "Лидеры",
    "support": "Агенты поддержки",
    "admins": "Администраторы",
}
SCOPE_METRIC_LABELS = {
    "leaders": "Баллы",
    "support": "Аски",
    "admins": "Ответы",
}
SCOPE_METRIC_TOTAL_LABELS = {
    "leaders": "Количество баллов",
    "support": "Количество асков",
    "admins": "Количество ответов",
}
SCOPE_METRIC_ACTION_LABELS = {
    "leaders": "баллы",
    "support": "аски",
    "admins": "ответы",
}
SCOPE_METRIC_LOSS_LABELS = {
    "leaders": "Потеря баллов",
    "support": "Потеря асков",
    "admins": "Потеря ответов",
}
PUNISHMENT_LABELS = {
    "rebuke": "Выговор",
    "warn": "Предупреждение",
    "verbal": "Устное предупреждение",
}
METRIC_LABELS = {
    "leaders": ("балл", "балла", "баллов"),
    "support": ("аск", "аска", "асков"),
    "admins": ("ответ", "ответа", "ответов"),
}
REMOVED_STRUCT = {
    "leaders": "l",
    "support": "s",
    "admins": "a",
}

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def now_ts() -> int:
    return int(time.time())


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def parse_iso_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def parse_ru_date(value: str) -> datetime:
    return datetime.strptime(value, "%d.%m.%Y")


def inclusive_end_timestamp(date_value: datetime) -> int:
    return int((date_value + timedelta(days=1)).timestamp()) - 1


def format_datetime(timestamp: int | None) -> str:
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y / %H:%M")


def format_appointment(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y / %H:%M")


def datetime_to_input(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def datetime_local_to_input(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%dT%H:%M")


def parse_datetime_local(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%dT%H:%M")
    except ValueError:
        return parse_iso_date(cleaned)


templates.env.filters["datetime_display"] = format_datetime
templates.env.filters["datetime_to_input"] = datetime_to_input
templates.env.filters["datetime_local_to_input"] = datetime_local_to_input


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + salt.hex() + "$" + derived.hex()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        _, n, r, p, salt_hex, digest_hex = hashed.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=int(n),
        r=int(r),
        p=int(p),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def generate_token() -> str:
    return secrets.token_urlsafe(24)


def set_flash(request: Request, text: str, level: str = "info") -> None:
    request.session["flash"] = {"text": text, "level": level}


def pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop("flash", None)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = generate_token()
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, token: str | None) -> bool:
    return bool(token) and token == request.session.get("csrf_token")


def set_generated_link(request: Request, nickname: str, link: str) -> None:
    request.session["generated_link"] = {"nickname": nickname, "link": link}


def pop_generated_link(request: Request) -> dict[str, str] | None:
    return request.session.pop("generated_link", None)


def build_invite_url(request: Request, token: str) -> str:
    return str(request.url_for("setup_password", token=token))


def db_setting(model, key: str, default: int | str) -> int | str:
    item = model.get_or_none(model.setting == key)
    if item is None:
        if isinstance(default, int):
            item = model.create(setting=key, val=default)
        else:
            item = model.create(setting=key, val=default)
    return item.val


def set_setting_value(model, key: str, value: int | str) -> None:
    item = model.get_or_none(model.setting == key)
    if item is None:
        model.create(setting=key, val=value)
        return
    item.val = value
    item.save()


def sync_sheets(composition: bool = False, removed: bool = False, inactives: bool = False) -> None:
    with suppress(Exception):
        bot_sheets.main(composition=composition, removed=removed, inactives=inactives)


def normalize_page(value: int | None) -> int:
    return max(int(value or 1), 1)


def paginate_list[T](items: list[T], page: int, per_page: int) -> tuple[list[T], bool]:
    page = normalize_page(page)
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], end < len(items)


def paginate_query(query, page: int, per_page: int):
    page = normalize_page(page)
    start = (page - 1) * per_page
    rows = list(query.offset(start).limit(per_page + 1))
    return rows[:per_page], len(rows) > per_page


def query_with(request: Request, **updates: Any) -> str:
    params: dict[str, str] = dict(request.query_params)
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    query = urlencode(params)
    return f"{request.url.path}?{query}" if query else request.url.path


def has_special_access(user: Users, access_role: str) -> bool:
    return (
        SpecialAccesses.get_or_none(
            SpecialAccesses.telegram_id == str(user.telegram_id),
            SpecialAccesses.role == access_role,
        )
        is not None
    )


def user_scope(user: Users) -> str:
    if user.fraction:
        return "leaders"
    if user.role in SUPPORT_ROLES:
        return "support"
    return "admins"


def user_display_role(user: Users) -> str:
    return "Лидер" if user.fraction else (user.role or "Пользователь")


def user_by_telegram_value(value: Any) -> Users | None:
    try:
        telegram_id = int(value)
    except (TypeError, ValueError):
        return None
    return Users.get_or_none(Users.telegram_id == telegram_id)


def build_user_lookups() -> tuple[dict[str, Users], dict[Any, Users]]:
    nickname_lookup: dict[str, Users] = {}
    telegram_lookup: dict[Any, Users] = {}
    for user in Users.select():
        nickname_lookup[user.nickname] = user
        telegram_lookup[user.telegram_id] = user
        telegram_lookup[str(user.telegram_id)] = user
    return nickname_lookup, telegram_lookup


def lookup_user(user_lookup: dict[Any, Users] | None, value: Any) -> Users | None:
    if value is None:
        return None
    if user_lookup is None:
        return user_by_telegram_value(value)
    return user_lookup.get(value) or user_lookup.get(str(value))


def role_tone_class(role: str | None) -> str:
    if not role:
        return ""
    if role in {"Младший модератор", "Модератор", "Старший модератор"}:
        return "tone-green"
    if role in {"Администратор", "Старший администратор"}:
        return "tone-blue"
    if role in {
        "Заместитель КА",
        "Заместитель куратора администрации",
        "Заместитель КАП",
        "Заместитель КО",
        "Заместитель КР",
        "Куратор администрации",
        "Куратор агентов поддержки",
        "Куратор организации",
    }:
        return "tone-pink"
    if role in {
        "Главный администратор",
        "Заместитель ГА",
        "Основной ЗГА",
        "Основной заместитель",
        "ГА",
        "Га",
    }:
        return "tone-red"
    return ""


def structure_tone_class(structure: str | None) -> str:
    if structure in {"Администрация", "Администраторы"}:
        return "tone-red"
    if structure == "Лидеры":
        return "tone-blue"
    if structure == "Агенты поддержки":
        return "tone-pink"
    return ""


def can_manage_scope(user: Users, scope: str) -> bool:
    if scope == "leaders":
        return user.role in LEADER_MANAGER_ROLES
    if scope == "support":
        return user.role in SUPPORT_MANAGER_ROLES or has_special_access(user, "swatcher")
    if scope == "admins":
        return user.role in ADMIN_MANAGER_ROLES
    return False


def can_access_admin_reviews(user: Users) -> bool:
    return user.role in ADMIN_MANAGER_ROLES


def can_access_server(user: Users) -> bool:
    return user.role in TOP_MANAGER_ROLES


def accessible_search_scopes(user: Users) -> list[str]:
    if user.role in GENERAL_SEARCH_ROLES:
        return ["admins", "leaders", "support"]
    scopes: list[str] = []
    if user.role in {"Куратор организации", "Заместитель КО"}:
        scopes.append("leaders")
    if user.role in {"Куратор агентов поддержки", "Заместитель КАП"}:
        scopes.append("support")
    return scopes


def can_use_global_search(user: Users) -> bool:
    return bool(accessible_search_scopes(user))


def profile_url(user: Users) -> str:
    return f"/p/{quote(user.nickname, safe='')}"


def can_manage_user_profile(actor: Users, target: Users) -> bool:
    return can_manage_scope(actor, user_scope(target))


def profile_role_options(actor: Users, target: Users) -> list[str]:
    if actor.role in TOP_MANAGER_ROLES:
        return ["__leader__", *SUPPORT_ROLES, *ROLES]
    scope = user_scope(target)
    if scope == "leaders":
        return ["__leader__"]
    if scope == "support":
        return list(SUPPORT_ROLES)
    if scope == "admins":
        return list(ROLES)
    return []


def count_actionable_punishment_requests_for_admins(admin_lookup: dict[str, Users]) -> int:
    pending_keys: set[tuple[int, str]] = set()
    for record in (
        PunishmentsRequests.select()
        .where(PunishmentsRequests.status == "pending")
        .order_by(PunishmentsRequests.id.desc())
    ):
        owner = admin_lookup.get(str(record.telegram_id))
        if owner is None:
            continue
        if int(getattr(owner, record.punishment, 0) or 0) <= 0:
            continue
        pending_keys.add((owner.id, record.punishment))
    return len(pending_keys)


def count_actionable_punishment_requests_for_user(user: Users) -> int:
    active_types = {
        punishment_type
        for punishment_type in PUNISHMENT_LABELS
        if int(getattr(user, punishment_type, 0) or 0) > 0
    }
    if not active_types:
        return 0
    pending_types = {
        record.punishment
        for record in (
            PunishmentsRequests.select()
            .where(
                PunishmentsRequests.telegram_id == str(user.telegram_id),
                PunishmentsRequests.status == "pending",
                PunishmentsRequests.punishment << list(active_types),
            )
        )
    }
    return len(pending_types)


def pending_menu_badges(user: Users) -> dict[str, int]:
    badges: dict[str, int] = {}
    user_tgid = str(user.telegram_id)

    own_inactives = (
        InactiveRequests.select()
        .where(
            InactiveRequests.tgid == user_tgid,
            InactiveRequests.status == "pending",
        )
        .count()
    )
    if own_inactives:
        badges["inactives"] = own_inactives

    if user.role in ROLES:
        own_reports = Reports.select().where(Reports.user == user, Reports.status == "pending").count()
        own_forms = (
            Forms.select()
            .where(
                Forms.fromtgid == user.telegram_id,
                Forms.status == "pending",
            )
            .count()
        )
        own_punishments = count_actionable_punishment_requests_for_user(user)
        if own_reports:
            badges["reports"] = own_reports
        if own_forms:
            badges["forms"] = own_forms
        if own_punishments:
            badges["punishments"] = own_punishments

    if can_access_admin_reviews(user):
        admin_users = list(Users.select().where(Users.role << ROLES))
        admin_tgids = [admin.telegram_id for admin in admin_users]
        admin_tgid_strings = [str(admin.telegram_id) for admin in admin_users]
        admin_ids = [admin.id for admin in admin_users]
        admin_lookup = {str(admin.telegram_id): admin for admin in admin_users}
        if admin_tgid_strings:
            admin_inactives = (
                InactiveRequests.select()
                .where(
                    InactiveRequests.tgid << admin_tgid_strings,
                    InactiveRequests.status == "pending",
                )
                .count()
            )
            if admin_inactives:
                badges["administration_inactives"] = admin_inactives
        if admin_tgids:
            admin_forms = (
                Forms.select()
                .where(
                    Forms.fromtgid << admin_tgids,
                    Forms.status == "pending",
                )
                .count()
            )
            if admin_forms:
                badges["administration_forms"] = admin_forms
        if admin_ids:
            admin_reports = (
                Reports.select()
                .where(
                    Reports.user_id << admin_ids,
                    Reports.status == "pending",
                )
                .count()
            )
            if admin_reports:
                badges["administration_reports"] = admin_reports
        admin_punishments = count_actionable_punishment_requests_for_admins(admin_lookup)
        if admin_punishments:
            badges["administration_punishments"] = admin_punishments

    return badges


def menu_for_user(user: Users, active_page: str) -> list[dict[str, Any]]:
    items = [
        {"title": "Главная", "href": "/dashboard", "key": "dashboard", "section": "main"},
        {"title": "Неактивы", "href": "/inactives", "key": "inactives", "section": "main"},
    ]
    if user.role in ROLES:
        items.extend(
            [
                {"title": "Отчёты", "href": "/reports", "key": "reports", "section": "main"},
                {"title": "Формы", "href": "/forms", "key": "forms", "section": "main"},
                {"title": "Наказания", "href": "/punishments", "key": "punishments", "section": "main"},
            ]
        )
    if can_access_admin_reviews(user):
        items.extend(
            [
                {
                    "title": "Список администрации",
                    "href": "/administration/users",
                    "key": "administration_users",
                    "section": "administration",
                },
                {
                    "title": "Неактивы",
                    "href": "/administration/inactives",
                    "key": "administration_inactives",
                    "section": "administration",
                },
                {
                    "title": "Формы",
                    "href": "/administration/forms",
                    "key": "administration_forms",
                    "section": "administration",
                },
                {
                    "title": "Отчёты",
                    "href": "/administration/reports",
                    "key": "administration_reports",
                    "section": "administration",
                },
                {
                    "title": "Наказания",
                    "href": "/administration/punishments",
                    "key": "administration_punishments",
                    "section": "administration",
                },
            ]
        )
    for scope in ("leaders", "support", "admins"):
        if can_manage_scope(user, scope):
            items.append(
                {
                    "title": f"Управление {SCOPE_TITLES[scope].lower()}",
                    "href": f"/management/{scope}",
                    "key": f"management_{scope}",
                    "section": "management",
                }
            )
    if can_access_server(user):
        items.append(
            {
                "title": "Управление сервером",
                "href": "/server",
                "key": "server",
                "section": "management",
            }
        )
    badges = pending_menu_badges(user)
    for item in items:
        item["active"] = "true" if item["key"] == active_page else "false"
        item["badge"] = badges.get(item["key"], 0)
    return items


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status_code)


def require_auth(request: Request) -> Users | None:
    cached = getattr(request.state, "user", None)
    if cached is not None:
        return cached
    user_id = request.session.get("user_id") if "session" in request.scope else None
    user = Users.get_or_none(Users.id == user_id) if user_id else None
    request.state.user = user
    return user


def parse_report_attachments(value: str | None) -> list[dict[str, Any]]:
    return [normalize_attachment_item(item) for item in json_loads(value)]


def attachment_is_image(item: dict[str, Any]) -> bool:
    content_type = str(item.get("content_type") or "")
    if content_type.startswith("image/"):
        return True
    candidate = str(item.get("name") or item.get("path") or item.get("url") or "")
    candidate = candidate.split("?", 1)[0].split("#", 1)[0]
    return Path(candidate).suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".avif",
    }


def normalize_attachment_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["is_image"] = attachment_is_image(normalized)
    return normalized


def parse_form_proofs(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    parsed = json_loads(value)
    if parsed:
        return [normalize_attachment_item(item) for item in parsed]
    try:
        legacy = ast.literal_eval(value)
    except Exception:
        legacy = None
    if not isinstance(legacy, list):
        return []
    proofs: list[dict[str, Any]] = []
    for index, item in enumerate(legacy, start=1):
        match = re.search(r'href="([^"]+)"', item)
        proofs.append(
            normalize_attachment_item(
                {
                "type": "link",
                "name": f"Доказательство {index}",
                "url": match.group(1) if match else str(item),
                "legacy": True,
                }
            )
        )
    return proofs


def serialize_attachments(items: list[dict[str, Any]]) -> str | None:
    return json_dumps(items) if items else None


def save_uploads(files: list[UploadFile]) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    for upload in files:
        if not upload.filename:
            continue
        extension = Path(upload.filename).suffix
        filename = f"{secrets.token_hex(16)}{extension}"
        destination = UPLOADS_DIR / filename
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        stored.append(
            {
                "type": "file",
                "name": upload.filename,
                "path": filename,
                "content_type": upload.content_type or mimetypes.guess_type(upload.filename)[0] or "",
            }
        )
    return stored


def normalize_links(raw_links: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for chunk in re.split(r"[, \n]+", raw_links.strip()):
        if not chunk:
            continue
        url = chunk if chunk.startswith("http") else f"https://{chunk}"
        if validators.url(url):
            links.append({"type": "link", "name": chunk, "url": url})
    return links


def metric_field_for_scope(scope: str) -> str:
    return "apa"


def scope_queryset(scope: str):
    if scope == "leaders":
        return Users.select().where(Users.fraction.is_null(False))
    if scope == "support":
        return Users.select().where(Users.role << SUPPORT_ROLES)
    return Users.select().where(Users.role << ROLES)


def scope_sort_key(scope: str, user: Users) -> tuple[Any, ...]:
    if scope == "leaders":
        return (FRACTIONS.index(user.fraction), user.nickname)
    if scope == "support":
        return (SUPPORT_ROLES.index(user.role), user.appointed, user.nickname)
    promoted = user.promoted if user.promoted else user.appointed
    return (ROLES.index(user.role), promoted, user.nickname)


def penalty_amount_for_user(user: Users, start_dt: datetime, end_dt: datetime) -> int:
    days = max((end_dt.date() - start_dt.date()).days + 1, 1)
    scope = user_scope(user)
    if scope == "leaders":
        amount = int(db_setting(Settings_l, "inactiveamnt_points", 5))
    elif scope == "support":
        amount = int(db_setting(Settings_s, "inactiveamnt_asks", 10))
    else:
        amount = int(db_setting(Settings_a, "inactiveamnt_answers", 100))
    return amount * days


def apply_penalty(user: Users, amount: int) -> None:
    user.apa = max(user.apa - amount, 0)
    user.save()


def inactive_total_days(user: Users) -> int:
    total = 0
    rows = Inactives.select().where(
        Inactives.nickname == user.nickname,
        Inactives.status == "Одобрен",
    )
    for row in rows:
        try:
            start = parse_ru_date(row.start)
            end = parse_ru_date(row.end)
        except Exception:
            continue
        total += (end.date() - start.date()).days + 1
    return total


def current_inactive_info(user: Users) -> dict[str, Any] | None:
    if not user.inactiveend or user.inactiveend < time.time():
        return None
    record = (
        Inactives.select()
        .where(
            Inactives.nickname == user.nickname,
            Inactives.start == formatts(user.inactivestart),
            Inactives.end == formatts(user.inactiveend),
            Inactives.status == "Одобрен",
        )
        .order_by(Inactives.id.desc())
        .first()
    )
    manager = None
    if record and getattr(record, "processed_by", None):
        manager_user = Users.get_or_none(Users.telegram_id == record.processed_by)
        manager = manager_user.nickname if manager_user else str(record.processed_by)
    return {
        "start": formatts(user.inactivestart),
        "end": formatts(user.inactiveend),
        "reason": record.reason if record else "",
        "approved_by": manager or "Не указано",
    }


def pending_inactive_requests(user: Users) -> list[InactiveRequests]:
    return list(
        InactiveRequests.select()
        .where(
            InactiveRequests.tgid == str(user.telegram_id),
            InactiveRequests.status == "pending",
        )
        .order_by(InactiveRequests.id.desc())
    )


def inactive_request_block_reason(
    current: dict[str, Any] | None,
    pending: list[InactiveRequests],
) -> str | None:
    if current:
        return "У вас уже есть действующий неактив. Новую заявку отправить нельзя."
    if pending:
        return "У вас уже есть отправленная заявка на неактив. Дождитесь её рассмотрения."
    return None


def punishment_entries(user: Users) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    real_entries = list(
        PunishmentEntries.select()
        .where(PunishmentEntries.user == user)
        .order_by(PunishmentEntries.issued_at.desc())
    )
    active_real = [entry for entry in real_entries if entry.removed_at is None]
    active_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    active_by_type = {key: 0 for key in PUNISHMENT_LABELS}
    for entry in real_entries:
        manager = Users.get_or_none(Users.telegram_id == entry.issued_by)
        removed_by = Users.get_or_none(Users.telegram_id == entry.removed_by) if entry.removed_by else None
        row = {
            "id": entry.id,
            "type_key": entry.punishment_type,
            "type": PUNISHMENT_LABELS.get(entry.punishment_type, entry.punishment_type),
            "reason": entry.reason,
            "issued_at": format_datetime(entry.issued_at),
            "issued_by": manager.nickname if manager else str(entry.issued_by),
            "removed_at": format_datetime(entry.removed_at),
            "removed_by": removed_by.nickname if removed_by else ("-" if not entry.removed_by else str(entry.removed_by)),
            "removed_reason": entry.removed_reason or "-",
            "active": entry.removed_at is None,
            "legacy": False,
        }
        history_rows.append(row)
        if entry.removed_at is None:
            active_rows.append(row)
            active_by_type[entry.punishment_type] += 1

    requested_counts = {
        "rebuke": user.rebuke,
        "warn": user.warn,
        "verbal": user.verbal,
    }
    for key, requested in requested_counts.items():
        missing = max(requested - active_by_type[key], 0)
        for index in range(missing):
            row = {
                "id": f"legacy-{key}-{index}",
                "type_key": key,
                "type": PUNISHMENT_LABELS[key],
                "reason": "-",
                "issued_at": "-",
                "issued_by": "-",
                "removed_at": "-",
                "removed_by": "-",
                "removed_reason": "-",
                "active": True,
                "legacy": True,
            }
            active_rows.append(row)
            history_rows.append(row)

    return active_rows, history_rows


def last_punishment(user: Users) -> dict[str, str] | None:
    active, history = punishment_entries(user)
    if not history:
        return None
    for row in history:
        if not row["legacy"]:
            return {
                "label": row["type"],
                "date": row["issued_at"],
                "reason": row["reason"],
                "issued_by": row["issued_by"],
            }
    if active:
        first = active[0]
        return {
            "label": first["type"],
            "date": "-",
            "reason": first["reason"],
            "issued_by": first["issued_by"],
        }
    return None


def report_scope_allowed(user: Users) -> bool:
    return user.role in ROLES


def user_card(user: Users) -> dict[str, Any]:
    scope = user_scope(user)
    display_role = user_display_role(user)
    structure = STRUCTURES.get(user.role) if user.role else None
    appointed_days = max(math.ceil((time.time() - user.appointed) / 86400), 0)
    current_inactive = current_inactive_info(user)
    last = last_punishment(user)
    age_years = calcage(user.age)
    leader_term = int(db_setting(Settings_l, "term_days", LEADERS_TIME_LEFT))
    support_transfer_days = int(db_setting(Settings_s, "transferamnt_d", 10))
    support_transfer_asks = int(db_setting(Settings_s, "transferamnt_a", 500))
    card = {
        "id": user.id,
        "nickname": user.nickname,
        "role": display_role,
        "role_tone_class": role_tone_class(user.role or display_role),
        "scope": scope,
        "structure": structure,
        "structure_tone_class": structure_tone_class(structure),
        "fraction": user.fraction,
        "appointed": format_appointment(user.appointed),
        "appointed_days": appointed_days,
        "name": user.name,
        "age": age_years,
        "age_text": f"{age_years} лет",
        "birth_date": calcdateofbirth(user.age),
        "city": user.city,
        "discord_id": user.discord_id or "",
        "telegram_id": user.telegram_id or "",
        "forum": user.forum,
        "vk": user.vk,
        "rebuke": user.rebuke,
        "warn": user.warn,
        "verbal": user.verbal,
        "apa": user.apa,
        "coins": user.coins,
        "metric_label": SCOPE_METRIC_LABELS[scope],
        "metric_total_label": SCOPE_METRIC_TOTAL_LABELS[scope],
        "apa_word": plural_word(user.apa, METRIC_LABELS[scope]),
        "apa_text": f"{user.apa} {plural_word(user.apa, METRIC_LABELS[scope])}",
        "objective_completed": user.objective_completed or 0,
        "promoted": format_datetime(user.promoted),
        "inactive_total_days": inactive_total_days(user),
        "current_inactive": current_inactive,
        "last_punishment": last,
        "days_left_label": "",
        "days_left_value": "",
        "support_transfer_asks": support_transfer_asks,
        "appointed_days_text": f"{appointed_days} {plural_word(appointed_days, ('день', 'дня', 'дней'))}",
        "inactive_total_days_text": "",
        "coins_text": f"{user.coins} {plural_word(user.coins, ('монетка', 'монетки', 'монеток'))}",
    }
    inactive_days = card["inactive_total_days"]
    card["inactive_total_days_text"] = (
        f"{inactive_days} {plural_word(inactive_days, ('день', 'дня', 'дней'))}"
    )
    if scope == "leaders":
        days_left = max(leader_term - appointed_days, 0)
        card["days_left_label"] = "Дней до окончания срока"
        card["days_left_value"] = f"{days_left} {plural_word(days_left, ('день', 'дня', 'дней'))}"
    elif scope == "support":
        days_left = max(support_transfer_days - appointed_days, 0)
        card["days_left_label"] = "Дней до перевода"
        card["days_left_value"] = f"{days_left} {plural_word(days_left, ('день', 'дня', 'дней'))}"
    else:
        card["days_left_label"] = "Дней выполненного норматива"
        completed = user.objective_completed or 0
        card["days_left_value"] = f"{completed} {plural_word(completed, ('день', 'дня', 'дней'))}"
    return card


def visible_report(record: Reports, viewer: Users) -> bool:
    return record.user_id == viewer.id or can_manage_scope(viewer, user_scope(record.user))


def visible_form(record: Forms, viewer: Users) -> bool:
    owner = user_by_telegram_value(record.fromtgid)
    if owner is None:
        return can_manage_scope(viewer, "admins")
    return owner.id == viewer.id or can_manage_scope(viewer, user_scope(owner))


def build_report_row(
    record: Reports,
    user_lookup: dict[Any, Users] | None = None,
    owner: Users | None = None,
) -> dict[str, Any]:
    attachments = parse_report_attachments(record.attachments)
    reviewer = lookup_user(user_lookup, record.checked_by) if record.checked_by else None
    row_owner = owner or Users.get_or_none(Users.id == record.user_id)
    if row_owner is None and user_lookup is not None:
        row_owner = lookup_user(user_lookup, record.user_id)
    return {
        "id": record.id,
        "user": row_owner,
        "user_name": row_owner.nickname if row_owner is not None else f"ID {record.user_id}",
        "type": "Норматив" if record.report_type == "objective" else "Доп. ответы",
        "type_key": record.report_type,
        "report_date": record.report_date,
        "status": record.status,
        "result": record.result or "-",
        "checked_by": reviewer.nickname if reviewer else "-",
        "credited_amount": record.credited_amount,
        "counts_for_objective": bool(record.counts_for_objective),
        "created_at": format_datetime(record.created_at),
        "processed_at": format_datetime(record.processed_at),
        "attachments": attachments,
    }


def build_form_row(record: Forms, user_lookup: dict[Any, Users] | None = None) -> dict[str, Any]:
    owner = lookup_user(user_lookup, record.fromtgid)
    reviewer = lookup_user(user_lookup, record.processed_by) if getattr(record, "processed_by", None) else None
    return {
        "id": record.id,
        "user": owner,
        "form": record.form,
        "status": getattr(record, "status", "legacy") or "legacy",
        "result": getattr(record, "result", None) or "-",
        "processed_at": format_datetime(getattr(record, "processed_at", None)),
        "created_at": format_datetime(getattr(record, "created_at", None)),
        "processed_by": reviewer.nickname if reviewer else "-",
        "proofs": parse_form_proofs(record.proofs),
    }


def build_inactive_row(record: Inactives, user_lookup: dict[Any, Users] | None = None) -> dict[str, Any]:
    reviewer = lookup_user(user_lookup, getattr(record, "processed_by", None)) if getattr(record, "processed_by", None) else None
    return {
        "id": record.id,
        "nickname": record.nickname,
        "start": record.start,
        "end": record.end,
        "status": record.status,
        "reason": record.reason or "-",
        "processed_by": reviewer.nickname if reviewer else "-",
        "processed_at": format_datetime(getattr(record, "processed_at", None)),
        "process_comment": getattr(record, "process_comment", None) or None,
        "penalty_amount": getattr(record, "penalty_amount", None),
    }


def build_punishment_request_row(
    record: PunishmentsRequests,
    user_lookup: dict[Any, Users] | None = None,
) -> dict[str, Any]:
    owner = lookup_user(user_lookup, record.telegram_id)
    reviewer = lookup_user(user_lookup, getattr(record, "processed_by", None)) if getattr(record, "processed_by", None) else None
    reason = getattr(record, "reason", None)
    answers_penalty = getattr(record, "answers_penalty", None)
    if answers_penalty is None and reason:
        legacy_match = re.fullmatch(r"\s*Снято ответов:\s*(\d+)\s*", reason)
        if legacy_match:
            answers_penalty = int(legacy_match.group(1))
            reason = None
    return {
        "id": record.id,
        "user": owner,
        "punishment_type": PUNISHMENT_LABELS.get(record.punishment, record.punishment),
        "status": getattr(record, "status", "pending") or "pending",
        "reason": reason or "-",
        "answers_penalty": answers_penalty or 0,
        "processed_at": format_datetime(getattr(record, "processed_at", None)),
        "created_at": format_datetime(getattr(record, "created_at", None)),
        "processed_by": reviewer.nickname if reviewer else "-",
    }


def render(
    request: Request,
    template_name: str,
    page_title: str,
    active_page: str,
    **context: Any,
) -> HTMLResponse:
    user = require_auth(request)
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "page_title": page_title,
            "current_user": user,
            "menu_items": menu_for_user(user, active_page) if user else [],
            "active_page": active_page,
            "flash": pop_flash(request),
            "generated_link": pop_generated_link(request),
            "csrf_token": ensure_csrf_token(request),
            "query_with": lambda **updates: query_with(request, **updates),
            "global_search_scopes": accessible_search_scopes(user) if user else [],
            "global_search_query": request.query_params.get("q", "") if active_page == "search" else "",
            "status_label": {
                "pending": "На проверке",
                "approved": "Одобрено",
                "rejected": "Отказано",
                "legacy": "Legacy",
                "Одобрен": "Одобрен",
                "Отказан": "Отказан",
            },
            "scope_titles": SCOPE_TITLES,
            "scope_metric_labels": SCOPE_METRIC_LABELS,
            "scope_metric_total_labels": SCOPE_METRIC_TOTAL_LABELS,
            "scope_metric_action_labels": SCOPE_METRIC_ACTION_LABELS,
            "scope_metric_loss_labels": SCOPE_METRIC_LOSS_LABELS,
            "role_tone_class": role_tone_class,
            "structure_tone_class": structure_tone_class,
            "punishment_labels": PUNISHMENT_LABELS,
            **context,
        },
    )


def ensure_bootstrap_invites() -> None:
    if WebCredentials.select().where(WebCredentials.password_hash.is_null(False)).exists():
        return
    bootstrap_users = list(
        Users.select().where(
            (Users.role == "Главный администратор") | (Users.telegram_id << ADMIN)
        )
    )
    if not bootstrap_users:
        return
    base_url = os.getenv("APP_BASE_URL", "").rstrip("/")
    for user in bootstrap_users:
        credentials, _ = WebCredentials.get_or_create(user=user)
        if credentials.invite_token:
            continue
        credentials.invite_token = generate_token()
        credentials.invite_created_at = now_ts()
        credentials.invite_created_by = 0
        credentials.save()
        path = f"/setup/{credentials.invite_token}"
        logger.warning(
            "Bootstrap invite for {}: {}",
            user.nickname,
            f"{base_url}{path}" if base_url else path,
        )


def assign_role(user: Users, role_value: str, fraction: str | None) -> None:
    if role_value == "__leader__":
        user.role = None
        user.fraction = fraction
    else:
        user.role = role_value
        user.fraction = None


def create_removed_entry(user: Users, actor: Users, reason: str) -> None:
    Removed.create(
        nickname=user.nickname,
        role=user.role,
        fraction=user.fraction,
        appointed=user.appointed,
        name=user.name,
        age=calcage(user.age),
        city=user.city,
        discord_id=user.discord_id,
        telegram_id=user.telegram_id,
        forum=user.forum,
        vk=user.vk,
        whoremoved=actor.nickname,
        reason=reason,
        date=formatts(time.time()),
        struct=REMOVED_STRUCT[user_scope(user)],
    )


def target_or_none(user_id: int, scope: str) -> Users | None:
    target = Users.get_or_none(Users.id == user_id)
    if target is None or user_scope(target) != scope:
        return None
    return target


def profile_target_or_none(user_id: int) -> Users | None:
    return Users.get_or_none(Users.id == user_id)


def profile_target_by_nickname(nickname: str) -> Users | None:
    lowered = nickname.strip().lower()
    if not lowered:
        return None
    for user in Users.select():
        if user.nickname.lower() == lowered:
            return user
    return None


def profile_inactive_rows(target: Users) -> list[dict[str, Any]]:
    rows = []
    for record in (
        Inactives.select()
        .where(Inactives.nickname == target.nickname)
        .order_by(Inactives.id.desc())
        .limit(100)
    ):
        rows.append(build_inactive_row(record))
    return rows


def profile_report_rows(target: Users) -> list[dict[str, Any]]:
    return [
        build_report_row(record, owner=target)
        for record in (
            Reports.select()
            .where(Reports.user == target)
            .order_by(Reports.id.desc())
            .limit(100)
        )
    ]


def active_users_summary() -> dict[str, int]:
    leaders = Users.select().where(Users.fraction.is_null(False)).count()
    support = Users.select().where(Users.role << SUPPORT_ROLES).count()
    admins = Users.select().where(Users.role << ROLES).count()
    return {"leaders": leaders, "support": support, "admins": admins}


def user_matches_search(user: Users, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    fields = (
        user.nickname,
        user.vk,
        user.forum,
        str(user.telegram_id or ""),
    )
    return any(needle in str(value or "").lower() for value in fields)


def user_result_href(viewer: Users, target: Users) -> str | None:
    if can_manage_user_profile(viewer, target):
        return profile_url(target)
    return None


def appointed_by_label(user: Users, credentials: dict[int, WebCredentials], telegram_lookup: dict[Any, Users]) -> str:
    credential = credentials.get(user.id)
    creator_id = getattr(credential, "invite_created_by", None) if credential else None
    if not creator_id:
        return "-"
    creator = lookup_user(telegram_lookup, creator_id)
    return creator.nickname if creator else str(creator_id)


def admin_user_rows(users: list[Users], selected_user_id: int | None = None) -> list[dict[str, Any]]:
    credentials = {credential.user_id: credential for credential in WebCredentials.select()}
    _, telegram_lookup = build_user_lookups()
    rows: list[dict[str, Any]] = []
    for item in users:
        rows.append(
            {
                "user": item,
                "card": user_card(item) if item.id == selected_user_id else None,
                "appointed_by": appointed_by_label(item, credentials, telegram_lookup),
            }
        )
    return rows


def owner_for_request(row: InactiveRequests) -> Users | None:
    return user_by_telegram_value(row.tgid)


def admin_redirect_path(area: str) -> str:
    return f"/administration/{area}"


def admin_inactive_request_rows(user_lookup: dict[Any, Users] | None = None) -> list[dict[str, Any]]:
    if user_lookup is None:
        _, user_lookup = build_user_lookups()
    rows: list[dict[str, Any]] = []
    for record in (
        InactiveRequests.select()
        .where(InactiveRequests.status == "pending")
        .order_by(InactiveRequests.id.desc())
    ):
        owner = lookup_user(user_lookup, record.tgid)
        if owner is None or user_scope(owner) != "admins":
            continue
        start_dt = parse_ru_date(record.start)
        end_dt = parse_ru_date(record.end)
        total_days = (end_dt.date() - start_dt.date()).days + 1
        rows.append(
            {
                "id": record.id,
                "owner": owner,
                "reason": record.reason,
                "start": record.start,
                "end": record.end,
                "total_days": total_days,
                "total_days_text": f"{total_days} {plural_word(total_days, ('день', 'дня', 'дней'))}",
                "answers": owner.apa,
                "penalty": record.w,
                "created_at": format_datetime(getattr(record, "created_at", None)),
            }
        )
    return rows


def build_admin_inactive_request_row(request_record: InactiveRequests, owner: Users) -> dict[str, Any]:
    start_dt = parse_ru_date(request_record.start)
    end_dt = parse_ru_date(request_record.end)
    total_days = (end_dt.date() - start_dt.date()).days + 1
    return {
        "id": request_record.id,
        "owner": owner,
        "reason": request_record.reason,
        "start": request_record.start,
        "end": request_record.end,
        "total_days": total_days,
        "total_days_text": f"{total_days} {plural_word(total_days, ('день', 'дня', 'дней'))}",
        "answers": owner.apa,
        "penalty": request_record.w,
        "created_at": format_datetime(getattr(request_record, "created_at", None)),
    }


def inactive_request_for_inactive_row(owner: Users | None, record: Inactives) -> InactiveRequests | None:
    request_id = getattr(record, "request_id", None)
    if request_id:
        return InactiveRequests.get_or_none(InactiveRequests.id == request_id)
    if owner is None:
        return None
    matches = list(
        InactiveRequests.select()
        .where(
            InactiveRequests.tgid == str(owner.telegram_id),
            InactiveRequests.start == record.start,
            InactiveRequests.end == record.end,
        )
        .order_by(InactiveRequests.id.desc())
        .limit(2)
    )
    return matches[0] if len(matches) == 1 else None


def inactive_row_for_admin(
    record: Inactives,
    owner: Users | None = None,
    request_record: InactiveRequests | None = None,
    user_lookup: dict[Any, Users] | None = None,
) -> dict[str, Any]:
    base = build_inactive_row(record, user_lookup=user_lookup)
    if owner is None:
        owner = Users.get_or_none(Users.nickname == record.nickname)
    if request_record is None:
        request_record = inactive_request_for_inactive_row(owner, record)
    approved_at = base["processed_at"]
    if approved_at == "-" and request_record is not None:
        approved_at = format_datetime(getattr(request_record, "processed_at", None))
    process_comment = base["process_comment"]
    if process_comment is None and request_record is not None:
        process_comment = getattr(request_record, "process_comment", None) or None
    try:
        start_dt = parse_ru_date(record.start)
        end_dt = parse_ru_date(record.end)
        total_days = (end_dt.date() - start_dt.date()).days + 1
        start_input = start_dt.strftime("%Y-%m-%d")
        end_input = end_dt.strftime("%Y-%m-%d")
    except Exception:
        total_days = 0
        start_input = ""
        end_input = ""
    base.update(
        {
            "owner": owner,
            "approved_at": approved_at,
            "answers": owner.apa if owner else None,
            "process_comment": process_comment,
            "total_days": total_days,
            "total_days_text": f"{total_days} {plural_word(total_days, ('день', 'дня', 'дней'))}" if total_days else "-",
            "start_input": start_input,
            "end_input": end_input,
        }
    )
    return base


def admin_active_inactive_rows() -> list[dict[str, Any]]:
    active_rows: list[dict[str, Any]] = []
    now = now_ts()
    for record in Inactives.select().order_by(Inactives.id.desc()):
        owner = Users.get_or_none(Users.nickname == record.nickname)
        row_scope = user_scope(owner) if owner is not None else ("leaders" if record.fraction else "admins")
        if row_scope != "admins" or record.status != "Одобрен":
            continue
        try:
            if inclusive_end_timestamp(parse_ru_date(record.end)) < now:
                continue
        except Exception:
            continue
        active_rows.append(inactive_row_for_admin(record))
    return active_rows


def admin_inactive_history_rows(page: int, per_page: int = 100) -> tuple[list[dict[str, Any]], bool]:
    records = []
    for record in Inactives.select().order_by(Inactives.id.desc()):
        owner = Users.get_or_none(Users.nickname == record.nickname)
        row_scope = user_scope(owner) if owner is not None else ("leaders" if record.fraction else "admins")
        if row_scope != "admins":
            continue
        records.append(record)
    start = max(page - 1, 0) * per_page
    rows = [inactive_row_for_admin(record) for record in records[start : start + per_page]]
    has_next = start + per_page < len(records)
    return rows, has_next


def admin_form_rows(status: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = Forms.select().order_by(Forms.id.desc())
    if status is not None:
        query = query.where(Forms.status == status)
    for record in query:
        row = build_form_row(record)
        if row["user"] is None or user_scope(row["user"]) != "admins":
            continue
        rows.append(row)
    return rows


def admin_report_rows(status: str | None = None, report_type: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = Reports.select().order_by(Reports.id.desc())
    if status is not None:
        query = query.where(Reports.status == status)
    if report_type is not None:
        query = query.where(Reports.report_type == report_type)
    for record in query:
        if user_scope(record.user) != "admins":
            continue
        rows.append(build_report_row(record))
    return rows


def punishment_entry_for_request(record: PunishmentsRequests, owner: Users | None) -> PunishmentEntries | None:
    if owner is None:
        return None
    active_entry = (
        PunishmentEntries.select()
        .where(
            PunishmentEntries.user == owner,
            PunishmentEntries.punishment_type == record.punishment,
            PunishmentEntries.removed_at.is_null(True),
        )
        .order_by(PunishmentEntries.issued_at.asc())
        .first()
    )
    if active_entry is not None:
        return active_entry
    return (
        PunishmentEntries.select()
        .where(
            PunishmentEntries.user == owner,
            PunishmentEntries.punishment_type == record.punishment,
        )
        .order_by(PunishmentEntries.issued_at.desc())
        .first()
    )


def admin_punishment_request_rows(status: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    query = PunishmentsRequests.select().order_by(PunishmentsRequests.id.desc())
    if status is not None:
        query = query.where(PunishmentsRequests.status == status)
    for record in query:
        row = build_punishment_request_row(record)
        owner = row["user"]
        if owner is None or user_scope(owner) != "admins":
            continue
        entry = punishment_entry_for_request(record, owner)
        days_since = None
        issued_at = "-"
        if entry is not None:
            issued_at = format_datetime(entry.issued_at)
            days_since_value = max(math.ceil((time.time() - entry.issued_at) / 86400), 0)
            days_since = f"{days_since_value} {plural_word(days_since_value, ('день', 'дня', 'дней'))}"
        row.update(
            {
                "role": owner.role,
                "answers": owner.apa,
                "issued_at": issued_at,
                "days_since_issue": days_since or "-",
            }
        )
        rows.append(row)
    return rows


def close_stale_admin_punishment_requests(
    telegram_lookup: dict[Any, Users] | None = None,
) -> int:
    if telegram_lookup is None:
        _, telegram_lookup = build_user_lookups()
    kept_pending_keys: set[tuple[int, str]] = set()
    closed_count = 0
    timestamp = now_ts()
    query = (
        PunishmentsRequests.select()
        .where(PunishmentsRequests.status == "pending")
        .order_by(PunishmentsRequests.id.desc())
    )
    for record in query:
        owner = lookup_user(telegram_lookup, record.telegram_id)
        if owner is None or user_scope(owner) != "admins":
            continue

        reason = None
        active_count = int(getattr(owner, record.punishment, 0) or 0)
        pending_key = (owner.id, record.punishment)
        if active_count <= 0:
            reason = "Автоматически закрыто: наказание уже снято или отсутствует."
        elif pending_key in kept_pending_keys:
            reason = "Автоматически закрыто: дубликат заявки на это наказание."
        else:
            kept_pending_keys.add(pending_key)
            continue

        record.status = "rejected"
        record.processed_at = record.processed_at or timestamp
        record.reason = record.reason or reason
        record.answers_penalty = record.answers_penalty or 0
        record.save()
        closed_count += 1
    return closed_count


def admin_inactive_history_query(nickname_lookup: dict[str, Users]):
    known_nicknames = list(nickname_lookup)
    admin_nicknames = [
        user.nickname
        for user in nickname_lookup.values()
        if user_scope(user) == "admins"
    ]
    legacy_admin_filter = (
        Inactives.nickname.not_in(known_nicknames)
        & (Inactives.fraction.is_null(True) | (Inactives.fraction == ""))
        & (
            Inactives.role.is_null(True)
            | (Inactives.role == "")
            | (Inactives.role << ROLES)
        )
    )
    return (
        Inactives.select()
        .where((Inactives.nickname << admin_nicknames) | legacy_admin_filter)
        .order_by(Inactives.id.desc())
    )


def admin_active_inactive_page_rows(
    nickname_lookup: dict[str, Users],
    telegram_lookup: dict[Any, Users],
    page: int,
    per_page: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    rows: list[dict[str, Any]] = []
    now = now_ts()
    query = admin_inactive_history_query(nickname_lookup).where(Inactives.status == "Одобрен")
    for record in query:
        try:
            if inclusive_end_timestamp(parse_ru_date(record.end)) < now:
                continue
        except Exception:
            continue
        rows.append(
            inactive_row_for_admin(
                record,
                owner=nickname_lookup.get(record.nickname),
                user_lookup=telegram_lookup,
            )
        )
    paginated_rows, has_next = paginate_list(rows, page, per_page)
    return paginated_rows, has_next, len(rows)


def admin_inactive_page_rows(
    pending_page: int,
    active_page: int,
    history_page: int,
    per_page: int = ADMIN_LIST_PAGE_SIZE,
) -> tuple[
    list[dict[str, Any]],
    bool,
    int,
    list[dict[str, Any]],
    bool,
    int,
    list[dict[str, Any]],
    bool,
]:
    nickname_lookup, telegram_lookup = build_user_lookups()
    admin_telegram_ids = [
        str(user.telegram_id)
        for user in nickname_lookup.values()
        if user_scope(user) == "admins"
    ]

    pending_query = (
        InactiveRequests.select()
        .where(
            InactiveRequests.status == "pending",
            InactiveRequests.tgid << admin_telegram_ids,
        )
        .order_by(InactiveRequests.id.desc())
    )
    pending_total = pending_query.count()
    pending_records, pending_has_next = paginate_query(pending_query, pending_page, per_page)
    pending_rows: list[dict[str, Any]] = []
    for record in pending_records:
        owner = lookup_user(telegram_lookup, record.tgid)
        if owner is not None:
            pending_rows.append(build_admin_inactive_request_row(record, owner))

    active_rows, active_has_next, active_total = admin_active_inactive_page_rows(
        nickname_lookup,
        telegram_lookup,
        active_page,
        per_page,
    )

    history_query = admin_inactive_history_query(nickname_lookup)
    history_records, history_has_next = paginate_query(history_query, history_page, per_page)
    history_rows = [
        inactive_row_for_admin(
            record,
            owner=nickname_lookup.get(record.nickname),
            user_lookup=telegram_lookup,
        )
        for record in history_records
    ]
    return (
        pending_rows,
        pending_has_next,
        pending_total,
        active_rows,
        active_has_next,
        active_total,
        history_rows,
        history_has_next,
    )


def admin_forms_page_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    _, telegram_lookup = build_user_lookups()
    pending_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    approved_total = 0
    for record in Forms.select().order_by(Forms.id.desc()):
        row = build_form_row(record, user_lookup=telegram_lookup)
        owner = row["user"]
        if owner is None or user_scope(owner) != "admins":
            continue
        if row["status"] not in {"pending", "rejected"}:
            approved_total += 1
        if row["status"] == "pending":
            pending_rows.append(row)
        else:
            history_rows.append(row)
    return pending_rows, history_rows, approved_total


def admin_reports_page_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    _, telegram_lookup = build_user_lookups()
    pending_objective_rows: list[dict[str, Any]] = []
    pending_additional_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    for record in Reports.select().order_by(Reports.id.desc()):
        owner = Users.get_or_none(Users.id == record.user_id)
        row = build_report_row(record, user_lookup=telegram_lookup, owner=owner)
        if row["status"] == "pending":
            if record.report_type == "objective":
                pending_objective_rows.append(row)
            else:
                pending_additional_rows.append(row)
        else:
            history_rows.append(row)
    return pending_objective_rows, pending_additional_rows, history_rows


def admin_punishment_page_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _, telegram_lookup = build_user_lookups()
    close_stale_admin_punishment_requests(telegram_lookup)
    pending_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    active_entries: dict[tuple[int, str], PunishmentEntries] = {}
    latest_entries: dict[tuple[int, str], PunishmentEntries] = {}
    for entry in PunishmentEntries.select().order_by(PunishmentEntries.issued_at.desc()):
        key = (entry.user_id, entry.punishment_type)
        latest_entries.setdefault(key, entry)
        if entry.removed_at is None:
            active_entries[key] = entry
    for record in PunishmentsRequests.select().order_by(PunishmentsRequests.id.desc()):
        row = build_punishment_request_row(record, user_lookup=telegram_lookup)
        owner = row["user"]
        if owner is None or user_scope(owner) != "admins":
            continue
        entry_key = (owner.id, record.punishment)
        entry = active_entries.get(entry_key) or latest_entries.get(entry_key)
        days_since = None
        issued_at = "-"
        if entry is not None:
            issued_at = format_datetime(entry.issued_at)
            days_since_value = max(math.ceil((time.time() - entry.issued_at) / 86400), 0)
            days_since = f"{days_since_value} {plural_word(days_since_value, ('день', 'дня', 'дней'))}"
        row.update(
            {
                "role": owner.role,
                "answers": owner.apa,
                "issued_at": issued_at,
                "days_since_issue": days_since or "-",
            }
        )
        if row["status"] == "pending":
            pending_rows.append(row)
        else:
            history_rows.append(row)
    return pending_rows, history_rows


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_bootstrap_invites()
    sync_sheets(composition=True, removed=True, inactives=True)
    bot_task = None
    if os.getenv("ENABLE_TELEGRAM_BOT") == "1":
        from Bot import Bot

        bot_task = asyncio.create_task(Bot().run())
    yield
    if bot_task is not None:
        bot_task.cancel()
        with suppress(Exception):
            await bot_task
    if not dbhandle.is_closed():
        dbhandle.close()


app = FastAPI(title="BlackRussia Admin Panel", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=SESSION_MAX_AGE,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    if dbhandle.is_closed():
        dbhandle.connect(reuse_if_open=True)
    request.state.user = None
    try:
        response = await call_next(request)
    finally:
        if not dbhandle.is_closed():
            dbhandle.close()
    return response


@app.get("/", name="home")
async def home(request: Request):
    user = require_auth(request)
    return redirect("/dashboard" if user else "/login")


@app.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request):
    if require_auth(request):
        return redirect("/dashboard")
    return render(request, "login.html", "Вход", "login")


@app.post("/login", name="login_action")
async def login_action(
    request: Request,
    nickname: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела, попробуйте ещё раз.", "error")
        return redirect("/login")
    user = Users.get_or_none(Users.nickname == nickname.strip())
    if user is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/login")
    credentials = WebCredentials.get_or_none(WebCredentials.user == user)
    if credentials is None or not verify_password(password, credentials.password_hash):
        set_flash(request, "Неверный пароль или пароль ещё не установлен.", "error")
        return redirect("/login")
    credentials.last_login_at = now_ts()
    credentials.save()
    request.session["user_id"] = user.id
    set_flash(request, f"С возвращением, {user.nickname}.", "success")
    return redirect("/dashboard")


@app.post("/logout", name="logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    if validate_csrf(request, csrf_token):
        request.session.clear()
    return redirect("/login")


@app.get("/setup/{token}", response_class=HTMLResponse, name="setup_password")
async def setup_password(request: Request, token: str):
    credentials = WebCredentials.get_or_none(WebCredentials.invite_token == token)
    if credentials is None:
        set_flash(request, "Ссылка недействительна или уже использована.", "error")
        return redirect("/login")
    return render(
        request,
        "setup.html",
        "Первичная настройка",
        "setup",
        token=token,
        user=credentials.user,
    )


@app.post("/setup/{token}", name="setup_password_action")
async def setup_password_action(
    request: Request,
    token: str,
    password: str = Form(...),
    password_repeat: str = Form(...),
    csrf_token: str = Form(...),
):
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела, откройте ссылку заново.", "error")
        return redirect(f"/setup/{token}")
    credentials = WebCredentials.get_or_none(WebCredentials.invite_token == token)
    if credentials is None:
        set_flash(request, "Ссылка недействительна или уже использована.", "error")
        return redirect("/login")
    if len(password) < 8:
        set_flash(request, "Пароль должен быть не короче 8 символов.", "error")
        return redirect(f"/setup/{token}")
    if password != password_repeat:
        set_flash(request, "Пароли не совпадают.", "error")
        return redirect(f"/setup/{token}")
    credentials.password_hash = password_hash(password)
    credentials.invite_used_at = now_ts()
    credentials.invite_token = None
    credentials.save()
    set_flash(request, "Пароль установлен, теперь можно войти на сайт.", "success")
    return redirect("/login")


@app.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    card = user_card(user)
    own_inactives = [
        build_inactive_row(row)
        for row in Inactives.select()
        .where(Inactives.nickname == user.nickname)
        .order_by(Inactives.id.desc())
        .limit(12)
    ]
    own_reports = []
    if report_scope_allowed(user):
        own_reports = [
            build_report_row(row)
            for row in Reports.select()
            .where(Reports.user == user)
            .order_by(Reports.id.desc())
            .limit(8)
        ]
    own_forms = []
    if report_scope_allowed(user):
        own_forms = [
            build_form_row(row)
            for row in Forms.select()
            .where(Forms.fromtgid == str(user.telegram_id))
            .order_by(Forms.id.desc())
            .limit(8)
        ]
    active_punishments, _ = punishment_entries(user)
    return render(
        request,
        "dashboard.html",
        "Главная",
        "dashboard",
        card=card,
        own_inactives=own_inactives,
        own_reports=own_reports,
        own_forms=own_forms,
        active_punishments=active_punishments,
    )


@app.get("/search", response_class=HTMLResponse, name="global_search_page")
async def global_search_page(request: Request, q: str = "", page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    scopes = accessible_search_scopes(user)
    if not scopes:
        set_flash(request, "У вас нет доступа к общему поиску.", "error")
        return redirect("/dashboard")
    query = q.strip()
    results_all: list[dict[str, Any]] = []
    if query:
        allowed = set(scopes)
        for target in Users.select():
            scope = user_scope(target)
            if scope not in allowed or not user_matches_search(target, query):
                continue
            results_all.append(
                {
                    "user": target,
                    "scope": scope,
                    "scope_title": SCOPE_TITLES[scope],
                    "role": user_display_role(target),
                    "href": user_result_href(user, target),
                }
            )
    results_all.sort(key=lambda row: (scopes.index(row["scope"]), row["user"].nickname.lower()))
    page = normalize_page(page)
    results, has_next = paginate_list(results_all, page, USER_LIST_PAGE_SIZE)
    return render(
        request,
        "search.html",
        "Поиск",
        "search",
        q=query,
        results=results,
        result_total=len(results_all),
        result_number_offset=(page - 1) * USER_LIST_PAGE_SIZE,
        page=page,
        has_next=has_next,
    )


@app.get("/p/{nickname}", response_class=HTMLResponse, name="profile_page")
async def profile_page(request: Request, nickname: str):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    target = profile_target_by_nickname(nickname)
    if target is None:
        set_flash(request, "Профиль пользователя не найден.", "error")
        return redirect("/dashboard")
    if not can_manage_user_profile(actor, target):
        set_flash(request, "У вас нет доступа к управлению этим профилем.", "error")
        return redirect("/dashboard")
    active_punishments, punishment_history = punishment_entries(target)
    return render(
        request,
        "profile.html",
        f"Профиль {target.nickname}",
        "profile",
        target=target,
        card=user_card(target),
        scope=user_scope(target),
        active_punishments=active_punishments,
        punishment_history=punishment_history[:100],
        inactive_history=profile_inactive_rows(target),
        report_history=profile_report_rows(target),
        role_options=profile_role_options(actor, target),
        fractions=FRACTIONS,
        punishment_labels=PUNISHMENT_LABELS,
        today=today_str(),
    )


@app.post("/p/{user_id}/dismiss", name="profile_dismiss_user")
async def profile_dismiss_user(
    request: Request,
    user_id: int,
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    target = profile_target_or_none(user_id)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/dashboard")
    if not can_manage_user_profile(actor, target):
        return redirect("/dashboard")
    if target.id == actor.id:
        set_flash(request, "Нельзя снять самого себя через профиль.", "error")
        return redirect(profile_url(target))
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(profile_url(target))
    create_removed_entry(target, actor, reason.strip())
    WebCredentials.delete().where(WebCredentials.user == target).execute()
    Inactives.delete().where(Inactives.nickname == target.nickname).execute()
    target.delete_instance()
    sync_sheets(composition=True, removed=True, inactives=True)
    set_flash(request, "Пользователь снят с должности.", "success")
    return redirect("/dashboard")


@app.post("/p/{user_id}/update", name="profile_update_user")
async def profile_update_user(
    request: Request,
    user_id: int,
    nickname: str = Form(...),
    role_value: str = Form(...),
    fraction: str = Form(""),
    name: str = Form(...),
    birth_date: str = Form(...),
    city: str = Form(...),
    discord_id: str = Form(""),
    telegram_id: str = Form(""),
    forum: str = Form(""),
    vk: str = Form(""),
    appointed_at: str = Form(...),
    promoted_at: str = Form(""),
    inactive_start: str = Form(""),
    inactive_end: str = Form(""),
    apa: int = Form(0),
    objective_completed: int = Form(0),
    coins: int = Form(0),
    rebuke: int = Form(0),
    warn: int = Form(0),
    verbal: int = Form(0),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    target = profile_target_or_none(user_id)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/dashboard")
    if not can_manage_user_profile(actor, target):
        return redirect("/dashboard")
    redirect_url = profile_url(target)
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(redirect_url)
    duplicate = Users.get_or_none(Users.nickname == nickname.strip(), Users.id != user_id)
    if duplicate:
        set_flash(request, "Пользователь с таким ником уже существует.", "error")
        return redirect(redirect_url)
    valid_roles = set(profile_role_options(actor, target))
    if role_value not in valid_roles:
        set_flash(request, "Выберите корректную должность.", "error")
        return redirect(redirect_url)
    if role_value == "__leader__" and fraction not in FRACTIONS:
        set_flash(request, "Для лидера нужно выбрать фракцию.", "error")
        return redirect(redirect_url)
    try:
        appointed_dt = parse_datetime_local(appointed_at)
        promoted_dt = parse_datetime_local(promoted_at)
        if appointed_dt is None:
            raise ValueError
        target.nickname = nickname.strip()
        target.name = name.strip()
        target.age = int(parse_iso_date(birth_date).timestamp())
        target.city = city.strip()
        target.discord_id = parse_optional_int(discord_id)
        target.telegram_id = parse_optional_int(telegram_id)
        target.forum = forum.strip()
        target.vk = vk.strip()
        target.appointed = int(appointed_dt.timestamp())
        target.promoted = int(promoted_dt.timestamp()) if promoted_dt else None
        target.apa = max(apa, 0)
        target.objective_completed = max(objective_completed, 0)
        target.coins = max(coins, 0)
        target.rebuke = max(rebuke, 0)
        target.warn = max(warn, 0)
        target.verbal = max(verbal, 0)
        if inactive_start or inactive_end:
            if not inactive_start or not inactive_end:
                raise ValueError
            start_dt = parse_iso_date(inactive_start)
            end_dt = parse_iso_date(inactive_end)
            if end_dt < start_dt:
                raise ValueError
            target.inactivestart = formatedtotts(start_dt.strftime("%d.%m.%Y"))
            target.inactiveend = inclusive_end_timestamp(end_dt)
        else:
            target.inactivestart = None
            target.inactiveend = None
    except ValueError:
        set_flash(request, "Проверьте даты и числовые поля.", "error")
        return redirect(redirect_url)
    assign_role(target, role_value, fraction or None)
    target.save()
    sync_sheets(composition=True, inactives=True)
    set_flash(request, "Профиль пользователя обновлён.", "success")
    return redirect(profile_url(target))


@app.post("/p/{user_id}/punishments", name="profile_add_punishment")
async def profile_add_punishment(
    request: Request,
    user_id: int,
    punishment_type: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    target = profile_target_or_none(user_id)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/dashboard")
    if not can_manage_user_profile(actor, target):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(profile_url(target))
    if punishment_type not in PUNISHMENT_LABELS:
        set_flash(request, "Неизвестный тип наказания.", "error")
        return redirect(profile_url(target))
    setattr(target, punishment_type, getattr(target, punishment_type) + 1)
    target.save()
    PunishmentEntries.create(
        user=target,
        scope=user_scope(target),
        punishment_type=punishment_type,
        reason=reason.strip(),
        issued_by=actor.telegram_id,
        issued_at=now_ts(),
    )
    sync_sheets(composition=True)
    set_flash(request, "Наказание выдано.", "success")
    return redirect(profile_url(target))


@app.post("/p/{user_id}/promote", name="profile_promote_user")
async def profile_promote_user(
    request: Request,
    user_id: int,
    role_value: str = Form(...),
    fraction: str = Form(""),
    reset_objective: str | None = Form(None),
    answers_penalty: int = Form(0),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    target = profile_target_or_none(user_id)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/dashboard")
    if not can_manage_user_profile(actor, target):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(profile_url(target))
    valid_roles = set(profile_role_options(actor, target))
    if role_value not in valid_roles or answers_penalty < 0:
        set_flash(request, "Проверьте параметры повышения.", "error")
        return redirect(profile_url(target))
    if role_value == "__leader__" and fraction not in FRACTIONS:
        set_flash(request, "Для лидера нужно выбрать фракцию.", "error")
        return redirect(profile_url(target))
    assign_role(target, role_value, fraction or None)
    target.promoted = now_ts()
    if reset_objective:
        target.objective_completed = 0
    target.apa = max(target.apa - answers_penalty, 0)
    target.save()
    sync_sheets(composition=True)
    set_flash(request, "Пользователь повышен/переведён.", "success")
    return redirect(profile_url(target))


@app.get("/inactives", response_class=HTMLResponse, name="inactives_page")
async def inactives_page(request: Request, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    page = normalize_page(history_page)
    history_records, history_has_next = paginate_query(
        Inactives.select()
        .where(Inactives.nickname == user.nickname)
        .order_by(Inactives.id.desc()),
        page,
        USER_LIST_PAGE_SIZE,
    )
    history = [build_inactive_row(row) for row in history_records]
    pending = pending_inactive_requests(user)
    current = current_inactive_info(user)
    request_block_reason = inactive_request_block_reason(current, pending)
    return render(
        request,
        "inactives.html",
        "Неактивы",
        "inactives",
        card=user_card(user),
        current=current,
        history=history,
        history_page=page,
        history_has_next=history_has_next,
        pending=pending,
        inactive_request_block_reason=request_block_reason,
        today=today_str(),
    )


@app.post("/inactives/request", name="create_inactive_request")
async def create_inactive_request(
    request: Request,
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/inactives")
    current = current_inactive_info(user)
    pending = pending_inactive_requests(user)
    if block_reason := inactive_request_block_reason(current, pending):
        set_flash(request, block_reason, "error")
        return redirect("/inactives")
    try:
        start_dt = parse_iso_date(start_date)
        end_dt = parse_iso_date(end_date)
    except ValueError:
        set_flash(request, "Проверьте даты неактива.", "error")
        return redirect("/inactives")
    if end_dt < start_dt:
        set_flash(request, "Дата окончания не может быть раньше даты начала.", "error")
        return redirect("/inactives")
    penalty = penalty_amount_for_user(user, start_dt, end_dt)
    InactiveRequests.create(
        tgid=str(user.telegram_id),
        reason=reason.strip(),
        start=start_dt.strftime("%d.%m.%Y"),
        end=end_dt.strftime("%d.%m.%Y"),
        w=penalty,
        status="pending",
        created_at=now_ts(),
    )
    set_flash(
        request,
        f"Заявка на неактив отправлена. При одобрении снимется {penalty} {plural_word(penalty, METRIC_LABELS[user_scope(user)])}.",
        "success",
    )
    return redirect("/inactives")


@app.post("/inactives/cancel", name="cancel_inactive")
async def cancel_inactive(request: Request, csrf_token: str = Form(...)):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/inactives")
    user.inactivestart = None
    user.inactiveend = None
    user.save()
    sync_sheets(composition=True, inactives=True)
    set_flash(request, "Действующий неактив снят.", "success")
    return redirect("/inactives")


@app.get("/reports", response_class=HTMLResponse, name="reports_page")
async def reports_page(request: Request, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    page = normalize_page(history_page)
    records, history_has_next = paginate_query(
        Reports.select()
        .where(Reports.user == user)
        .order_by(Reports.id.desc()),
        page,
        USER_LIST_PAGE_SIZE,
    )
    rows = [build_report_row(row) for row in records]
    return render(
        request,
        "reports.html",
        "Отчёты",
        "reports",
        rows=rows,
        history_page=page,
        history_has_next=history_has_next,
        today=today_str(),
    )


@app.post("/reports", name="create_report")
async def create_report(
    request: Request,
    report_type: str = Form(...),
    report_date: str = Form(...),
    csrf_token: str = Form(...),
    attachments: list[UploadFile] | None = None,
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/reports")
    if report_type not in {"objective", "additional"}:
        set_flash(request, "Выберите корректный тип отчёта.", "error")
        return redirect("/reports")
    try:
        parse_iso_date(report_date)
    except ValueError:
        set_flash(request, "Проверьте дату отчёта.", "error")
        return redirect("/reports")
    files = save_uploads(attachments or [])
    if not files:
        set_flash(request, "Нужно приложить хотя бы один файл или скриншот.", "error")
        return redirect("/reports")
    Reports.create(
        user=user,
        report_type=report_type,
        report_date=report_date,
        attachments=serialize_attachments(files),
        status="pending",
    )
    set_flash(request, "Отчёт отправлен на проверку.", "success")
    return redirect("/reports")


@app.get("/forms", response_class=HTMLResponse, name="forms_page")
async def forms_page(request: Request, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    page = normalize_page(history_page)
    records, history_has_next = paginate_query(
        Forms.select()
        .where(Forms.fromtgid == str(user.telegram_id))
        .order_by(Forms.id.desc()),
        page,
        USER_LIST_PAGE_SIZE,
    )
    rows = [build_form_row(row) for row in records]
    return render(
        request,
        "forms.html",
        "Формы",
        "forms",
        rows=rows,
        history_page=page,
        history_has_next=history_has_next,
    )


@app.post("/forms", name="create_form_request")
async def create_form_request(
    request: Request,
    form_text: str = Form(...),
    proof_links: str = Form(""),
    csrf_token: str = Form(...),
    proof_files: list[UploadFile] | None = None,
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/forms")
    if not form_text.strip().startswith("/"):
        set_flash(request, 'Форма должна начинаться с команды, например "/ban Nick 7 reason".', "error")
        return redirect("/forms")
    proofs = save_uploads(proof_files or [])
    proofs.extend(normalize_links(proof_links))
    if not proofs:
        set_flash(request, "Добавьте хотя бы одно доказательство: файл или ссылку.", "error")
        return redirect("/forms")
    Forms.create(
        form=form_text.strip(),
        proofs=serialize_attachments(proofs),
        fromtgid=str(user.telegram_id),
        status="pending",
        created_at=now_ts(),
    )
    set_flash(request, "Форма отправлена на проверку.", "success")
    return redirect("/forms")


@app.get("/punishments", response_class=HTMLResponse, name="punishments_page")
async def punishments_page(request: Request, requests_page: int = 1, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    active, history = punishment_entries(user)
    active_punishment_types = {row["type_key"] for row in active}
    pending_requests = list(
        PunishmentsRequests.select()
        .where(
            PunishmentsRequests.telegram_id == str(user.telegram_id),
            PunishmentsRequests.status == "pending",
        )
        .order_by(PunishmentsRequests.id.desc())
    )
    active_pending_requests = [
        row for row in pending_requests if row.punishment in active_punishment_types
    ]
    pending_request_types = {
        row.punishment
        for row in active_pending_requests
    }
    for row in active:
        row["pending_request"] = row["type_key"] in pending_request_types
    requests_page = normalize_page(requests_page)
    history_page = normalize_page(history_page)
    request_records, requests_has_next = paginate_list(
        active_pending_requests,
        requests_page,
        USER_LIST_PAGE_SIZE,
    )
    requests_rows = [build_punishment_request_row(row) for row in request_records]
    history_rows, history_has_next = paginate_list(history, history_page, USER_LIST_PAGE_SIZE)
    return render(
        request,
        "punishments.html",
        "Наказания",
        "punishments",
        active_rows=active,
        history_rows=history_rows,
        history_page=history_page,
        history_has_next=history_has_next,
        request_rows=requests_rows,
        requests_page=requests_page,
        requests_has_next=requests_has_next,
    )


@app.post("/punishments/request", name="create_punishment_request")
async def create_punishment_request(
    request: Request,
    punishment_type: str = Form(...),
    csrf_token: str = Form(...),
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not report_scope_allowed(user):
        set_flash(request, "Этот раздел доступен только администрации.", "error")
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/punishments")
    if punishment_type not in PUNISHMENT_LABELS:
        set_flash(request, "Неизвестный тип наказания.", "error")
        return redirect("/punishments")
    if getattr(user, punishment_type) <= 0:
        set_flash(request, "У вас нет такого активного наказания.", "error")
        return redirect("/punishments")
    existing_request = PunishmentsRequests.get_or_none(
        PunishmentsRequests.telegram_id == str(user.telegram_id),
        PunishmentsRequests.punishment == punishment_type,
        PunishmentsRequests.status == "pending",
    )
    if existing_request is not None:
        set_flash(
            request,
            "Заявка на снятие этого наказания уже отправлена и ещё не обработана.",
            "error",
        )
        return redirect("/punishments")
    PunishmentsRequests.create(
        telegram_id=str(user.telegram_id),
        punishment=punishment_type,
        status="pending",
        created_at=now_ts(),
    )
    set_flash(request, "Заявка на снятие наказания отправлена.", "success")
    return redirect("/punishments")


@app.get("/administration/users", response_class=HTMLResponse, name="administration_users_page")
async def administration_users_page(request: Request, user_id: int | None = None):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_manage_scope(user, "admins"):
        set_flash(request, "У вас нет доступа к списку администрации.", "error")
        return redirect("/dashboard")
    admins = sorted(list(scope_queryset("admins")), key=lambda item: scope_sort_key("admins", item))
    selected_user_id = user_id if any(item.id == user_id for item in admins) else None
    return render(
        request,
        "administration_users.html",
        "Список администрации",
        "administration_users",
        rows=admin_user_rows(admins, selected_user_id),
        selected_user_id=selected_user_id,
        role_options=ROLES,
        today=today_str(),
    )


@app.post("/administration/users/create", name="administration_create_user")
async def administration_create_user(
    request: Request,
    nickname: str = Form(...),
    role_value: str = Form(...),
    name: str = Form(...),
    birth_date: str = Form(...),
    city: str = Form(...),
    discord_id: str = Form(""),
    telegram_id: str = Form(""),
    forum: str = Form(""),
    vk: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, "admins"):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/administration/users")
    nickname = nickname.strip()
    if Users.get_or_none(Users.nickname == nickname):
        set_flash(request, "Администратор с таким ником уже существует.", "error")
        return redirect("/administration/users")
    if role_value not in ROLES:
        set_flash(request, "Выберите корректную должность администрации.", "error")
        return redirect("/administration/users")
    try:
        birth_ts = int(parse_iso_date(birth_date).timestamp())
        telegram_numeric = parse_optional_int(telegram_id)
        discord_numeric = parse_optional_int(discord_id)
    except ValueError:
        set_flash(request, "Проверьте дату рождения и числовые поля.", "error")
        return redirect("/administration/users")
    target = Users.create(
        nickname=nickname,
        role=role_value,
        fraction=None,
        appointed=now_ts(),
        promoted=None,
        objective_completed=0,
        apa=0,
        rebuke=0,
        warn=0,
        verbal=0,
        inactivestart=None,
        inactiveend=None,
        name=name.strip(),
        age=birth_ts,
        city=city.strip(),
        discord_id=discord_numeric,
        telegram_id=telegram_numeric,
        forum=forum.strip(),
        vk=vk.strip(),
        coins=0,
        coins_last_spend=0,
    )
    credentials, _ = WebCredentials.get_or_create(user=target)
    credentials.invite_token = generate_token()
    credentials.invite_created_by = actor.telegram_id
    credentials.invite_created_at = now_ts()
    credentials.invite_used_at = None
    credentials.save()
    set_generated_link(request, target.nickname, build_invite_url(request, credentials.invite_token))
    sync_sheets(composition=True)
    set_flash(request, "Администратор добавлен. Ссылка ниже одноразовая.", "success")
    return redirect(f"/administration/users?user_id={target.id}")


@app.post("/administration/users/{user_id}/update", name="administration_update_user")
async def administration_update_user(
    request: Request,
    user_id: int,
    nickname: str = Form(...),
    role_value: str = Form(...),
    name: str = Form(...),
    birth_date: str = Form(...),
    city: str = Form(...),
    discord_id: str = Form(""),
    telegram_id: str = Form(""),
    forum: str = Form(""),
    vk: str = Form(""),
    apa: int = Form(0),
    objective_completed: int = Form(0),
    rebuke: int = Form(0),
    warn: int = Form(0),
    verbal: int = Form(0),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, "admins"):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/administration/users?user_id={user_id}")
    target = target_or_none(user_id, "admins")
    if target is None:
        set_flash(request, "Администратор не найден.", "error")
        return redirect("/administration/users")
    duplicate = Users.get_or_none(Users.nickname == nickname.strip(), Users.id != user_id)
    if duplicate:
        set_flash(request, "Пользователь с таким ником уже существует.", "error")
        return redirect(f"/administration/users?user_id={user_id}")
    if role_value not in ROLES:
        set_flash(request, "Выберите корректную должность администрации.", "error")
        return redirect(f"/administration/users?user_id={user_id}")
    try:
        target.nickname = nickname.strip()
        target.role = role_value
        target.fraction = None
        target.name = name.strip()
        target.age = int(parse_iso_date(birth_date).timestamp())
        target.city = city.strip()
        target.discord_id = parse_optional_int(discord_id)
        target.telegram_id = parse_optional_int(telegram_id)
        target.forum = forum.strip()
        target.vk = vk.strip()
        target.apa = max(apa, 0)
        target.objective_completed = max(objective_completed, 0)
        target.rebuke = max(rebuke, 0)
        target.warn = max(warn, 0)
        target.verbal = max(verbal, 0)
    except ValueError:
        set_flash(request, "Проверьте дату рождения и числовые поля.", "error")
        return redirect(f"/administration/users?user_id={user_id}")
    target.save()
    sync_sheets(composition=True)
    set_flash(request, "Информация администратора обновлена.", "success")
    return redirect(f"/administration/users?user_id={target.id}")


@app.post("/administration/users/{user_id}/dismiss", name="administration_dismiss_user")
async def administration_dismiss_user(
    request: Request,
    user_id: int,
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, "admins"):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/administration/users?user_id={user_id}")
    target = target_or_none(user_id, "admins")
    if target is None:
        set_flash(request, "Администратор не найден.", "error")
        return redirect("/administration/users")
    create_removed_entry(target, actor, reason.strip())
    WebCredentials.delete().where(WebCredentials.user == target).execute()
    Inactives.delete().where(Inactives.nickname == target.nickname).execute()
    target.delete_instance()
    sync_sheets(composition=True, removed=True, inactives=True)
    set_flash(request, "Администратор снят с должности.", "success")
    return redirect("/administration/users")


@app.get("/administration/inactives", response_class=HTMLResponse, name="administration_inactives_page")
async def administration_inactives_page(
    request: Request,
    pending_page: int = 1,
    active_page: int = 1,
    history_page: int = 1,
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_admin_reviews(user):
        set_flash(request, "У вас нет доступа к этому разделу.", "error")
        return redirect("/dashboard")
    pending_page = normalize_page(pending_page)
    active_page = normalize_page(active_page)
    history_page = normalize_page(history_page)
    (
        pending_rows,
        pending_has_next,
        pending_total,
        active_rows,
        active_has_next,
        active_total,
        history_rows,
        history_has_next,
    ) = admin_inactive_page_rows(pending_page, active_page, history_page)
    return render(
        request,
        "administration_inactives.html",
        "Администрация • Неактивы",
        "administration_inactives",
        pending_rows=pending_rows,
        pending_page=pending_page,
        pending_has_next=pending_has_next,
        pending_total=pending_total,
        active_rows=active_rows,
        active_list_page=active_page,
        active_has_next=active_has_next,
        history_rows=history_rows,
        history_page=history_page,
        history_has_next=history_has_next,
        admins_inactive_count=active_total,
    )


@app.post("/administration/inactives/{inactive_id}/update", name="administration_update_inactive")
async def administration_update_inactive(
    request: Request,
    inactive_id: int,
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_access_admin_reviews(actor):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(admin_redirect_path("inactives"))
    record = Inactives.get_or_none(Inactives.id == inactive_id)
    if record is None:
        set_flash(request, "Неактив не найден.", "error")
        return redirect(admin_redirect_path("inactives"))
    owner = Users.get_or_none(Users.nickname == record.nickname)
    if owner is None or user_scope(owner) != "admins":
        set_flash(request, "Неактив относится к другой сфере.", "error")
        return redirect(admin_redirect_path("inactives"))
    try:
        start_dt = parse_iso_date(start_date)
        end_dt = parse_iso_date(end_date)
    except ValueError:
        set_flash(request, "Проверьте даты неактива.", "error")
        return redirect(admin_redirect_path("inactives"))
    if end_dt < start_dt:
        set_flash(request, "Дата окончания не может быть раньше даты начала.", "error")
        return redirect(admin_redirect_path("inactives"))
    old_penalty = getattr(record, "penalty_amount", None) or 0
    new_penalty = penalty_amount_for_user(owner, start_dt, end_dt) if old_penalty > 0 else 0
    owner.inactivestart = formatedtotts(start_dt.strftime("%d.%m.%Y"))
    owner.inactiveend = inclusive_end_timestamp(end_dt)
    owner.apa = max(owner.apa + old_penalty - new_penalty, 0)
    owner.save()
    request_record = inactive_request_for_inactive_row(owner, record)
    record.start = start_dt.strftime("%d.%m.%Y")
    record.end = end_dt.strftime("%d.%m.%Y")
    record.reason = reason.strip()
    if request_record is not None and not getattr(record, "request_id", None):
        record.request_id = request_record.id
    record.penalty_amount = new_penalty
    record.save()
    if request_record is not None:
        request_record.start = record.start
        request_record.end = record.end
        request_record.reason = record.reason
        request_record.w = new_penalty
        request_record.save()
    sync_sheets(composition=True, inactives=True)
    set_flash(request, "Неактив обновлён.", "success")
    return redirect(admin_redirect_path("inactives"))


@app.post("/administration/inactives/{inactive_id}/delete", name="administration_delete_inactive")
async def administration_delete_inactive(
    request: Request,
    inactive_id: int,
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_access_admin_reviews(actor):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(admin_redirect_path("inactives"))
    record = Inactives.get_or_none(Inactives.id == inactive_id)
    if record is None:
        set_flash(request, "Неактив не найден.", "error")
        return redirect(admin_redirect_path("inactives"))
    owner = Users.get_or_none(Users.nickname == record.nickname)
    if owner is None or user_scope(owner) != "admins":
        set_flash(request, "Неактив относится к другой сфере.", "error")
        return redirect(admin_redirect_path("inactives"))

    penalty_amount = getattr(record, "penalty_amount", None) or 0
    current_start = formatts(owner.inactivestart) if owner.inactivestart else None
    current_end = formatts(owner.inactiveend) if owner.inactiveend else None
    is_current_record = (
        current_start == record.start
        and current_end == record.end
        and record.status == "Одобрен"
    )
    has_same_active_duplicate = (
        Inactives.select()
        .where(
            Inactives.id != record.id,
            Inactives.nickname == record.nickname,
            Inactives.start == record.start,
            Inactives.end == record.end,
            Inactives.status == "Одобрен",
        )
        .exists()
    )

    if record.status == "Одобрен" and penalty_amount > 0:
        owner.apa += penalty_amount
    if is_current_record and not has_same_active_duplicate:
        owner.inactivestart = None
        owner.inactiveend = None
    owner.save()

    record.delete_instance()
    sync_sheets(composition=True, inactives=True)
    set_flash(request, "Неактив полностью удалён.", "success")
    return redirect(admin_redirect_path("inactives"))


@app.get("/administration/forms", response_class=HTMLResponse, name="administration_forms_page")
async def administration_forms_page(request: Request, pending_page: int = 1, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_admin_reviews(user):
        set_flash(request, "У вас нет доступа к этому разделу.", "error")
        return redirect("/dashboard")
    pending_rows_all, history_rows_all, approved_total = admin_forms_page_rows()
    pending_page = normalize_page(pending_page)
    history_page = normalize_page(history_page)
    pending_rows, pending_has_next = paginate_list(pending_rows_all, pending_page, ADMIN_LIST_PAGE_SIZE)
    history_rows, history_has_next = paginate_list(history_rows_all, history_page, ADMIN_LIST_PAGE_SIZE)
    return render(
        request,
        "administration_forms.html",
        "Администрация • Формы",
        "administration_forms",
        pending_rows=pending_rows,
        pending_page=pending_page,
        pending_has_next=pending_has_next,
        history_rows=history_rows,
        history_page=history_page,
        history_has_next=history_has_next,
        approved_total=approved_total,
        pending_total=len(pending_rows_all),
    )


@app.get("/administration/reports", response_class=HTMLResponse, name="administration_reports_page")
async def administration_reports_page(
    request: Request,
    objective_page: int = 1,
    additional_page: int = 1,
    history_page: int = 1,
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_admin_reviews(user):
        set_flash(request, "У вас нет доступа к этому разделу.", "error")
        return redirect("/dashboard")
    objective_rows_all, additional_rows_all, history_rows_all = admin_reports_page_rows()
    objective_page = normalize_page(objective_page)
    additional_page = normalize_page(additional_page)
    history_page = normalize_page(history_page)
    pending_objective_rows, objective_has_next = paginate_list(objective_rows_all, objective_page, ADMIN_LIST_PAGE_SIZE)
    pending_additional_rows, additional_has_next = paginate_list(additional_rows_all, additional_page, ADMIN_LIST_PAGE_SIZE)
    history_rows, history_has_next = paginate_list(history_rows_all, history_page, ADMIN_LIST_PAGE_SIZE)
    return render(
        request,
        "administration_reports.html",
        "Администрация • Отчёты",
        "administration_reports",
        pending_objective_rows=pending_objective_rows,
        objective_page=objective_page,
        objective_has_next=objective_has_next,
        pending_additional_rows=pending_additional_rows,
        additional_page=additional_page,
        additional_has_next=additional_has_next,
        history_rows=history_rows,
        history_page=history_page,
        history_has_next=history_has_next,
    )


@app.get("/administration/punishments", response_class=HTMLResponse, name="administration_punishments_page")
async def administration_punishments_page(request: Request, pending_page: int = 1, history_page: int = 1):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_admin_reviews(user):
        set_flash(request, "У вас нет доступа к этому разделу.", "error")
        return redirect("/dashboard")
    pending_rows_all, history_rows_all = admin_punishment_page_rows()
    pending_page = normalize_page(pending_page)
    history_page = normalize_page(history_page)
    pending_rows, pending_has_next = paginate_list(pending_rows_all, pending_page, ADMIN_LIST_PAGE_SIZE)
    history_rows, history_has_next = paginate_list(history_rows_all, history_page, ADMIN_LIST_PAGE_SIZE)
    return render(
        request,
        "administration_punishments.html",
        "Администрация • Наказания",
        "administration_punishments",
        pending_rows=pending_rows,
        pending_page=pending_page,
        pending_has_next=pending_has_next,
        history_rows=history_rows,
        history_page=history_page,
        history_has_next=history_has_next,
    )


@app.get("/management/{scope}", response_class=HTMLResponse, name="management_page")
async def management_page(request: Request, scope: str, user_id: int | None = None, search: str = ""):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if scope not in SCOPE_TITLES or not can_manage_scope(user, scope):
        set_flash(request, "У вас нет доступа к этому разделу.", "error")
        return redirect("/dashboard")
    users = sorted(list(scope_queryset(scope)), key=lambda item: scope_sort_key(scope, item))
    if search:
        users = [item for item in users if search.lower() in item.nickname.lower()]
    selected = None
    if user_id:
        selected = next((item for item in users if item.id == user_id), None)
    if selected is None and users:
        selected = users[0]
    pending_inactive_requests = []
    if scope != "admins":
        for row in (
            InactiveRequests.select()
            .where(InactiveRequests.status == "pending")
            .order_by(InactiveRequests.id.desc())
        ):
            owner = owner_for_request(row)
            if owner is None or user_scope(owner) != scope:
                continue
            pending_inactive_requests.append(
                {
                    "id": row.id,
                    "owner": owner,
                    "start": row.start,
                    "end": row.end,
                    "reason": row.reason,
                    "penalty": row.w,
                    "created_at": format_datetime(getattr(row, "created_at", None)),
                }
            )
    recent_inactives = []
    for row in Inactives.select().order_by(Inactives.id.desc()).limit(20):
        owner = Users.get_or_none(Users.nickname == row.nickname)
        row_scope = user_scope(owner) if owner is not None else ("leaders" if row.fraction else "admins")
        if row_scope != scope:
            continue
        recent_inactives.append(build_inactive_row(row))
    removed_scope = REMOVED_STRUCT[scope]
    removed_rows = list(
        Removed.select()
        .where(Removed.struct == removed_scope)
        .order_by(Removed.id.desc())
        .limit(10)
    )
    active_rows = []
    history_rows = []
    selected_card = None
    if selected:
        selected_card = user_card(selected)
        active_rows, history_rows = punishment_entries(selected)
    return render(
        request,
        "management.html",
        f"Управление {SCOPE_TITLES[scope].lower()}",
        f"management_{scope}",
        scope=scope,
        users=users,
        selected=selected,
        selected_card=selected_card,
        selected_active_punishments=active_rows,
        selected_punishment_history=history_rows[:20],
        pending_inactive_requests=pending_inactive_requests,
        recent_inactives=recent_inactives,
        removed_rows=removed_rows,
        search=search,
        today=today_str(),
    )


@app.post("/management/{scope}/metric", name="management_change_metric")
async def management_change_metric(
    request: Request,
    scope: str,
    user_id: int = Form(...),
    amount: int = Form(...),
    operation: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target = target_or_none(user_id, scope)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(f"/management/{scope}")
    if operation not in {"+", "-"}:
        set_flash(request, "Неизвестная операция.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target.apa = max(target.apa + amount if operation == "+" else target.apa - amount, 0)
    target.save()
    sync_sheets(composition=True)
    set_flash(request, f"{SCOPE_METRIC_LABELS[scope]} пользователя обновлены.", "success")
    return redirect(f"/management/{scope}?user_id={user_id}")


@app.post("/management/{scope}/inactive", name="management_set_inactive")
async def management_set_inactive(
    request: Request,
    scope: str,
    user_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target = target_or_none(user_id, scope)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(f"/management/{scope}")
    try:
        start_dt = parse_iso_date(start_date)
        end_dt = parse_iso_date(end_date)
    except ValueError:
        set_flash(request, "Проверьте даты неактива.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    if end_dt < start_dt:
        set_flash(request, "Дата окончания не может быть раньше даты начала.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    penalty = penalty_amount_for_user(target, start_dt, end_dt)
    Inactives.create(
        nickname=target.nickname,
        role=target.role,
        fraction=target.fraction,
        start=start_dt.strftime("%d.%m.%Y"),
        end=end_dt.strftime("%d.%m.%Y"),
        status="Одобрен",
        reason=reason.strip(),
        requested_by=actor.telegram_id,
        processed_by=actor.telegram_id,
        processed_at=now_ts(),
        process_comment=None,
        request_id=None,
        penalty_amount=penalty,
    )
    target.inactivestart = formatedtotts(start_dt.strftime("%d.%m.%Y"))
    target.inactiveend = inclusive_end_timestamp(end_dt)
    apply_penalty(target, penalty)
    sync_sheets(composition=True, inactives=True)
    set_flash(request, f"Неактив выдан, {SCOPE_METRIC_ACTION_LABELS[scope]} автоматически уменьшены.", "success")
    return redirect(f"/management/{scope}?user_id={user_id}")


@app.post("/management/{scope}/inactive/{user_id}/clear", name="management_clear_inactive")
async def management_clear_inactive(
    request: Request,
    scope: str,
    user_id: int,
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target = target_or_none(user_id, scope)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(f"/management/{scope}")
    target.inactivestart = None
    target.inactiveend = None
    target.save()
    sync_sheets(composition=True, inactives=True)
    set_flash(request, "Действующий неактив снят.", "success")
    return redirect(f"/management/{scope}?user_id={user_id}")


@app.post("/management/{scope}/punishments", name="management_add_punishment")
async def management_add_punishment(
    request: Request,
    scope: str,
    user_id: int = Form(...),
    punishment_type: str = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target = target_or_none(user_id, scope)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(f"/management/{scope}")
    if punishment_type not in PUNISHMENT_LABELS:
        set_flash(request, "Неизвестный тип наказания.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    setattr(target, punishment_type, getattr(target, punishment_type) + 1)
    target.save()
    PunishmentEntries.create(
        user=target,
        scope=scope,
        punishment_type=punishment_type,
        reason=reason.strip(),
        issued_by=actor.telegram_id,
        issued_at=now_ts(),
    )
    sync_sheets(composition=True)
    set_flash(request, "Наказание выдано.", "success")
    return redirect(f"/management/{scope}?user_id={user_id}")


@app.post("/management/{scope}/dismiss", name="management_dismiss_user")
async def management_dismiss_user(
    request: Request,
    scope: str,
    user_id: int = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/management/{scope}?user_id={user_id}")
    target = target_or_none(user_id, scope)
    if target is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(f"/management/{scope}")
    create_removed_entry(target, actor, reason.strip())
    WebCredentials.delete().where(WebCredentials.user == target).execute()
    Inactives.delete().where(Inactives.nickname == target.nickname).execute()
    target.delete_instance()
    sync_sheets(composition=True, removed=True, inactives=True)
    set_flash(request, "Пользователь снят с должности.", "success")
    return redirect(f"/management/{scope}")


@app.post("/management/{scope}/review/inactive/{request_id}", name="review_inactive_request")
async def review_inactive_request(
    request: Request,
    scope: str,
    request_id: int,
    decision: str = Form(...),
    comment: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    redirect_url = admin_redirect_path("inactives") if scope == "admins" else f"/management/{scope}"
    if actor is None:
        return redirect("/login")
    if not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(redirect_url)
    inactive_request = InactiveRequests.get_or_none(InactiveRequests.id == request_id)
    if inactive_request is None or inactive_request.status != "pending":
        set_flash(request, "Заявка уже обработана или не найдена.", "error")
        return redirect(redirect_url)
    owner = user_by_telegram_value(inactive_request.tgid)
    if owner is None or user_scope(owner) != scope:
        set_flash(request, "Заявка относится к другой сфере.", "error")
        return redirect(redirect_url)
    if decision not in {"approve", "reject", "approve_no_metric", "approve_with_metric"}:
        set_flash(request, "Неизвестное решение по заявке.", "error")
        return redirect(redirect_url)
    is_approved = decision in {"approve", "approve_no_metric", "approve_with_metric"}
    apply_metric = decision in {"approve", "approve_with_metric"} or (scope != "admins" and decision == "approve")
    penalty_amount = inactive_request.w if (is_approved and apply_metric) else 0
    inactive_request.status = "approved" if is_approved else "rejected"
    inactive_request.processed_by = actor.telegram_id
    inactive_request.processed_at = now_ts()
    inactive_request.process_comment = comment.strip() or None
    inactive_request.save()
    Inactives.create(
        nickname=owner.nickname,
        role=owner.role,
        fraction=owner.fraction,
        start=inactive_request.start,
        end=inactive_request.end,
        status="Одобрен" if is_approved else "Отказан",
        reason=inactive_request.reason,
        requested_by=owner.telegram_id,
        processed_by=actor.telegram_id,
        processed_at=inactive_request.processed_at,
        process_comment=inactive_request.process_comment,
        request_id=inactive_request.id,
        penalty_amount=penalty_amount,
    )
    if is_approved:
        owner.inactivestart = formatedtotts(inactive_request.start)
        owner.inactiveend = inclusive_end_timestamp(parse_ru_date(inactive_request.end))
        if penalty_amount > 0:
            apply_penalty(owner, penalty_amount)
        else:
            owner.save()
        sync_sheets(composition=True, inactives=True)
        if penalty_amount > 0:
            set_flash(request, "Заявка на неактив одобрена со снятием ответов.", "success")
        else:
            set_flash(request, "Заявка на неактив одобрена без снятия ответов.", "success")
    else:
        sync_sheets(inactives=True)
        set_flash(request, "Заявка на неактив отклонена.", "success")
    return redirect(redirect_url)


@app.post("/management/{scope}/review/report/{report_id}", name="review_report")
async def review_report(
    request: Request,
    scope: str,
    report_id: int,
    decision: str = Form(...),
    amount: int = Form(0),
    counts_for_objective: str | None = Form(None),
    result: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    redirect_url = admin_redirect_path("reports") if scope == "admins" else f"/management/{scope}"
    if actor is None:
        return redirect("/login")
    if scope != "admins" or not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(redirect_url)
    report = Reports.get_or_none(Reports.id == report_id)
    if report is None or report.status != "pending":
        set_flash(request, "Отчёт уже обработан или не найден.", "error")
        return redirect(redirect_url)
    if decision not in {"approve", "reject", "approve_objective", "approve_answers"}:
        set_flash(request, "Неизвестное решение по отчёту.", "error")
        return redirect(redirect_url)
    is_approved = decision in {"approve", "approve_objective", "approve_answers"}
    counts_objective = bool(counts_for_objective) or decision == "approve_objective"
    report.status = "approved" if is_approved else "rejected"
    report.checked_by = actor.telegram_id
    report.result = result.strip() or None
    report.credited_amount = amount if is_approved else 0
    report.counts_for_objective = 1 if (is_approved and report.report_type == "objective" and counts_objective) else 0
    report.processed_at = now_ts()
    report.save()
    if is_approved:
        report.user.apa += max(amount, 0)
        if report.report_type == "objective" and counts_objective:
            report.user.objective_completed = (report.user.objective_completed or 0) + 1
            Objectives.create(telegram_id=str(report.user.telegram_id), time=now_ts())
        report.user.save()
        sync_sheets(composition=True)
        set_flash(request, f"Отчёт одобрен, {SCOPE_METRIC_ACTION_LABELS['admins']} обновлены.", "success")
    else:
        set_flash(request, "Отчёт отклонён.", "success")
    return redirect(redirect_url)


@app.post("/management/{scope}/review/form/{form_id}", name="review_form")
async def review_form(
    request: Request,
    scope: str,
    form_id: int,
    decision: str = Form(...),
    result: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    redirect_url = admin_redirect_path("forms") if scope == "admins" else f"/management/{scope}"
    if actor is None:
        return redirect("/login")
    if scope != "admins" or not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(redirect_url)
    form = Forms.get_or_none(Forms.id == form_id)
    if form is None or form.status != "pending":
        set_flash(request, "Форма уже обработана или не найдена.", "error")
        return redirect(redirect_url)
    if decision not in {"approve", "reject"}:
        set_flash(request, "Неизвестное решение по форме.", "error")
        return redirect(redirect_url)
    form.status = "approved" if decision == "approve" else "rejected"
    form.processed_by = actor.telegram_id
    form.processed_at = now_ts()
    form.result = result.strip() or None
    form.save()
    set_flash(request, "Форма обработана.", "success")
    return redirect(redirect_url)


@app.post("/management/{scope}/review/punishment/{request_id}", name="review_punishment_request")
async def review_punishment_request(
    request: Request,
    scope: str,
    request_id: int,
    decision: str = Form(...),
    answers_penalty: int = Form(0),
    comment: str = Form(""),
    reason: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    redirect_url = admin_redirect_path("punishments") if scope == "admins" else f"/management/{scope}"
    if actor is None:
        return redirect("/login")
    if scope != "admins" or not can_manage_scope(actor, scope):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(redirect_url)
    punishment_request = PunishmentsRequests.get_or_none(PunishmentsRequests.id == request_id)
    if punishment_request is None or punishment_request.status != "pending":
        set_flash(request, "Заявка уже обработана или не найдена.", "error")
        return redirect(redirect_url)
    owner = user_by_telegram_value(punishment_request.telegram_id)
    if owner is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect(redirect_url)
    if decision not in {"approve", "reject"}:
        set_flash(request, "Неизвестное решение по заявке.", "error")
        return redirect(redirect_url)
    if answers_penalty < 0:
        set_flash(request, "Количество ответов не может быть отрицательным.", "error")
        return redirect(redirect_url)
    comment_text = comment.strip() or reason.strip() or None
    punishment_request.status = "approved" if decision == "approve" else "rejected"
    punishment_request.processed_by = actor.telegram_id
    punishment_request.processed_at = now_ts()
    punishment_request.reason = comment_text
    punishment_request.answers_penalty = answers_penalty if decision == "approve" else 0
    punishment_request.save()
    if decision == "approve":
        setattr(owner, punishment_request.punishment, max(getattr(owner, punishment_request.punishment) - 1, 0))
        owner.apa = max(owner.apa - answers_penalty, 0)
        owner.save()
        entry = (
            PunishmentEntries.select()
            .where(
                PunishmentEntries.user == owner,
                PunishmentEntries.punishment_type == punishment_request.punishment,
                PunishmentEntries.removed_at.is_null(True),
            )
            .order_by(PunishmentEntries.issued_at.asc())
            .first()
        )
        if entry is not None:
            entry.removed_at = now_ts()
            entry.removed_by = actor.telegram_id
            entry.removed_reason = comment_text or ("Снято по заявке" if not answers_penalty else f"Снято по заявке, ответов списано: {answers_penalty}")
            entry.save()
        sync_sheets(composition=True)
        set_flash(request, "Наказание снято.", "success")
    else:
        set_flash(request, "Заявка на снятие наказания отклонена.", "success")
    return redirect(redirect_url)


@app.get("/server", response_class=HTMLResponse, name="server_page")
async def server_page(request: Request, edit_user_id: int | None = None):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_server(user):
        set_flash(request, "У вас нет доступа к управлению сервером.", "error")
        return redirect("/dashboard")
    users = list(Users.select().order_by(Users.nickname.asc()))
    credentials = {
        cred.user_id: cred for cred in WebCredentials.select()
    }
    edit_user = Users.get_or_none(Users.id == edit_user_id) if edit_user_id else None
    settings = {
        "leaders_term_days": int(db_setting(Settings_l, "term_days", LEADERS_TIME_LEFT)),
        "leaders_inactive_points": int(db_setting(Settings_l, "inactiveamnt_points", 5)),
        "support_inactive_asks": int(db_setting(Settings_s, "inactiveamnt_asks", 10)),
        "support_transfer_days": int(db_setting(Settings_s, "transferamnt_d", 10)),
        "support_transfer_asks": int(db_setting(Settings_s, "transferamnt_a", 500)),
        "admins_inactive_answers": int(db_setting(Settings_a, "inactiveamnt_answers", 100)),
        "sheet_support": db_setting(Sheets, "s", ""),
        "sheet_leaders": db_setting(Sheets, "l", ""),
        "sheet_admins": db_setting(Sheets, "a", ""),
    }
    return render(
        request,
        "server.html",
        "Управление сервером",
        "server",
        summary=active_users_summary(),
        users=users,
        credentials=credentials,
        edit_user=edit_user,
        settings=settings,
        role_options=["__leader__", *SUPPORT_ROLES, *ROLES],
        fractions=FRACTIONS,
    )


@app.post("/server/settings", name="update_server_settings")
async def update_server_settings(
    request: Request,
    leaders_term_days: int = Form(...),
    leaders_inactive_points: int = Form(...),
    support_inactive_asks: int = Form(...),
    support_transfer_days: int = Form(...),
    support_transfer_asks: int = Form(...),
    admins_inactive_answers: int = Form(...),
    sheet_support: str = Form(""),
    sheet_leaders: str = Form(""),
    sheet_admins: str = Form(""),
    csrf_token: str = Form(...),
):
    user = require_auth(request)
    if user is None:
        return redirect("/login")
    if not can_access_server(user):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/server")
    set_setting_value(Settings_l, "term_days", leaders_term_days)
    set_setting_value(Settings_l, "inactiveamnt_points", leaders_inactive_points)
    set_setting_value(Settings_s, "inactiveamnt_asks", support_inactive_asks)
    set_setting_value(Settings_s, "transferamnt_d", support_transfer_days)
    set_setting_value(Settings_s, "transferamnt_a", support_transfer_asks)
    set_setting_value(Settings_a, "inactiveamnt_answers", admins_inactive_answers)
    set_setting_value(Sheets, "s", sheet_support.strip())
    set_setting_value(Sheets, "l", sheet_leaders.strip())
    set_setting_value(Sheets, "a", sheet_admins.strip())
    set_flash(request, "Настройки сервера обновлены.", "success")
    return redirect("/server")


def parse_optional_int(value: str) -> int:
    cleaned = value.strip()
    return int(cleaned) if cleaned else 0


@app.post("/server/users/create", name="create_server_user")
async def create_server_user(
    request: Request,
    nickname: str = Form(...),
    role_value: str = Form(...),
    name: str = Form(...),
    birth_date: str = Form(...),
    city: str = Form(...),
    discord_id: str = Form(""),
    telegram_id: str = Form(""),
    forum: str = Form(""),
    vk: str = Form(""),
    fraction: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_access_server(actor):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/server")
    if Users.get_or_none(Users.nickname == nickname.strip()):
        set_flash(request, "Пользователь с таким ником уже существует.", "error")
        return redirect("/server")
    if role_value == "__leader__" and fraction not in FRACTIONS:
        set_flash(request, "Для лидера нужно выбрать фракцию.", "error")
        return redirect("/server")
    try:
        birth_ts = int(parse_iso_date(birth_date).timestamp())
        telegram_numeric = parse_optional_int(telegram_id)
        discord_numeric = parse_optional_int(discord_id)
    except ValueError:
        set_flash(request, "Проверьте дату рождения и числовые поля.", "error")
        return redirect("/server")
    user = Users.create(
        nickname=nickname.strip(),
        role=None,
        fraction=None,
        appointed=now_ts(),
        promoted=None,
        objective_completed=0,
        apa=0,
        rebuke=0,
        warn=0,
        verbal=0,
        inactivestart=None,
        inactiveend=None,
        name=name.strip(),
        age=birth_ts,
        city=city.strip(),
        discord_id=discord_numeric,
        telegram_id=telegram_numeric,
        forum=forum.strip(),
        vk=vk.strip(),
        coins=0,
        coins_last_spend=0,
    )
    assign_role(user, role_value, fraction or None)
    user.save()
    credentials, _ = WebCredentials.get_or_create(user=user)
    credentials.invite_token = generate_token()
    credentials.invite_created_by = actor.telegram_id
    credentials.invite_created_at = now_ts()
    credentials.invite_used_at = None
    credentials.save()
    link = build_invite_url(request, credentials.invite_token)
    set_generated_link(request, user.nickname, link)
    sync_sheets(composition=True)
    set_flash(request, "Пользователь создан. Ссылка ниже одноразовая.", "success")
    return redirect("/server")


@app.post("/server/users/{user_id}/update", name="update_server_user")
async def update_server_user(
    request: Request,
    user_id: int,
    nickname: str = Form(...),
    role_value: str = Form(...),
    name: str = Form(...),
    birth_date: str = Form(...),
    city: str = Form(...),
    discord_id: str = Form(""),
    telegram_id: str = Form(""),
    forum: str = Form(""),
    vk: str = Form(""),
    fraction: str = Form(""),
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_access_server(actor):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect(f"/server?edit_user_id={user_id}")
    user = Users.get_or_none(Users.id == user_id)
    if user is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/server")
    duplicate = Users.get_or_none(Users.nickname == nickname.strip(), Users.id != user_id)
    if duplicate:
        set_flash(request, "Пользователь с таким ником уже существует.", "error")
        return redirect(f"/server?edit_user_id={user_id}")
    if role_value == "__leader__" and fraction not in FRACTIONS:
        set_flash(request, "Для лидера нужно выбрать фракцию.", "error")
        return redirect(f"/server?edit_user_id={user_id}")
    try:
        user.nickname = nickname.strip()
        user.name = name.strip()
        user.age = int(parse_iso_date(birth_date).timestamp())
        user.city = city.strip()
        user.discord_id = parse_optional_int(discord_id)
        user.telegram_id = parse_optional_int(telegram_id)
        user.forum = forum.strip()
        user.vk = vk.strip()
    except ValueError:
        set_flash(request, "Проверьте дату рождения и числовые поля.", "error")
        return redirect(f"/server?edit_user_id={user_id}")
    assign_role(user, role_value, fraction or None)
    user.save()
    sync_sheets(composition=True)
    set_flash(request, "Данные пользователя обновлены.", "success")
    return redirect(f"/server?edit_user_id={user_id}")


@app.post("/server/users/{user_id}/reset-password", name="reset_server_user_password")
async def reset_server_user_password(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
):
    actor = require_auth(request)
    if actor is None:
        return redirect("/login")
    if not can_access_server(actor):
        return redirect("/dashboard")
    if not validate_csrf(request, csrf_token):
        set_flash(request, "Сессия формы устарела.", "error")
        return redirect("/server")
    user = Users.get_or_none(Users.id == user_id)
    if user is None:
        set_flash(request, "Пользователь не найден.", "error")
        return redirect("/server")
    credentials, _ = WebCredentials.get_or_create(user=user)
    credentials.invite_token = generate_token()
    credentials.invite_created_by = actor.telegram_id
    credentials.invite_created_at = now_ts()
    credentials.invite_used_at = None
    credentials.save()
    link = build_invite_url(request, credentials.invite_token)
    set_generated_link(request, user.nickname, link)
    set_flash(request, "Одноразовая ссылка для сброса пароля создана.", "success")
    return redirect("/server")


@app.get("/attachments/{entity}/{record_id}/{index}", name="download_attachment")
async def download_attachment(
    request: Request,
    entity: str,
    record_id: int,
    index: int,
    mode: str = "download",
):
    viewer = require_auth(request)
    if viewer is None:
        return redirect("/login")
    if entity == "report":
        record = Reports.get_or_none(Reports.id == record_id)
        if record is None or not visible_report(record, viewer):
            set_flash(request, "Файл недоступен.", "error")
            return redirect("/dashboard")
        items = parse_report_attachments(record.attachments)
    elif entity == "form":
        record = Forms.get_or_none(Forms.id == record_id)
        if record is None or not visible_form(record, viewer):
            set_flash(request, "Файл недоступен.", "error")
            return redirect("/dashboard")
        items = parse_form_proofs(record.proofs)
    else:
        set_flash(request, "Файл недоступен.", "error")
        return redirect("/dashboard")
    if index < 0 or index >= len(items):
        set_flash(request, "Файл не найден.", "error")
        return redirect("/dashboard")
    item = items[index]
    if item.get("type") == "link":
        return RedirectResponse(item["url"], status_code=302)
    filepath = (UPLOADS_DIR / item["path"]).resolve()
    if not filepath.exists() or UPLOADS_DIR.resolve() not in filepath.parents:
        set_flash(request, "Файл не найден.", "error")
        return redirect("/dashboard")
    return FileResponse(
        filepath,
        filename=item["name"],
        content_disposition_type="inline" if mode == "view" else "attachment",
    )
