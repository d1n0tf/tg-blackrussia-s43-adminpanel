import threading
import time
import traceback
from math import ceil

import gspread
from gspread import Cell
from loguru import logger

from Bot.utils import calcage, calcdateofbirth, formatts, plural_word
from config import FRACTIONS, LEADERS_TIME_LEFT, ROLES, SUPPORT_ROLES
from db import Inactives, Removed, Settings_s, Sheets, Users

try:
    google_sheets = gspread.service_account(filename="credits.json")
except FileNotFoundError:
    google_sheets = None
except Exception:
    google_sheets = None
    logger.exception("Unable to initialize Google Sheets client")
_lastupdate = 0
_update_interval = 60
_update_lock = threading.Lock()
_update_pending = {"composition": False, "removed": False, "inactives": False}
_update_worker_running = False
_credentials_warning_logged = False


def getSheetsByID(sheetid: str):
    global _credentials_warning_logged
    if google_sheets is None or not sheetid or len(sheetid.strip()) < 20:
        if google_sheets is None and not _credentials_warning_logged:
            logger.warning("Google Sheets sync skipped: credits.json is missing or invalid")
            _credentials_warning_logged = True
        return
    sh = google_sheets.open_by_key(sheetid)
    return sh.get_worksheet(0), sh.get_worksheet(1), sh.get_worksheet(2)


def getappointformbycode(sheetid: str, code: str, nickname: str | None) -> list | None:
    if google_sheets is None or not sheetid or len(sheetid.strip()) < 20:
        return
    sh = google_sheets.open_by_key(sheetid)
    ws = sh.get_worksheet(0)
    for i in ws.get_all_values()[::-1]:
        if i[2].strip() == code.strip() and (
            nickname is None or i[3].strip() == nickname.strip()
        ):
            res = i[3:]
            for k, y in enumerate(res):
                if isinstance(y, str):
                    res[k] = y.strip()
            return res  # nickname, name, age, city, discord_id, vk, forum, telegram_id
    return None


def search(sheetid: str, value) -> list | None:
    if google_sheets is None or not sheetid or len(sheetid.strip()) < 20:
        return
    value = str(value)
    res = [[], []]
    sh = google_sheets.open_by_key(sheetid)
    for wsi in range(0, 6):
        ws = sh.get_worksheet(wsi)
        for i in ws.get_all_values()[::-1]:
            if any(
                (value[2:] if (len(value) > 2 and value[:2] == "id") else value)
                in str(y)
                for y in (
                    (
                        (i[4], i[7], i[8]),
                        (i[3], i[6], i[7]),
                        (i[3], i[6], i[7]),
                        (i[3], i[6], i[7]),
                        (i[3], i[6], i[7]),
                        (i[3], i[5], i[6]),
                    )[wsi]
                )
            ):
                res[0 if wsi < 3 else 1].append(
                    tuple(
                        [
                            i[k]
                            for k in (
                                (0, 3, 2, 5, 6, 7, 10, 8, 11, 13),
                                (0, 2, 1, 4, 5, 6, 9, 7, 10, 11),
                                (0, 2, 1, 4, 5, 6, 9, 7, 10, 11),
                                (0, 2, 1, 5, 10, 6, 9, 7, 11, 12),
                                (0, 2, 1, 5, 10, 6, 9, 7, 11, 12),
                                (2, 1, 0, 4, 9, 5, 8, 6, 10, 11),
                            )[wsi]
                        ]
                    )
                )
    return res


def main(composition: bool = False, removed: bool = False, inactives: bool = False):
    global _update_worker_running
    if not any((composition, removed, inactives)):
        return
    with _update_lock:
        _update_pending["composition"] = _update_pending["composition"] or composition
        _update_pending["removed"] = _update_pending["removed"] or removed
        _update_pending["inactives"] = _update_pending["inactives"] or inactives
        if _update_worker_running:
            return
        _update_worker_running = True
    try:
        threading.Thread(
            target=_run_pending_updates,
            daemon=True,
        ).start()
    except Exception:
        with _update_lock:
            _update_worker_running = False
        logger.exception(traceback.format_exc())


