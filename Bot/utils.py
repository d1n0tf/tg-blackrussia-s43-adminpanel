import time
from datetime import datetime
from math import ceil

from config import (
    FRACTIONS,
    LEADERS_ROLES,
    LEADERS_TIME_LEFT,
    ROLES,
    STRUCTURES,
    SUPPORT_ROLES,
)
from db import Chats, Settings_s, SpecialAccesses, Users


def plural_word(value: int, words: tuple | list) -> str:
    """
    :param value: int
    :param words: e.g. ('минута', 'минуты', 'минут')
    :return:
    """
    if value % 10 == 1 and value % 100 != 11:
        return words[0]
    elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
        return words[1]
    else:
        return words[2]


def formatts(timestamp: int | float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


def formatedtotts(formatted: str) -> float:
    return datetime.strptime(formatted, "%d.%m.%Y").timestamp()


def getuserstats(user):
    if user.fraction:
        uid = [
            i.nickname
            for i in sorted(
                Users.select().where(Users.role.is_null(True)),
                key=lambda x: FRACTIONS.index(x.fraction),
            )
        ]
        text = f"""
🌐 <b>Подробная статистика -</b> <a href="tg://user?id={user.telegram_id}">{
            user.nickname
        }</a> <code>(#{uid.index(user.nickname) + 1})</code>

🧑 <b>Ваше имя:</b> <code>{user.name}</code>
☸️ <b>Ваш возраст:</b> <code>{calcage(user.age)} лет</code>
⚛️ <b>Город:</b> <code>{user.city}</code>

📧 <b>Должность:</b> <code>Лидер</code>
🎲 <b>Фракция:</b> <code>{user.fraction}</code>
🕒 <b>Назначен на пост:</b> <code>{formatts(user.appointed)} ({
            ceil((time.time() - user.appointed) / 86400)
        } {
            plural_word(
                ceil((time.time() - user.appointed) / 86400), ("день", "дня", "дней")
            )
        })</code>
⌛ <b>Дней до окончания:</b> <code>{
            LEADERS_TIME_LEFT - ceil((time.time() - user.appointed) / 86400)
        } {
            plural_word(
                LEADERS_TIME_LEFT - ceil((time.time() - user.appointed) / 86400),
                ("день", "дня", "дней"),
            )
        }</code>
💎 <b>Количество баллов:</b> <code>{user.apa} {
            plural_word(user.apa, ("балл", "балла", "баллов"))
        }</code>\n"""

        if user.inactiveend and user.inactiveend > time.time():
            text += (
                f"\n🌑 <b>Действующий неактив:</b> <code>с "
                f"{formatts(user.inactivestart)} по {formatts(user.inactiveend)}\n</code>"
            )

        text += f'''\n
🔗 <b>Discord:</b> <code>{user.discord_id}</code>
🔗 <b>ВКонтакте:</b> <a href="{user.vk}">Кликабельно</a>
🔗 <b>Форум:</b> <a href="{user.forum}">Кликабельно</a>
🔗 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n\n'''
        if user.rebuke:
            text += f"⛔ <b>Количество выговоров:</b> {user.rebuke}\n"
        if user.warn:
            text += f"⛔ <b>Количество предупреждений:</b> {user.warn}\n"
        if user.verbal:
            text += f"⛔ <b>Количество устников:</b> {user.verbal}"
    elif user.role in SUPPORT_ROLES:
        uid = [
            i.nickname
            for i in sorted(
                Users.select().where(Users.role << SUPPORT_ROLES),
                key=lambda x: SUPPORT_ROLES.index(x.role),
            )
        ]
        transferd = Settings_s.get(Settings_s.setting == "transferamnt_d").val - ceil(
            (time.time() - user.appointed) / 86400
        )
        text = f"""
🌐 <b>Подробная статистика -</b> <a href="tg://user?id={user.telegram_id}">{
            user.nickname
        }</a> <code>(#{uid.index(user.nickname) + 1})</code>

🧑 <b>Ваше имя:</b> <code>{user.name}</code>
☸️ <b>Ваш возраст:</b> <code>{calcage(user.age)} лет</code>
⚛️ <b>Город:</b> <code>{user.city}</code>

📧 <b>Должность:</b> <code>{user.role}</code>
🕒 <b>Назначен на пост:</b> <code>{formatts(user.appointed)} ({
            ceil((time.time() - user.appointed) / 86400)
        } {
            plural_word(
                ceil((time.time() - user.appointed) / 86400), ("день", "дня", "дней")
            )
        })</code>
⌛ <b>Дней до перевода:</b> <code>{max(transferd, 0)} {
            plural_word(transferd, ("день", "дня", "дней")) if transferd > 0 else "дней"
        }</code>
💎 <b>Количество асков:</b> <code>{user.apa} {
            plural_word(user.apa, ("аск", "аска", "асков"))
        }</code>\n"""

        if user.inactiveend and user.inactiveend > time.time():
            text += (
                f"\n🌑 <b>Действующий неактив:</b> "
                f"<code>с {formatts(user.inactivestart)} по {formatts(user.inactiveend)}</code>\n"
            )

        text += f'''\n
🔗 <b>Discord:</b> <code>{user.discord_id}</code>
🔗 <b>ВКонтакте:</b> <a href="{user.vk}">Кликабельно</a>
🔗 <b>Форум:</b> <a href="{user.forum}">Кликабельно</a>
🔗 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n\n'''
        if user.rebuke:
            text += f"⛔ <b>Количество выговоров:</b> {user.rebuke}\n"
        if user.warn:
            text += f"⛔ <b>Количество предупреждений:</b> {user.warn}\n"
        if user.verbal:
            text += f"⛔ <b>Количество устников:</b> {user.verbal}"
    else:
        uid = [
            i.nickname
            for i in sorted(
                Users.select().where(Users.role << ROLES),
                key=lambda x: ROLES.index(x.role),
            )
        ]
        lp = (
            (
                f"{formatts(user.promoted)} ({ceil((time.time() - user.promoted) / 86400)} "
                f"{plural_word(ceil((time.time() - user.promoted) / 86400), ('день', 'дня', 'дней'))})"
            )
            if user.promoted
            else "не было"
        )
        text = (
            f"""
🌐 <b>Подробная статистика -</b> <a href="tg://user?id={user.telegram_id}">{
                user.nickname
            }</a> <code>(#{uid.index(user.nickname) + 1})</code>

🧑 <b>Ваше имя:</b> <code>{user.name}</code>
☸️ <b>Ваш возраст:</b> <code>{calcage(user.age)} лет</code>
⚛️ <b>Город:</b> <code>{user.city}</code>

📧 <b>Должность:</b> <code>{user.role}</code>"""
            + (
                f"\n🎲 Структура: <code>{STRUCTURES[user.role]}</code>"
                if user.role in STRUCTURES
                else ""
            )
            + f"""
🕒 <b>Назначен на пост:</b> <code>{formatts(user.appointed)} ({
                ceil((time.time() - user.appointed) / 86400)
            } {
                plural_word(
                    ceil((time.time() - user.appointed) / 86400),
                    ("день", "дня", "дней"),
                )
            })</code>
🕒 <b>Последнее повышение:</b> <code>{lp}</code>
❇️ <b>Дней выполненной нормы:</b> <code>{user.objective_completed} {
                plural_word(user.objective_completed, ("день", "дня", "дней"))
            }</code>
💎 <b>Количество ответов:</b> <code>{user.apa} {
                plural_word(user.apa, ("ответ", "ответа", "ответов"))
            }</code>"""
        )

        if Chats.get_or_none(Chats.setting == "coins"):
            text += f"\n🪙 <b>Количество монеток: <code>{user.coins} штук</code></b>"

        if user.inactiveend and user.inactiveend > time.time():
            text += (
                f"\n🌑 <b>Действующий неактив:</b> <code>с {formatts(user.inactivestart)} по "
                f"{formatts(user.inactiveend)}</code>\n"
            )

        text += f'''\n
🔗 <b>Discord:</b> <code>{user.discord_id}</code>
🔗 <b>ВКонтакте:</b> <a href="{user.vk}">Кликабельно</a>
🔗 <b>Форум:</b> <a href="{user.forum}">Кликабельно</a>
🔗 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n\n'''
        if user.rebuke:
            text += f"⛔ <b>Количество выговоров:</b> {user.rebuke}\n"
        if user.warn:
            text += f"⛔ <b>Количество предупреждений:</b> {user.warn}\n"
        if user.verbal:
            text += f"⛔ <b>Количество устников:</b> {user.verbal}"
    return text


def checkrole(admin: Users, target: Users):
    if admin.role in (
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
        "Куратор администрации",
        "Заместитель КА",
    ):
        return True
    if target.role in SUPPORT_ROLES and (
        admin.role in ("Главный АП", "Куратор агентов поддержки", "Заместитель КАП")
        or SpecialAccesses.get_or_none(
            SpecialAccesses.telegram_id == admin.telegram_id,
            SpecialAccesses.role == "swatcher",
        )
    ):
        return True
    if target.fraction and admin.role in LEADERS_ROLES:
        return True
    return False


def calcage(born):
    born = datetime.utcfromtimestamp(born).date()
    today = datetime.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def calcdateofbirth(born):
    return datetime.utcfromtimestamp(born - 1).date().strftime("%d.%m.%Y")