def _run_pending_updates():
    global _lastupdate, _update_worker_running
    try:
        while True:
            with _update_lock:
                composition = _update_pending["composition"]
                removed = _update_pending["removed"]
                inactives = _update_pending["inactives"]
                _update_pending["composition"] = False
                _update_pending["removed"] = False
                _update_pending["inactives"] = False
            if not any((composition, removed, inactives)):
                with _update_lock:
                    if not any(_update_pending.values()):
                        _update_worker_running = False
                        return
                continue
            delay = _update_interval - (time.time() - _lastupdate)
            if delay > 0:
                time.sleep(delay)
                with _update_lock:
                    composition = composition or _update_pending["composition"]
                    removed = removed or _update_pending["removed"]
                    inactives = inactives or _update_pending["inactives"]
                    _update_pending["composition"] = False
                    _update_pending["removed"] = False
                    _update_pending["inactives"] = False
            _lastupdate = time.time()
            fill(composition, removed, inactives)
    except Exception:
        logger.exception(traceback.format_exc())
        with _update_lock:
            _update_worker_running = False


def fill(composition: bool, removed: bool, inactives: bool):
    try:
        sheet_s = getSheetsByID(Sheets.get(Sheets.setting == "s").val)
        if sheet_s is None:
            return
        sheet_l = getSheetsByID(Sheets.get(Sheets.setting == "l").val)
        if sheet_l is None:
            return
        sheet_a = getSheetsByID(Sheets.get(Sheets.setting == "a").val)
        if sheet_a is None:
            return
        composition_s, removed_s, inactives_s = sheet_s
        composition_l, removed_l, inactives_l = sheet_l
        composition_a, removed_a, inactives_a = sheet_a
        if composition:
            compdata_s = sorted(
                Users.select().where(Users.role == SUPPORT_ROLES[1]),
                key=lambda x: x.appointed,
            ) + sorted(
                Users.select().where(Users.role == SUPPORT_ROLES[0]),
                key=lambda x: x.appointed,
            )
            compdata_l = sorted(
                Users.select().where(Users.role.is_null(True)),
                key=lambda x: FRACTIONS.index(x.fraction),
            )
            compdata_a = sorted(
                Users.select().where(Users.role << ROLES),
                key=lambda x: (
                    ROLES.index(x.role),
                    x.promoted if x.promoted else x.appointed,
                ),
            )
            fillcompisiton_s(composition_s, compdata_s)
            fillcompisiton_l(composition_l, compdata_l)
            fillcompisiton_a(composition_a, compdata_a)
        if removed:
            removeddata_s = Removed.select().where(Removed.role << SUPPORT_ROLES)[::-1]
            removeddata_l = Removed.select().where(Removed.role.is_null(True))[::-1]
            removeddata_a = Removed.select().where(Removed.role << ROLES)[::-1]
            fillremoved_s(removed_s, removeddata_s)
            fillremoved_l(removed_l, removeddata_l)
            fillremoved_a(removed_a, removeddata_a)
        if inactives:
            inactivesdata_s = Inactives.select().where(Inactives.role << SUPPORT_ROLES)
            inactivesdata_l = Inactives.select().where(Inactives.role.is_null(True))
            inactivesdata_a = Inactives.select().where(Inactives.role << ROLES)
            fillinactives_s(inactives_s, inactivesdata_s)
            fillinactives_l(inactives_l, inactivesdata_l)
            fillinactives_a(inactives_a, inactivesdata_a)
    except gspread.exceptions.APIError:
        logger.exception("Google Sheets API error while filling sheets")
    except Exception:
        logger.exception(traceback.format_exc())


def fillcompisiton_s(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="СОСТАВ АГЕНТОВ ПОДДЕРЖКИ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Должность"),
        Cell(row=2, col=4, value="Назначен"),
        Cell(row=2, col=5, value="Дней до перевода"),
        Cell(row=2, col=6, value="Асков"),
        Cell(row=2, col=7, value="Выговоры"),
        Cell(row=2, col=8, value="Предупреждения"),
        Cell(row=2, col=9, value="Устники"),
        Cell(row=2, col=10, value="Действующий"),
        Cell(row=2, col=11, value="Имя"),
        Cell(row=2, col=12, value="Возраст"),
        Cell(row=2, col=13, value="Город"),
        Cell(row=2, col=14, value="DISCORD"),
        Cell(row=2, col=15, value="TELEGRAM"),
        Cell(row=2, col=16, value="FORUM"),
        Cell(row=2, col=17, value="VK"),
    ]
    transferamnt_d = Settings_s.get(Settings_s.setting == "transferamnt_d").val
    k = 0
    for k, i in enumerate(data):
        inactive = (
            f"{formatts(i.inactivestart)} - {formatts(i.inactiveend)}"
            if i.inactiveend and i.inactiveend > time.time()
            else "Нету"
        )
        utd = transferamnt_d - ceil((time.time() - i.appointed) / 86400)
        utd = 0 if utd < 0 else utd
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.role),
                Cell(row=3 + k, col=4, value=appointed),
                Cell(
                    row=3 + k,
                    col=5,
                    value=f"{utd} {plural_word(utd, ('день', 'дня', 'дней'))}",
                ),
                Cell(row=3 + k, col=6, value=i.apa),
                Cell(row=3 + k, col=7, value=f"{i.rebuke} из 3"),
                Cell(row=3 + k, col=8, value=f"{i.warn} из 2"),
                Cell(row=3 + k, col=9, value=f"{i.verbal} из 2"),
                Cell(row=3 + k, col=10, value=inactive),
                Cell(row=3 + k, col=11, value=i.name),
                Cell(
                    row=3 + k,
                    col=12,
                    value=f"{calcage(i.age)} лет ({calcdateofbirth(i.age)})",
                ),
                Cell(row=3 + k, col=13, value=i.city),
                Cell(row=3 + k, col=14, value=str(i.discord_id)),
                Cell(row=3 + k, col=15, value=i.telegram_id),
                Cell(row=3 + k, col=16, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=17, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:Q1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:Q2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:Q{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillcompisiton_l(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="СОСТАВ ЛИДЕРОВ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Фракция"),
        Cell(row=2, col=4, value="Назначен"),
        Cell(row=2, col=5, value="Дней до перевода"),
        Cell(row=2, col=6, value="Баллов"),
        Cell(row=2, col=7, value="Выговоры"),
        Cell(row=2, col=8, value="Предупреждения"),
        Cell(row=2, col=9, value="Устники"),
        Cell(row=2, col=10, value="Действующий"),
        Cell(row=2, col=11, value="Имя"),
        Cell(row=2, col=12, value="Возраст"),
        Cell(row=2, col=13, value="Город"),
        Cell(row=2, col=14, value="DISCORD"),
        Cell(row=2, col=15, value="TELEGRAM"),
        Cell(row=2, col=16, value="FORUM"),
        Cell(row=2, col=17, value="VK"),
    ]
    k = 0
    for k, i in enumerate(data):
        inactive = (
            f"{formatts(i.inactivestart)} - {formatts(i.inactiveend)}"
            if i.inactiveend and i.inactiveend > time.time()
            else "Нету"
        )
        utd = LEADERS_TIME_LEFT - ceil((time.time() - i.appointed) / 86400)
        utd = 0 if utd < 0 else utd
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.fraction),
                Cell(row=3 + k, col=4, value=appointed),
                Cell(
                    row=3 + k,
                    col=5,
                    value=f"{utd} {plural_word(utd, ('день', 'дня', 'дней'))}",
                ),
                Cell(row=3 + k, col=6, value=i.apa),
                Cell(row=3 + k, col=7, value=f"{i.rebuke} из 3"),
                Cell(row=3 + k, col=8, value=f"{i.warn} из 2"),
                Cell(row=3 + k, col=9, value=f"{i.verbal} из 2"),
                Cell(row=3 + k, col=10, value=inactive),
                Cell(row=3 + k, col=11, value=i.name),
                Cell(
                    row=3 + k,
                    col=12,
                    value=f"{calcage(i.age)} лет ({calcdateofbirth(i.age)})",
                ),
                Cell(row=3 + k, col=13, value=i.city),
                Cell(row=3 + k, col=14, value=str(i.discord_id)),
                Cell(row=3 + k, col=15, value=i.telegram_id),
                Cell(row=3 + k, col=16, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=17, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:Q1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:Q2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:Q{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillcompisiton_a(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="СОСТАВ АДМИНИСТРАЦИИ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Должность"),
        Cell(row=2, col=4, value="Назначен"),
        Cell(row=2, col=5, value="Последнее повышение"),
        Cell(row=2, col=6, value="Норматив"),
        Cell(row=2, col=7, value="Ответов"),
        Cell(row=2, col=8, value="Выговоры"),
        Cell(row=2, col=9, value="Предупреждения"),
        Cell(row=2, col=10, value="Устники"),
        Cell(row=2, col=11, value="Действующий"),
        Cell(row=2, col=12, value="Имя"),
        Cell(row=2, col=13, value="Возраст"),
        Cell(row=2, col=14, value="Город"),
        Cell(row=2, col=15, value="DISCORD"),
        Cell(row=2, col=16, value="TELEGRAM"),
        Cell(row=2, col=17, value="FORUM"),
        Cell(row=2, col=18, value="VK"),
    ]
    k = 0
    for k, i in enumerate(data):
        inactive = (
            f"{formatts(i.inactivestart)} - {formatts(i.inactiveend)}"
            if i.inactiveend and i.inactiveend > time.time()
            else "Нету"
        )
        oc = i.objective_completed if i.objective_completed is not None else "0"
        promoted = formatts(i.promoted) if i.promoted else "Пусто"
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.role),
                Cell(row=3 + k, col=4, value=appointed),
                Cell(row=3 + k, col=5, value=promoted),
                Cell(row=3 + k, col=6, value=oc),
                Cell(row=3 + k, col=7, value=i.apa),
                Cell(row=3 + k, col=8, value=f"{i.rebuke} из 3"),
                Cell(row=3 + k, col=9, value=f"{i.warn} из 2"),
                Cell(row=3 + k, col=10, value=f"{i.verbal} из 2"),
                Cell(row=3 + k, col=11, value=inactive),
                Cell(row=3 + k, col=12, value=i.name),
                Cell(
                    row=3 + k,
                    col=13,
                    value=f"{calcage(i.age)} лет ({calcdateofbirth(i.age)})",
                ),
                Cell(row=3 + k, col=14, value=i.city),
                Cell(row=3 + k, col=15, value=str(i.discord_id)),
                Cell(row=3 + k, col=16, value=i.telegram_id),
                Cell(row=3 + k, col=17, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=18, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:R1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:R2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:R{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillremoved_s(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ СНЯТЫХ АГЕНТОВ ПОДДЕРЖКИ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Назначен"),
        Cell(row=2, col=4, value="Имя"),
        Cell(row=2, col=5, value="Возраст"),
        Cell(row=2, col=6, value="Город"),
        Cell(row=2, col=7, value="DISCORD"),
        Cell(row=2, col=8, value="TELEGRAM"),
        Cell(row=2, col=9, value="FORUM"),
        Cell(row=2, col=10, value="VK"),
        Cell(row=2, col=11, value="Снят кем"),
        Cell(row=2, col=12, value="Причина"),
        Cell(row=2, col=13, value="Дата снятия"),
    ]
    k = 0
    for k, i in enumerate(data):
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{len(data) - k}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=appointed),
                Cell(row=3 + k, col=4, value=i.name),
                Cell(row=3 + k, col=5, value=f"{i.age} лет"),
                Cell(row=3 + k, col=6, value=i.city),
                Cell(row=3 + k, col=7, value=str(i.discord_id)),
                Cell(row=3 + k, col=8, value=i.telegram_id),
                Cell(row=3 + k, col=9, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=10, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
                Cell(row=3 + k, col=11, value=i.whoremoved),
                Cell(row=3 + k, col=12, value=i.reason),
                Cell(row=3 + k, col=13, value=i.date),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:M1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:M2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:M{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillremoved_l(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ СНЯТЫХ ЛИДЕРОВ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Фракция"),
        Cell(row=2, col=4, value="Назначен"),
        Cell(row=2, col=5, value="Имя"),
        Cell(row=2, col=6, value="Возраст"),
        Cell(row=2, col=7, value="Город"),
        Cell(row=2, col=8, value="DISCORD"),
        Cell(row=2, col=9, value="TELEGRAM"),
        Cell(row=2, col=10, value="FORUM"),
        Cell(row=2, col=11, value="VK"),
        Cell(row=2, col=12, value="Снят кем"),
        Cell(row=2, col=13, value="Причина"),
        Cell(row=2, col=14, value="Дата снятия"),
    ]
    k = 0
    for k, i in enumerate(data):
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{len(data) - k}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.fraction),
                Cell(row=3 + k, col=4, value=appointed),
                Cell(row=3 + k, col=5, value=i.name),
                Cell(row=3 + k, col=6, value=f"{i.age} лет"),
                Cell(row=3 + k, col=7, value=i.city),
                Cell(row=3 + k, col=8, value=str(i.discord_id)),
                Cell(row=3 + k, col=9, value=i.telegram_id),
                Cell(row=3 + k, col=10, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=11, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
                Cell(row=3 + k, col=12, value=i.whoremoved),
                Cell(row=3 + k, col=13, value=i.reason),
                Cell(row=3 + k, col=14, value=i.date),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:N1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:N2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:N{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillremoved_a(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ СНЯТЫХ АДМИНИСТРАТОРОВ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Должность"),
        Cell(row=2, col=4, value="Назначен"),
        Cell(row=2, col=5, value="Имя"),
        Cell(row=2, col=6, value="Возраст"),
        Cell(row=2, col=7, value="Город"),
        Cell(row=2, col=8, value="DISCORD"),
        Cell(row=2, col=9, value="TELEGRAM"),
        Cell(row=2, col=10, value="FORUM"),
        Cell(row=2, col=11, value="VK"),
        Cell(row=2, col=12, value="Снят кем"),
        Cell(row=2, col=13, value="Причина"),
        Cell(row=2, col=14, value="Дата снятия"),
    ]
    k = 0
    for k, i in enumerate(data):
        appointed = (
            formatts(i.appointed)
            + f" ({ceil((time.time() - i.appointed) / 86400)} дней)"
        )
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{len(data) - k}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.role),
                Cell(row=3 + k, col=4, value=appointed),
                Cell(row=3 + k, col=5, value=i.name),
                Cell(row=3 + k, col=6, value=f"{i.age} лет"),
                Cell(row=3 + k, col=7, value=i.city),
                Cell(row=3 + k, col=8, value=str(i.discord_id)),
                Cell(row=3 + k, col=9, value=i.telegram_id),
                Cell(row=3 + k, col=10, value=f'=HYPERLINK("{i.forum}"; "CLICK")'),
                Cell(row=3 + k, col=11, value=f'=HYPERLINK("{i.vk}"; "CLICK")'),
                Cell(row=3 + k, col=12, value=i.whoremoved),
                Cell(row=3 + k, col=13, value=i.reason),
                Cell(row=3 + k, col=14, value=i.date),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:N1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:N2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:N{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillinactives_s(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ НЕАКТИВОВ АГЕНТОВ ПОДДЕРЖКИ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Начало"),
        Cell(row=2, col=4, value="Конец"),
        Cell(row=2, col=5, value="Статус"),
        Cell(row=2, col=6, value="Причина"),
    ]
    k = 0
    for k, i in enumerate(data):
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.start),
                Cell(row=3 + k, col=4, value=i.end),
                Cell(row=3 + k, col=5, value=i.status),
                Cell(row=3 + k, col=6, value=i.reason),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:F1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:F2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:F{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillinactives_l(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ НЕАКТИВОВ ЛИДЕРОВ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Фракция"),
        Cell(row=2, col=4, value="Начало"),
        Cell(row=2, col=5, value="Конец"),
        Cell(row=2, col=6, value="Статус"),
        Cell(row=2, col=7, value="Причина"),
    ]
    k = 0
    for k, i in enumerate(data):
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.fraction),
                Cell(row=3 + k, col=4, value=i.start),
                Cell(row=3 + k, col=5, value=i.end),
                Cell(row=3 + k, col=6, value=i.status),
                Cell(row=3 + k, col=7, value=i.reason),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:G1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:G2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:G{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )


def fillinactives_a(sheet, data):
    if sheet.row_count > 2:
        try:
            sheet.delete_rows(2, sheet.row_count)
        except Exception:
            pass
    update_data = [
        Cell(row=1, col=1, value="УЧЁТ НЕАКТИВОВ АДМИНИСТРАЦИИ"),
        Cell(row=2, col=1, value="ID"),
        Cell(row=2, col=2, value="Nickname"),
        Cell(row=2, col=3, value="Должность"),
        Cell(row=2, col=4, value="Начало"),
        Cell(row=2, col=5, value="Конец"),
        Cell(row=2, col=6, value="Статус"),
        Cell(row=2, col=7, value="Причина"),
    ]
    k = 0
    for k, i in enumerate(data):
        update_data.extend(
            [
                Cell(row=3 + k, col=1, value=f"{k + 1}"),
                Cell(row=3 + k, col=2, value=i.nickname),
                Cell(row=3 + k, col=3, value=i.role),
                Cell(row=3 + k, col=4, value=i.start),
                Cell(row=3 + k, col=5, value=i.end),
                Cell(row=3 + k, col=6, value=i.status),
                Cell(row=3 + k, col=7, value=i.reason),
            ]
        )

    sheet.update_cells(update_data, value_input_option="USER_ENTERED")
    sheet.format(
        "A1:G1",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "bold": True,
            },
        },
    )
    sheet.format(
        "A2:G2",
        {
            "backgroundColor": {"red": 0.57, "green": 0.76, "blue": 0.49},
            "horizontalAlignment": "CENTER",
            "textFormat": {
                "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                "bold": True,
            },
        },
    )
    if len(data) > 0:
        sheet.format(
            f"A3:G{k + 3}",
            {
                "backgroundColor": {"red": 0.84, "green": 0.91, "blue": 0.82},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "bold": True,
                },
            },
        )
