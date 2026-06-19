import ast
import asyncio
import random
import re
import string
import time
from datetime import datetime, timedelta
from math import ceil
from typing import List

import gspread
import validators
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram_media_group import media_group_handler

from Bot import keyboard, sheets, states
from Bot.filters import StatesGroupHandle
from Bot.types import CallbackQuery, Message
from Bot.utils import (
    calcage,
    checkrole,
    formatedtotts,
    formatts,
    getuserstats,
    plural_word,
)
from config import (
    ADMIN,
    COINS_SUBBUTTONS,
    FORMSSHEET,
    FORMURL,
    FRACTIONS,
    ROLES,
    SEARCHSHEET,
    SUPPORT_ROLES,
)
from db import (
    Chats,
    CoinsLog,
    CoinsRequests,
    Forms,
    InactiveRequests,
    Inactives,
    Objectives,
    PunishmentsRequests,
    Removed,
    Settings_a,
    Settings_l,
    Settings_s,
    Sheets,
    SpecialAccesses,
    Users,
)

router: Router = Router()


@router.message(Command("id"), F.chat.type == "private")
async def id(message: Message, state: FSMContext):
    await message.delete()
    msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=f"🆔 <b>UserID:</b> <code>{message.from_user.id}</code>",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(CommandStart(), F.chat.type == "private")
async def start(message: Message, state: FSMContext):
    await message.delete()
    user = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not user:
        await message.bot.send_message(
            chat_id=message.chat.id, text="У вас нет доступа к этому боту."
        )
    else:
        isswatcher = (
            SpecialAccesses.get_or_none(
                SpecialAccesses.telegram_id == user.telegram_id,
                SpecialAccesses.role == "swatcher",
            )
            is not None
        )
        text = "Список коротких команд:\n"
        if user.telegram_id in ADMIN:
            text += "/fill - Вручную заполнить таблицы.\n"
        # if user.role == 'Главный администратор':
        #     text += '/zov <TEXT> - Отправит всем администраторам уведомление с указанным текстом.\n'
        #     text += '/send <TEXT> - Отправит всем, кто имеет доступ к боту “АП, Лидеры, Админы”.\n'
        if user.role in (
            "главный администратор",
            "куратор администрации",
            "pаместитель ка",
        ):
            text += "/check <NICK> - Покажет список неактивов пользователя.\n"
        if (
            user.role
            in (
                "Главный администратор",
                "Основной ЗГА",
                "Заместитель ГА",
                "Куратор администрации",
                "Заместитель КА",
                "Главный за лидерами",
                "Куратор организации",
                "Куратор организации",
                "Заместитель КО",
                "Заместитель КО",
                "Главный АП",
                "Куратор агентов поддержки",
                "Заместитель КАП",
            )
            or isswatcher
        ):
            text += "/stats <NICK> - Покажет информацию о пользователе и возможные с ним действия.\n"
        if user.role in ROLES:
            text += "/form - Создать форму.\n"
        if user.role in (
            "Главный за лидерами",
            "Куратор организации",
            "Куратор организации",
            "Заместитель КО",
            "Заместитель КО",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        ):
            text += "/ld - Управление ЛД.\n"
            text += "/addld - Назначить лидера.\n"
            text += "/ball - Управление баллами.\n"
            text += "/ld_p - Наказать лидера.\n"
        if user.role in (
            "Куратор администрации",
            "Заместитель КА",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        ):
            text += "/adm - Управление АДМ.\n"
            text += "/addadm - Назначить администратора.\n"
            text += "/rep - Управление ответами.\n"
            text += "/adm_p - Наказать администратора.\n"
        if (
            user.role
            in (
                "Главный АП",
                "Куратор агентов поддержки",
                "Заместитель КАП",
                "Главный администратор",
                "Основной ЗГА",
                "Заместитель ГА",
            )
            or isswatcher
        ):
            text += "/ap - Управление АП.\n"
            text += "/addap - Назначить агента поддержки.\n"
            text += "/ask - Управление асками.\n"
            text += "/ap_p - Наказать агента поддержки.\n"
        if user.role in ("Главный администратор", "Основной ЗГА", "Заместитель ГА"):
            text += "/sc - Управление сервером.\n"
            text += "/givenorm - Изменить количество дней выполненной нормы.\n"

        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            parse_mode=None,
        )
        await msg.pin()
        coins_chat_exists = Chats.get_or_none(Chats.setting == "coins")
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            text="<b>Добро пожаловать в главное меню.</b>",
            reply_markup=keyboard.panel(
                user.role,
                SpecialAccesses.get_or_none(
                    SpecialAccesses.telegram_id == user.telegram_id,
                    SpecialAccesses.role == "swatcher",
                )
                is not None,
                coins_chat_exists,
            ),
        )
        await state.clear()
        await state.update_data(msg=msg)
    await state.clear()


@router.callback_query(keyboard.Callback.filter(F.type == "back(del)"))
async def back_del(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await state.clear()


@router.callback_query(keyboard.Callback.filter(F.type == "panel"))
async def panel(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user:
        await query.bot.send_message(
            chat_id=query.from_user.id, text="У вас нет доступа к этому боту."
        )
    else:
        coins_chat_exists = Chats.get_or_none(Chats.setting == "coins")
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="<b>Добро пожаловать в главное меню.</b>",
            reply_markup=keyboard.panel(
                user.role,
                SpecialAccesses.get_or_none(
                    SpecialAccesses.telegram_id == user.telegram_id,
                    SpecialAccesses.role == "swatcher",
                )
                is not None,
                coins_chat_exists,
            ),
        )
        await state.clear()
        await state.update_data(msg=msg)


@router.message(Command("fill"), F.chat.type == "private")
async def fill(message: Message, state: FSMContext):  # noqa
    if message.from_user.id not in ADMIN:
        return
    sheets.main(True, True, True)
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.back(),
        text="✅ Обновление запущено.",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("zov", "send"), F.chat.type == "private")
async def zov(message: Message, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not user or user.role.lower() != "главный администратор":
        return
    k = 0
    if "zov" in message.text.split()[0]:
        users = Users.select().where(
            Users.role.not_in(SUPPORT_ROLES), Users.fraction.is_null(True)
        )
        un = ("администратору", "администраторам", "администраторам")
    else:
        users = Users.select()
        un = ("пользователю", "пользователям", "пользователям")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    for i in users:
        try:
            await message.bot.send_message(
                chat_id=i.telegram_id, text=" ".join(message.text.split()[1:])
            )
            k += 1
        except Exception:
            pass
        await asyncio.sleep(0.1)
    await message.delete()
    msg = await message.bot.send_message(
        chat_id=message.chat.id,
        reply_markup=keyboard.back(),
        text=f"✅ Сообщение было доставлено {k} {plural_word(k, un)}.",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("check"), F.chat.type == "private")
async def check(message: Message, state: FSMContext):
    await message.delete()
    user = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not user or user.role not in ROLES[:4]:
        return
    if message.text.strip().split()[-1].isdigit():
        n = "ID"
        user = Users.get_or_none(Users.telegram_id == message.text.strip().split()[-1])
    else:
        n = "ником"
        user = Users.get_or_none(Users.nickname == message.text.strip().split()[-1])
    if not user or not checkrole(
        Users.get_or_none(Users.telegram_id == message.from_user.id), user
    ):
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text=f'⚠️ Пользователя с {n} "<code>{message.text.strip().split()[-1]}</code>'
            f'" не существует.',
        )
        await state.update_data(msg=msg)
        return
    inactives = list(
        Inactives.select()
        .where(Inactives.nickname == user.nickname)
        .order_by(Inactives.id.desc())
    )
    await state.clear()
    await state.update_data(checked_user=user.get_id(), inactives=inactives)
    await _show_check_inactives(
        message.bot, message.from_user.id, user, 0, inactives, state
    )


async def _show_check_inactives(bot, chat_id, user, page, inactives, state):
    text = f'🌐 Список неактивов пользователя - <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n'
    start_idx = page * 25
    end_idx = (page + 1) * 25

    if not inactives:
        text += "\nНет неактивов."
    else:
        for k, i in enumerate(inactives[start_idx:end_idx], start=start_idx + 1):
            text += f"\n[{k}]. <code>{i.start} - {i.end}</code> | {i.status}" + (
                f" | {i.reason}" if i.reason else ""
            )

    msg = await bot.send_message(
        chat_id=chat_id,
        reply_markup=keyboard.checkinactives(page, len(inactives)),
        text=text,
    )
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("checkinactives_")))
async def checkinactives_page(query: CallbackQuery, state: FSMContext):
    page = int(query.data.split(":")[-1].split("_")[1])
    data = await state.get_data()
    user = Users.get_by_id(data["checked_user"])
    inactives = data.get("inactives", [])

    text = f'🌐 Список неактивов пользователя - <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n'
    start_idx = page * 25
    end_idx = (page + 1) * 25

    if not inactives:
        text += "\nНет неактивов."
    else:
        for k, i in enumerate(inactives[start_idx:end_idx], start=start_idx + 1):
            text += f"\n[{k}]. <code>{i.start} - {i.end}</code> | {i.status}" + (
                f" | {i.reason}" if i.reason else ""
            )

    await query.message.edit_text(
        text, reply_markup=keyboard.checkinactives(page, len(inactives))
    )
    await state.update_data(msg=query.message)


@router.message(Command("stats"), F.chat.type == "private")
async def stats(message: Message, state: FSMContext):
    await message.delete()
    admin = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if message.text.strip().split()[-1].isdigit():
        user = Users.get_or_none(
            Users.telegram_id == int(message.text.strip().split()[-1])
        )
    else:
        user = Users.get_or_none(Users.nickname == message.text.strip().split()[-1])
    if not user or not admin or not checkrole(admin, user):
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Пользователя не существует или вы не имеете доступа к этому пользователю.",
        )
        await state.update_data(msg=msg)
        return
    text = getuserstats(user)
    msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=keyboard.stats(
            user.role, user.get_id(), user.fraction, admin.role
        ),
    )
    await state.clear()
    await state.update_data(msg=msg, user=user, admin=admin)


@router.message(Command("givenorm"), F.chat.type == "private")
async def givenorm(message: Message, state: FSMContext):
    await message.delete()
    admin = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not admin or admin.role not in ROLES[:3]:
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Вы не имеете доступа к этой команде.",
        )
        await state.update_data(msg=msg)
        return
    data = message.text.strip().split()
    if (
        len(data) != 3
        or len(data[-1]) < 2
        or data[-1][0] not in ("+", "-")
        or not data[-1][1:].isdigit()
    ):
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Использование: /givenorm NICKNAME +/-DAYS.",
        )
        await state.update_data(msg=msg)
        return
    if data[1].isdigit():
        user = Users.get_or_none(Users.telegram_id == int(data[1]))
    else:
        user = Users.get_or_none(Users.nickname == data[1])
    if not user:
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Пользователя не существует.",
        )
        await state.update_data(msg=msg)
        return
    user.objective_completed += int(data[-1])
    user.save()
    msg = await message.bot.send_message(
        chat_id=message.chat.id,
        reply_markup=keyboard.back(),
        text=f'📗 Вы успешно изменили администратору <a href="tg://user?id={user.telegram_id}">{user.nickname}</a> количество дней нормы на <code>{data[-1]}</code>.',
    )
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📗 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> изменил вам количество выполненного норматива на <code>{data[-1]}</code>.',
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("coins"), F.chat.type == "private")
async def coins_cmd(message: Message, state: FSMContext):
    await message.delete()
    user = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not user or user.role not in (
        "Куратор администрации",
        "Заместитель КА",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.back(),
        text='Введите никнейм администратора(-ов, через запятую или пробел), действие("+" или "-") и количество '
        'монет. Пример: "Andrey_Mal +300"',
    )
    await state.clear()
    await state.set_state(states.Coins.change.state)
    await state.update_data(msg=msg)


@router.message(states.Coins.change)
async def coinschange(message: Message, state: FSMContext):
    await message.delete()

    admin = Users.get_or_none(Users.telegram_id == message.from_user.id)
    stext, fdata = "", message.text.split("\n")
    for c, text in enumerate(fdata):
        data = [i for i in re.split(r"[, \n]", text.strip()) if i != ""]
        splitter = 0
        users = []
        for i in data:
            if i[0] in ("+", "-") or i.isdigit():
                splitter = data.index(i)
                break
            users.append(i)
        if len(data) < 2 or not splitter or not data[splitter][1:].isdigit():
            continue
        nicks = set()
        failed = set()
        reason = (
            ""
            if splitter == (len(data) - 1)
            else f' по причине: "{" ".join(data[splitter + 1 :])}"'
        )
        for i in data[:splitter]:
            user = Users.get_or_none(Users.nickname == i.replace(",", ""))
            if user is None or not checkrole(admin, user):
                stext += (
                    f"{f'[{c + 1}]. ' if len(fdata) > 1 else ''}⚠️ Пользователя с никнеймом {i.replace(',', '')} "
                    f"не существует.\n\n"
                )
                continue
            if user.nickname in nicks:
                continue
            user.coins += int(data[splitter])
            user.save()
            nicks.add(user.nickname)
            try:
                await message.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f'<b>{"📗" if "-" not in data[splitter] else "📕"} <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> '
                    f"{'выдал' if '-' not in data[splitter] else 'снял'} вам <code>{data[splitter]} монет</code>, "
                    f"теперь у вас <code>{user.coins} монет</code>{reason}.</b>",
                )
            except Exception:
                failed.add(user.nickname)
        if nicks:
            stext += (
                f"{f'[{c + 1}]. ' if len(fdata) > 1 else ''} ✅ Вы успешно "
                f"{'выдали' if '-' not in data[splitter] else 'сняли'} <code>{data[splitter]} монет</code> "
                f"<code>{'</code>, <code>'.join(nicks)}</code>{reason}.\n"
            )
            if failed:
                stext += f"⚠️ Не удалось отправить уведомление <code>{'</code>, <code>'.join(failed)}</code>.\n\n"
            else:
                stext += "\n"
    msg = await message.bot.send_message(
        chat_id=message.from_user.id, reply_markup=keyboard.back(), text=stext
    )

    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("search"), F.chat.type == "private")
async def search(message: Message, state: FSMContext):
    await message.delete()
    admin = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if not admin or admin.role not in ROLES[:3]:
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Вы не имеете доступа к этой команде.",
        )
        await state.update_data(msg=msg)
        return
    data = message.text.strip().split()
    if len(data) != 2:
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⚠️ Использование: /search VALUE(nickname or vk or discord id).",
        )
        await state.update_data(msg=msg)
        return
    msg = await message.bot.send_message(
        chat_id=message.chat.id, text="♾️ Идёт поиск..."
    )
    try:
        result = sheets.search(SEARCHSHEET, data[1])
        if result is None:
            raise ValueError
    except (gspread.exceptions.APIError, ValueError):
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            reply_markup=keyboard.back(),
            text="⏳ Попробуйте повторно через минуту.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    text = f'<b>🔍 По результатам поиска "<code>{data[1]}</code>" найдено — <code>{len(result[0]) + len(result[1])}</code> шт.'

    for k, i in enumerate(result):
        for y in i:
            proofs = ", ".join([f"<code>{j}</code>" for j in y[8].split("\n")])
            text += f"""\n\n
➡️ Вид: <code>{"Черный список проекта" if k == 0 else "Черный список администрации"}</code>
➡️ Дата добавления: <code>{y[0]}</code>
➡️ Сервер: <code>{y[1]}</code>
➡️ Занесён by: <code>{y[2]}</code>
↪️ Причина: <code>{y[3]}</code>
↪️ Тип: <code>{y[4]}</code>
1️⃣ ВКонтакте:  <code>{y[5]}</code>
2️⃣ Форум: <code>{y[6]}</code>
3️⃣ Discord: <code>{y[7]}</code>
4️⃣ Доказательства:  {proofs}
{f"5️⃣ Доп. информация:  <code>{y[9]}</code>" if y[9] else ""}"""
    await msg.delete()
    msg = await message.bot.send_message(
        chat_id=message.chat.id, reply_markup=keyboard.back(), text=text + "</b>"
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("removereason_")))
async def removereason_(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text="Введите причину:",
    )
    await state.clear()
    await state.set_state(states.Stats.remove.state)
    await state.update_data(msg=msg, user=int(query.data.split(":")[-1].split("_")[-1]))


@router.callback_query(keyboard.Callback.filter(F.type == "swatchers"))
async def swatchers(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.swatchers(),
        text="Управление следящими за АП",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.in_(("addswatcher", "remswatcher")))
)
async def addremswatcher(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text="Введите никнейм:"
    )
    await state.clear()
    if "rem" in query.data:
        await state.set_state(states.Swatchers.rem.state)
    else:
        await state.set_state(states.Swatchers.add.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "listswatcher"))
async def listswatcher(query: CallbackQuery, state: FSMContext):
    swatchers = SpecialAccesses.select().where(SpecialAccesses.role == "swatcher")
    text = f"❇️ Список пользователей с доступом к управлению АП - {len(swatchers)}\n\n"
    for k, i in enumerate(swatchers):
        if not (user := Users.get_or_none(Users.telegram_id == i.telegram_id)):
            continue
        text += f'[{k + 1}]. <a href="tg://user?id={user.telegram_id}">{user.nickname}</a> | <code>{user.role}</code>\n'
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, reply_markup=keyboard.back(), text=text
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(states.Swatchers.add)
async def swatchersadd(message: Message, state: FSMContext):
    await message.delete()
    if not (user := Users.get_or_none(Users.nickname == message.text.strip())):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            reply_markup=keyboard.back(),
            text="⚠️ Пользователя нет в списке следящих за АП.\nВведите никнейм:",
        )
        await state.update_data(msg=msg)
        return
    SpecialAccesses.create(telegram_id=user.telegram_id, role="swatcher")
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f'✅ Вы успешно дали доступ пользователю <a href="tg://user?id={user.telegram_id}">{user.nickname}</a> '
        f"к управлению АП.",
    )
    await state.clear()
    await state.update_data(msg=msg, nickname=message.text.strip())


@router.message(states.Swatchers.rem)
async def swatchersrem(message: Message, state: FSMContext):
    await message.delete()
    user = Users.get_or_none(Users.nickname == message.text.strip())
    if not user or not (
        suser := SpecialAccesses.get_or_none(
            SpecialAccesses.telegram_id == user.telegram_id
        )
    ):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            reply_markup=keyboard.back(),
            text="⚠️ Пользователя нет в списке следящих за АП.\nВведите никнейм:",
        )
        await state.update_data(msg=msg)
        return
    suser.delete_instance()
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.back(),
        text=f'✅ Вы успешно убрали права пользователя <a href="tg://user?id={user.telegram_id}">{user.nickname}</a> '
        f"к управлению АП.",
    )
    await state.clear()
    await state.update_data(msg=msg, nickname=message.text.strip())


@router.callback_query(keyboard.Callback.filter(F.type.startswith("transfer_")))
async def transfer_(query: CallbackQuery, state: FSMContext):
    user = Users.get_by_id(int(query.data.split(":")[-1].split("_")[-1]))
    if not (
        Settings_s.get(Settings_s.setting == "transferamnt_d").val
        <= ceil((time.time() - user.appointed) / 86400)
        and Settings_s.get(Settings_s.setting == "transferamnt_a").val <= user.apa
    ):
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.back(),
            text="Данный агент поддержки не подходит под минимальные требования перевода.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    user.role = "Кандидат"
    user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text=f'✅ Вы успешно установили должность "<code>Кандидат</code>" для агента поддержки '
        f'<a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type == "mystats"))
async def mystats(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    text = getuserstats(user)
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, reply_markup=keyboard.back(), text=text
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "myinactives"))
async def myinactives(query: CallbackQuery, state: FSMContext):
    await query.answer()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление неактивами:",
        reply_markup=keyboard.myinactives(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "takeinactive"))
async def takeinactive(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите дату неактива (формат: "15.12.2024 - 18.12.2024"):',
        reply_markup=keyboard.back(),
    )
    await state.clear()
    await state.set_state(states.Inactives.take.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "cancelinactive"))
async def cancelinactive(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or not user.inactiveend or user.inactiveend < time.time():
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.back(),
            text="⚠️ У вас нет активного неактива.",
        )
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Вы уверены, что хотите снять неактив?",
        reply_markup=keyboard.cancelinactive(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "cancelinactive_y"))
async def cancelinactive_y(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    user.inactivestart = None
    user.inactiveend = None
    user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text="Вы успешно сняли текущий неактив.",
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type == "inactive_take_y"))
async def inactive_take_y(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text="Введите причину:",
    )
    await state.set_state(states.Inactives.reason.state)
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(
        F.type.in_(("cancelinactive_n", "inactive_take_n", "usersinactiveset_n"))
    )
)
async def nobuttons(query: CallbackQuery, state: FSMContext):  # noqa
    await state.clear()


@router.callback_query(keyboard.Callback.filter(F.type == "listinactive"))
async def listinactive(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    inactives = list(
        Inactives.select()
        .where(Inactives.nickname == user.nickname)
        .order_by(Inactives.id.desc())
    )
    await state.clear()
    await state.update_data(inactives=inactives)
    await _show_user_inactives(query.bot, query.from_user.id, user, 0, inactives, state)


async def _show_user_inactives(bot, chat_id, user, page, inactives, state):
    text = f'🌐 Список неактивов пользователя - <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n'
    start_idx = page * 25
    end_idx = (page + 1) * 25

    if not inactives:
        text += "\nНет неактивов."
    else:
        for k, i in enumerate(inactives[start_idx:end_idx], start=start_idx + 1):
            text += f"\n[{k}]. <code>{i.start} - {i.end}</code> | {i.status}" + (
                f" | {i.reason}" if i.reason else ""
            )

    msg = await bot.send_message(
        chat_id=chat_id,
        reply_markup=keyboard.listinactives(page, len(inactives)),
        text=text,
    )
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("listinactives_")))
async def listinactives_page(query: CallbackQuery, state: FSMContext):
    page = int(query.data.split(":")[-1].split("_")[1])
    data = await state.get_data()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    inactives = data.get("inactives", [])

    text = f'🌐 Список неактивов пользователя - <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n'
    start_idx = page * 25
    end_idx = (page + 1) * 25

    if not inactives:
        text += "\nНет неактивов."
    else:
        for k, i in enumerate(inactives[start_idx:end_idx], start=start_idx + 1):
            text += f"\n[{k}]. <code>{i.start} - {i.end}</code> | {i.status}" + (
                f" | {i.reason}" if i.reason else ""
            )

    await query.message.edit_text(
        text, reply_markup=keyboard.listinactives(page, len(inactives))
    )
    await state.update_data(msg=query.message)


@router.callback_query(keyboard.Callback.filter(F.type == "reports"))
async def reports(query: CallbackQuery, state: FSMContext):
    await query.answer()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление отчётами:",
        reply_markup=keyboard.reports(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("ld"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "leaderscontrol"))
async def leaderscontrol(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Главный за лидерами",
        "Куратор организации",
        "Куратор организации",
        "Заместитель КО",
        "Заместитель КО",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление ЛД:",
        reply_markup=keyboard.leaderscontrol(await state.get_value("from_sc", False)),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("adm"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "adminscontrol"))
async def adminscontrol(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Куратор администрации",
        "Заместитель КА",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return

    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление АДМ:",
        reply_markup=keyboard.adminscontrol(await state.get_value("from_sc", False)),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "sendobjective"))
async def sendobjective(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text='Отправьте скриншот из "<code>/astats</code>":',
    )
    await state.clear()
    await state.set_state(states.Reports.sendobjective.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "sendadditionalreply"))
async def sendadditionalreply(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text="Отправьте скриншоты:"
    )
    await state.clear()
    await state.set_state(states.Reports.sendadditionalreply.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "forms"))
async def forms(query: CallbackQuery, state: FSMContext):
    await query.answer()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление формами:",
        reply_markup=keyboard.forms(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("form"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "createform"))
async def createform(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in ROLES:
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text='Введите форму(пример "/permban Test test"):',
    )
    await state.clear()
    await state.set_state(states.Forms.create.state)
    await state.update_data(msg=msg)


@router.message(Command("ap"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "supportcontrol"))
async def supportcontrol(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or (
        user.role
        not in (
            "Главный АП",
            "Куратор агентов поддержки",
            "Заместитель КАП",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        )
        and not SpecialAccesses.get_or_none(
            SpecialAccesses.role == "swatcher",
            SpecialAccesses.telegram_id == query.from_user.id,
        )
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление АП:",
        reply_markup=keyboard.supportcontrol(await state.get_value("from_sc", False)),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.contains("supportlist_")))
async def supportlist(query: CallbackQuery, state: FSMContext):
    page = int(query.data.split(":")[-1].split("_")[1])
    sup = sorted(
        Users.select().where(Users.role == SUPPORT_ROLES[1]), key=lambda x: x.appointed
    ) + sorted(
        Users.select().where(Users.role == SUPPORT_ROLES[0]), key=lambda x: x.appointed
    )
    text = f"📚 Список агентов поддержки - {len(sup)} {plural_word(len(sup), ('человек', 'человека', 'человек'))}.\n\n"
    for k, i in enumerate(sup[page * 15 : (page + 1) * 15]):
        i: Users
        text += (
            f'[{(15 * page) + 1 + k}]. <a href="tg://user?id={i.telegram_id}">{i.nickname}</a> | '
            f'<a href="{i.vk}">VK</a> | '
            f'{i.telegram_id} | <a href="{i.forum}">FA</a> | '
            f"<code>{i.role}</code>\n"
        )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=text,
        reply_markup=keyboard.supportlist(page, len(sup)),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("addap"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "appoint"))
async def appoint(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or (
        user.role
        not in (
            "Главный АП",
            "Куратор агентов поддержки",
            "Заместитель КАП",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        )
        and not SpecialAccesses.get_or_none(
            SpecialAccesses.role == "swatcher",
            SpecialAccesses.telegram_id == query.from_user.id,
        )
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text="Введите никнейм:",
    )
    await state.clear()
    await state.set_state(states.Appoint.s.state)
    await state.update_data(msg=msg)


@router.message(states.Appoint.s)
async def appoints(message: Message, state: FSMContext):
    await message.delete()
    if "_" not in message.text or " " in message.text:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text="⚠️ Неверный никнейм.\nВведите никнейм:"
        )
        await state.update_data(msg=msg)
        return
    code = "".join(
        [random.choice(string.ascii_letters + string.digits) for _ in range(8)]
    )
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.appointcheck(),
        text=f'Заполните <a href="{FORMURL}">форму</a>.\nПроверочный код: <code>{code}</code>',
    )
    await state.clear()
    await state.update_data(msg=msg, code=code, nickname=message.text)


@router.callback_query(keyboard.Callback.filter(F.type == "appointcheck"))
async def appointcheck(query: CallbackQuery, state: FSMContext):
    await query.bot.send_chat_action(chat_id=query.from_user.id, action="typing")
    sdata = sheets.getappointformbycode(
        FORMSSHEET,
        (await state.get_data())["code"],
        (await state.get_data())["nickname"],
    )
    if sdata is None:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.appointcheck(),
            text=f'⚠️ Форма не найдена.\nЗаполните <a href="{FORMURL}">форму</a>.\nПроверочный код: '
            f"<code>{(await state.get_data())['code']}</code>",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get_or_create(
        telegram_id=int(sdata[7]),
        defaults={
            "nickname": sdata[0],
            "role": SUPPORT_ROLES[0],
            "fraction": None,
            "appointed": int(time.time()),
            "promoted": None,
            "objective_completed": 0,
            "apa": 0,
            "rebuke": 0,
            "warn": 0,
            "verbal": 0,
            "inactivestart": None,
            "inactiveend": None,
            "name": sdata[1],
            "age": datetime.strptime(sdata[2], "%d.%m.%Y").timestamp(),
            "city": sdata[3],
            "discord_id": int(sdata[4]),
            "telegram_id": int(sdata[7]),   
            "forum": sdata[6],
            "vk": sdata[5],
        },
    )
    if user[1]:
        user = user[0]
        user.nickname = sdata[0]
        user.role = SUPPORT_ROLES[0]
        user.fraction = user.promoted = user.inactivestart = user.inactiveend = None
        user.appointed = int(time.time())
        user.objective_completed = user.apa = user.rebuke = user.warn = user.verbal = 0
        user.name = sdata[1]
        user.age = datetime.strptime(sdata[2], "%d.%m.%Y").timestamp()
        user.city = sdata[3]
        user.discord_id = int(sdata[4])
        user.telegram_id = int(sdata[7])
        user.forum = sdata[6]
        user.vk = sdata[5]
        user.save()
    else:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="❌ Пользователь с таким Telegram ID уже существует.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'✅ Вы успешно назначили нового агента поддержки - <a href="tg://user?id={user.telegram_id}">'
        f"{user.nickname}</a>",
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.message(Command("addld"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "appointleader"))
async def appointleader(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Главный за лидерами",
        "Куратор организации",
        "Куратор организации",
        "Заместитель КО",
        "Заместитель КО",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите никнейм:",
    )
    await state.set_state(states.Appoint.L.state)
    await state.update_data(msg=msg)


@router.message(states.Appoint.L)
async def appointl(message: Message, state: FSMContext):
    await message.delete()
    if "_" not in message.text or " " in message.text:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text="⚠️ Неверный никнейм.\nВведите никнейм:"
        )
        await state.update_data(msg=msg)
        return
    fracs = list(FRACTIONS)
    for i in Users.select().where(Users.fraction.is_null(False)):
        fracs.remove(i.fraction)
    if len(fracs) == 0:
        msg = await message.bot.send_message(
            chat_id=message.chat.id, text="❌ Сейчас нет свободных фракций."
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.appointl(fracs),
        text="Выберите одну из доступных фракций:",
    )
    await state.clear()
    await state.update_data(msg=msg, nickname=message.text.strip())


@router.callback_query(keyboard.Callback.filter(F.type.startswith("appointl_")))
async def appointl_(query: CallbackQuery, state: FSMContext):
    code = "".join(
        [random.choice(string.ascii_letters + string.digits) for _ in range(8)]
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.appointleadercheck(),
        text=f'Заполните <a href="{FORMURL}">форму</a>\nПроверочный код: <code>{code}</code>',
    )
    await state.update_data(
        msg=msg, code=code, fraction=int(query.data.split(":")[-1].split("_")[-1])
    )


@router.callback_query(keyboard.Callback.filter(F.type == "appointleadercheck"))
async def appointleadercheck(query: CallbackQuery, state: FSMContext):
    await query.bot.send_chat_action(chat_id=query.from_user.id, action="typing")
    sdata = sheets.getappointformbycode(
        FORMSSHEET,
        (await state.get_data())["code"],
        (await state.get_data())["nickname"],
    )
    if sdata is None:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.appointcheck(),
            text=f'⚠️ Форма не найдена.\nЗаполните <a href="{FORMURL}">форму</a>.\nПроверочный код: '
            f"<code>{(await state.get_data())['code']}</code>",
        )
        await state.update_data(msg=msg)
        return

    user = Users.get_or_create(
        telegram_id=int(sdata[7]),
        defaults={
            "nickname": sdata[0],
            "role": None,
            "fraction": FRACTIONS[(await state.get_data())["fraction"]],
            "appointed": int(time.time()),
            "promoted": None,
            "objective_completed": 0,
            "apa": 0,
            "rebuke": 0,
            "warn": 0,
            "verbal": 0,
            "inactivestart": None,
            "inactiveend": None,
            "name": sdata[1],
            "age": datetime.strptime(sdata[2], "%d.%m.%Y").timestamp(),
            "city": sdata[3],
            "discord_id": int(sdata[4]),
            "forum": sdata[6],
            "vk": sdata[5],
        },
    )
    if user[1]:
        user = user[0]
        user.nickname = sdata[0]
        user.role = user.promoted = user.inactivestart = user.inactiveend = None
        user.fraction = FRACTIONS[(await state.get_data())["fraction"]]
        user.appointed = int(time.time())
        user.objective_completed = user.apa = user.rebuke = user.warn = user.verbal = 0
        user.name = sdata[1]
        user.age = datetime.strptime(sdata[2], "%d.%m.%Y").timestamp()
        user.city = sdata[3]
        user.discord_id = int(sdata[4])
        user.forum = sdata[6]
        user.vk = sdata[5]
        user.save()
    else:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="❌ Пользователь с таким Telegram ID уже существует.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'✅ Вы успешно назначили нового лидера фракции "<code>{user.fraction}</code>" - '
        f'<a href="tg://user?id={user.telegram_id}">{user.nickname}</a>',
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.message(Command("addadm"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "appoint_a"))
async def appoint_a(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Куратор администрации",
        "Заместитель КА",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите никнейм:",
    )
    await state.set_state(states.Appoint.a.state)
    await state.update_data(msg=msg)


@router.message(states.Appoint.a)
async def appointa(message: Message, state: FSMContext):
    await message.delete()
    if "_" not in message.text or " " in message.text:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text="⚠️ Неверный никнейм.\nВведите никнейм:"
        )
        await state.update_data(msg=msg)
        return
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.appointa(ROLES.index(i) for i in ROLES),
        text="Выберите одну из должностей:",
    )
    await state.clear()
    await state.update_data(msg=msg, nickname=message.text.strip())


@router.callback_query(keyboard.Callback.filter(F.type.startswith("appoint_a_")))
async def appoint_a_(query: CallbackQuery, state: FSMContext):
    code = "".join(
        [random.choice(string.ascii_letters + string.digits) for _ in range(8)]
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.appoint_acheck(),
        text=f'Заполните <a href="{FORMURL}">форму</a>.\n'
        f"Проверочный код: <code>{code}</code>",
    )
    await state.update_data(
        msg=msg, code=code, role=int(query.data.split(":")[-1].split("_")[-1])
    )


@router.callback_query(keyboard.Callback.filter(F.type == "appoint_acheck"))
async def appoint_acheck(query: CallbackQuery, state: FSMContext):
    await query.bot.send_chat_action(chat_id=query.from_user.id, action="typing")
    sdata = sheets.getappointformbycode(
        FORMSSHEET,
        (await state.get_data())["code"],
        (await state.get_data())["nickname"],
    )
    if sdata is None:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.appointcheck(),
            text=f'⚠️ Форма не найдена.\nЗаполните <a href="{FORMURL}">форму</a>.\nПроверочный код: '
            f"<code>{(await state.get_data())['code']}</code>",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get_or_create(
        telegram_id=int(sdata[7]),
        defaults={
            "nickname": sdata[0],
            "role": ROLES[(await state.get_data())["role"]],
            "fraction": None,
            "appointed": int(time.time()),
            "promoted": None,
            "objective_completed": 0,
            "apa": 0,
            "rebuke": 0,
            "warn": 0,
            "verbal": 0,
            "inactivestart": None,
            "inactiveend": None,
            "name": sdata[1],
            "age": datetime.strptime(sdata[2], "%d.%m.%Y").timestamp(),
            "city": sdata[3],
            "discord_id": int(sdata[4]),
            "forum": sdata[6],
            "vk": sdata[5],
        },
    )
    if user[1]:
        user = user[0]
        user.nickname = sdata[0]
        user.role = ROLES[(await state.get_data())["role"]]
        user.fraction = user.promoted = user.inactivestart = user.inactiveend = None
        user.appointed = int(time.time())
        user.objective_completed = user.apa = user.rebuke = user.warn = user.verbal = 0
        user.name = sdata[1]
        user.age = datetime.strptime(sdata[2], "%d.%m.%Y").timestamp()
        user.city = sdata[3]
        user.discord_id = int(sdata[4])
        user.forum = sdata[6]
        user.vk = sdata[5]
        user.save()
    else:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="❌ Пользователь с таким Telegram ID уже существует.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'✅ Вы успешно назначили нового пользователя на должность "<code>{user.role}</code>" - '
        f'<a href="tg://user?id={user.telegram_id}">{user.nickname}</a>',
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type == "updateinfo"))
async def updateinfo(query: CallbackQuery, state: FSMContext):
    code = "".join(
        [random.choice(string.ascii_letters + string.digits) for _ in range(8)]
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.updateinfo_check(),
        text=f'Заполните <a href="{FORMURL}">форму</a>.\n'
        f"Проверочный код: <code>{code}</code>",
    )
    await state.clear()
    await state.update_data(msg=msg, code=code)


@router.callback_query(keyboard.Callback.filter(F.type == "updateinfo_check"))
async def updateinfo_check(query: CallbackQuery, state: FSMContext):
    await query.bot.send_chat_action(chat_id=query.from_user.id, action="typing")
    sdata = sheets.getappointformbycode(
        FORMSSHEET, (await state.get_data())["code"], None
    )
    if sdata is None:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            reply_markup=keyboard.updateinfo_check(),
            text=f'⚠️ Форма не найдена.\nЗаполните <a href="{FORMURL}">форму</a>.\nПроверочный код: '
            f"<code>{(await state.get_data())['code']}</code>",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == int(sdata[7]))
    user.nickname = sdata[0]
    user.name = sdata[1]
    user.age = datetime.strptime(sdata[2], "%d.%m.%Y").timestamp()
    user.city = sdata[3]
    user.discord_id = int(sdata[4])
    user.telegram_id = int(sdata[7])
    user.forum = sdata[6]
    user.vk = sdata[5]
    user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"✅ Вы успешно обновили информацию пользователя "
        f'<a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.message(Command("ap_p"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "punishments"))
async def punishments(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or (
        user.role
        not in (
            "Главный АП",
            "Куратор агентов поддержки",
            "Заместитель КАП",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        )
        and not SpecialAccesses.get_or_none(
            SpecialAccesses.role == "swatcher",
            SpecialAccesses.telegram_id == query.from_user.id,
        )
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Выберите тип наказания:",
        reply_markup=keyboard.punishments(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(
        F.type.in_(("punishments_v", "punishments_w", "punishments_r"))
    )
)
async def punishments_(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text='Введите никнейм агента поддержки, действие("+" чтобы выдать или "-" чтобы снять) и причину. '
        'Пример: "Andrey_Mal + Тест"',
    )
    await state.clear()
    if query.data.split(":")[-1] == "punishments_v":
        await state.set_state(states.Punishments.v.state)
    elif query.data.split(":")[-1] == "punishments_w":
        await state.set_state(states.Punishments.w.state)
    elif query.data.split(":")[-1] == "punishments_r":
        await state.set_state(states.Punishments.r.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "inactives_s"))
async def inactives_s(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление неактивами:",
        reply_markup=keyboard.inactives_s(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.in_(("setinactive_s", "removeinactive_s")))
)
async def setrminactive_s(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите никнейм агента поддержки, дату начала и дату окончания. Пример: "Andrey_Mal 15.12.2024 '
        '20.12.2024"'
        if query.data.split(":")[-1] == "setinactive_s"
        else "Введите никнейм агента поддержки.",
    )
    await state.clear()
    if query.data.split(":")[-1] == "setinactive_s":
        await state.set_state(states.UsersInactive.set.state)
    elif query.data.split(":")[-1] == "removeinactive_s":
        await state.set_state(states.UsersInactive.remove.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "listinactive_s"))
async def listinactive_s(query: CallbackQuery, state: FSMContext):
    sup = sorted(
        Users.select().where(
            Users.role == SUPPORT_ROLES[1],
            Users.inactiveend.is_null(False),
            Users.inactiveend > int(time.time()),
        ),
        key=lambda x: x.appointed,
    ) + sorted(
        Users.select().where(
            Users.role == SUPPORT_ROLES[0],
            Users.inactiveend.is_null(False),
            Users.inactiveend > int(time.time()),
        ),
        key=lambda x: x.appointed,
    )
    text = f"📚 Список агентов поддержки в неактиве - {len(sup)}\n\n"
    for k, i in enumerate(sup):
        text += (
            f'[{k + 1}]. <a href="tg://user?id={i.telegram_id}">{i.nickname}</a> '
            f"| <code>{formatts(i.inactivestart)} - {formatts(i.inactiveend)}</code>\n"
        )
    msg = await query.bot.send_message(chat_id=query.from_user.id, text=text)
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "settings_s"))
async def settings_s(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Настройки АП:",
        reply_markup=keyboard.settings_s(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "setinactiveamnt_s"))
async def setinactiveamnt_s(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите количество асков, которые будут сниматься за день неактива:",
    )
    await state.clear()
    await state.set_state(states.Settings.setinactiveamnt_asks.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "settransferamnt"))
async def settransferamnt(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.settransferamnt(),
        text="Настройки перевода:",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.in_(("settransferdays", "settransferasks")))
)
async def settransferda(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите минимальный срок службы для перевода в администрацию:"
        if query.data.split(":")[-1] == "settransferdays"
        else "Введите минимальное количество асков для перевода в администрацию:",
    )
    await state.clear()
    if query.data.split(":")[-1] == "settransferdays":
        await state.set_state(states.Settings.settransferamnt_d.state)
    elif query.data.split(":")[-1] == "settransferasks":
        await state.set_state(states.Settings.settransferamnt_a.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "leaderslist"))
async def leaderslist(query: CallbackQuery, state: FSMContext):
    leaders = sorted(
        Users.select().where(Users.role.is_null(True)),
        key=lambda x: FRACTIONS.index(x.fraction),
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.leaderslist(leaders),
        text="Выберите лидера:",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("leaderstats_")))
async def leaderstats(query: CallbackQuery, state: FSMContext):
    leader = "_".join(query.data.split(":")[-1].split("_")[-2:])
    user = Users.get_or_none(Users.nickname == leader)
    if not user:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id, text="⚠️ Данного пользователя не существует."
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.leaderstats_remove(leader),
        text=getuserstats(user),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("removeleader_")))
async def removeleader(query: CallbackQuery, state: FSMContext):
    leader = Users.get_or_none(
        Users.nickname == "_".join(query.data.split(":")[-1].split("_")[-2:])
    )
    if not leader:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id, text="⚠️ Данного пользователя не существует."
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text="Введите причину снятия:"
    )
    await state.clear()
    await state.set_state(states.RemoveLeader.reason.state)
    await state.update_data(msg=msg, leader=leader.nickname)


@router.message(states.RemoveLeader.reason)
async def removeleader_reason(message: Message, state: FSMContext):
    await message.delete()
    leader = (await state.get_data())["leader"]
    if not leader:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text="⚠️ Данного пользователя не существует."
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    user = Users.get_or_none(Users.nickname == leader)
    Removed.create(
        nickname=user.nickname,
        role=user.role,
        appointed=user.appointed,
        name=user.name,
        age=calcage(user.age),
        city=user.city,
        discord_id=user.discord_id,
        telegram_id=user.telegram_id,
        reason=message.text,
        forum=user.forum,
        vk=user.vk,
        whoremoved=Users.get(Users.telegram_id == message.from_user.id).nickname,
        date=formatts(time.time()),
        fraction=user.fraction,
        struct="l",
    ).save()
    user.delete_instance()
    Inactives.delete().where(Inactives.nickname == leader).execute()
    msg = await message.bot.send_message(
        chat_id=message.from_user.id, text="✅ Вы успешно сняли лидера с должности."
    )
    try:
        admin = Users.get(Users.telegram_id == message.from_user.id)
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> снял вас с '
            f"должности.",
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True, inactives=True, removed=True)


@router.callback_query(keyboard.Callback.filter(F.type == "inactives_l"))
async def inactives_l(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление неактивами:",
        reply_markup=keyboard.inactives_l(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.in_(("setinactive_l", "removeinactive_l")))
)
async def setrminactive_l(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите никнейм лидера, дату начала и дату окончания. Пример: "Andrey_Mal 15.12.2024 '
        '20.12.2024"'
        if query.data.split(":")[-1] == "setinactive_l"
        else "Введите никнейм лидера.",
    )
    await state.clear()
    if query.data.split(":")[-1] == "setinactive_l":
        await state.set_state(states.UsersInactive.set.state)
    elif query.data.split(":")[-1] == "removeinactive_l":
        await state.set_state(states.UsersInactive.remove.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "listinactive_l"))
async def listinactive_l(query: CallbackQuery, state: FSMContext):
    leaders = Users.select().where(
        Users.fraction.is_null(False),
        Users.inactiveend.is_null(False),
        Users.inactiveend > int(time.time()),
    )
    text = f"📚 Список лидеров в неактиве - {len(leaders)}\n\n"
    for k, i in enumerate(leaders):
        text += (
            f'[{k + 1}]. <a href="tg://user?id={i.telegram_id}">{i.nickname}</a> | '
            f"<code>{formatts(i.inactivestart)} - {formatts(i.inactiveend)}</code>\n"
        )
    msg = await query.bot.send_message(chat_id=query.from_user.id, text=text)
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("ball"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "points"))
async def points(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Главный за лидерами",
        "Куратор организации",
        "Куратор организации",
        "Заместитель КО",
        "Заместитель КО",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text='Введите никнейм лидера(-ов, через запятую или пробел), действие("+" или "-") и количество баллов. '
        'Пример: "Andrey_Mal +300"',
    )
    await state.clear()
    await state.set_state(states.APA.change.state)
    await state.update_data(msg=msg)


@router.message(Command("ask"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "asks"))
async def asks(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or (
        user.role
        not in (
            "Главный АП",
            "Куратор агентов поддержки",
            "Заместитель КАП",
            "Главный администратор",
            "Основной ЗГА",
            "Заместитель ГА",
        )
        and not SpecialAccesses.get_or_none(
            SpecialAccesses.role == "swatcher",
            SpecialAccesses.telegram_id == query.from_user.id,
        )
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text="Введите никнейм агента(-ов, через запятую или пробел) поддержки, "
        'действие("+" или "-") и количество асков. Пример: "Andrey_Mal +300"',
    )
    await state.clear()
    await state.set_state(states.APA.change.state)
    await state.update_data(msg=msg)


@router.message(Command("adm_p"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "punishments_a"))
async def punishments_a(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Куратор администрации",
        "Заместитель КА",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Выберите тип наказания:",
        reply_markup=keyboard.punishments_a(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(
        F.type.in_(("punishments_a_v", "punishments_a_w", "punishments_a_r"))
    )
)
async def punishments_a_(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите никнейм администратора, действие("+" чтобы выдать или "-" чтобы снять) и причину. '
        'Пример: "Andrey_Mal + Тест"',
    )
    await state.clear()
    if query.data.split(":")[-1] == "punishments_a_v":
        await state.set_state(states.Punishments.v.state)
    elif query.data.split(":")[-1] == "punishments_a_w":
        await state.set_state(states.Punishments.w.state)
    elif query.data.split(":")[-1] == "punishments_a_r":
        await state.set_state(states.Punishments.r.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.message(Command("ld_p"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "punishments_l"))
async def punishments_l(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Главный за лидерами",
        "Куратор организации",
        "Заместитель КО",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Выберите тип наказания:",
        reply_markup=keyboard.punishments_l(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(
        F.type.in_(("punishments_l_v", "punishments_l_w", "punishments_l_r"))
    )
)
async def punishments_l_(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите никнейм администратора, действие("+" чтобы выдать или "-" чтобы снять) и причину. '
        'Пример: "Andrey_Mal + Тест"',
    )
    await state.clear()
    if query.data.split(":")[-1] == "punishments_l_v":
        await state.set_state(states.Punishments.v.state)
    elif query.data.split(":")[-1] == "punishments_l_w":
        await state.set_state(states.Punishments.w.state)
    elif query.data.split(":")[-1] == "punishments_l_r":
        await state.set_state(states.Punishments.r.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "settings_l"))
async def settings_l(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Настройки фракций:",
        reply_markup=keyboard.settings_l(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "setinactiveamnt_l"))
async def setinactiveamnt_l(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите количество баллов, которые будут сниматься за день неактива:",
    )
    await state.clear()
    await state.set_state(states.Settings.setinactiveamnt_points.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "administration"))
async def administration(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.administration(),
        text="Управление администрацией:",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.contains("administration_list_"))
)
async def administration_list(query: CallbackQuery, state: FSMContext):
    page = int(query.data.split(":")[-1].split("_")[2])
    admins = sorted(
        Users.select().where(Users.role << ROLES), key=lambda x: ROLES.index(x.role)
    )
    text = (
        f"📚 Список администраторов - {len(admins)} {plural_word(len(admins), ('человек', 'человека', 'человек'))}."
        f"\n\n"
    )
    for k, i in enumerate(admins[page * 15 : (page + 1) * 15]):
        text += (
            f'[{(15 * page) + k + 1}]. <a href="tg://user?id={i.telegram_id}">{i.nickname}</a> |'
            f' <a href="{i.vk}">VK</a> | '
            f'{i.telegram_id} | <a href="{i.forum}">FA</a> | '
            f"<code>{i.role}</code>\n"
        )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=text,
        reply_markup=keyboard.administration_list(page, len(admins)),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "promote"))
async def promote(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите никнейм администратора:",
    )
    await state.clear()
    await state.set_state(states.Promote.promote.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "inactives_a"))
async def inactives_a(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Управление неактивами:",
        reply_markup=keyboard.inactives_a(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.in_(("setinactive_a", "removeinactive_a")))
)
async def setrminactive_a(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text='Введите никнейм администратора, дату начала и дату окончания. Пример: "Andrey_Mal 15.12.2024 '
        '20.12.2024"'
        if query.data.split(":")[-1] == "setinactive_a"
        else "Введите никнейм администратора.",
    )
    await state.clear()
    if query.data.split(":")[-1] == "setinactive_a":
        await state.set_state(states.UsersInactive.set.state)
    elif query.data.split(":")[-1] == "removeinactive_a":
        await state.set_state(states.UsersInactive.remove.state)
    else:
        raise TypeError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "listinactive_a"))
async def listinactive_a(query: CallbackQuery, state: FSMContext):
    admins = sorted(
        Users.select().where(
            Users.role << ROLES,
            Users.inactiveend.is_null(False),
            Users.inactiveend > int(time.time()),
        ),
        key=lambda x: ROLES.index(x.role),
    )
    text = f"📚 Список администраторов в неактиве - {len(admins)}\n\n"
    for k, i in enumerate(admins):
        text += (
            f'[{k + 1}]. <a href="tg://user?id={i.telegram_id}">{i.nickname}</a> |'
            f" <code>{formatts(i.inactivestart)} - {formatts(i.inactiveend)}</code>\n"
        )
    msg = await query.bot.send_message(chat_id=query.from_user.id, text=text)
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("rep"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "answers"))
async def answers(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Куратор администрации",
        "Заместитель КА",
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.back(),
        text='Введите никнейм администратора(-ов, через запятую или пробел), действие("+" или "-") и количество '
        'ответов. Пример: "Andrey_Mal +300"',
    )
    await state.clear()
    await state.set_state(states.APA.change.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "structurescontrol"))
async def structurescontrol(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.structurescontrol(),
        text="Управление структурами",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "strctrstats"))
async def strctrstats(query: CallbackQuery, state: FSMContext):
    users = Users.select()
    fractions = list(FRACTIONS)
    admins, sup, leaders = 0, 0, 0
    for i in users:
        if i.fraction is not None:
            leaders += 1
            fractions.remove(i.fraction)
        elif i.role in SUPPORT_ROLES:
            sup += 1
        else:
            admins += 1
    text = f"""❇️ Администраторов: <code>{admins}</code>
📚 Агентов Поддержки: <code>{sup}</code>
⚙️ Лидеров: <code>{leaders}</code>
"""
    if len(fractions) > 0:
        text += (
            "\n\n⚠️ Не хватает лидеров для следующих фракций: <code>"
            + "</code>, <code>".join(fractions)
            + "</code>"
        )
    msg = await query.bot.send_message(chat_id=query.from_user.id, text=text)
    await state.clear()
    await state.update_data(msg=msg)


@router.message(Command("sc"), F.chat.type == "private")
@router.callback_query(keyboard.Callback.filter(F.type == "servercontrol"))
async def servercontrol(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if not user or user.role not in (
        "Главный администратор",
        "Основной ЗГА",
        "Заместитель ГА",
    ):
        return
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.servercontrol(),
        text="Управление сервером",
    )
    await state.clear()
    await state.update_data(msg=msg, from_sc=True)


@router.callback_query(keyboard.Callback.filter(F.type == "serversettings"))
async def serversettings(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.serversettings(),
        text="Настройки",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serveradmins"))
async def serveradmins(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.serveradmins(),
        text="Настройка администрации:",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serversheets"))
async def serversheets(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.serversheets(),
        text="Настройка таблиц:",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("serversheets_")))
async def serversheets_(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text="Введите ID Google таблицы:"
    )
    await state.clear()
    if query.data.split(":")[-1].endswith("support"):
        await state.set_state(states.ServerSheets.s)
    elif query.data.split(":")[-1].endswith("leaders"):
        await state.set_state(states.ServerSheets.L)
    elif query.data.split(":")[-1].endswith("admins"):
        await state.set_state(states.ServerSheets.a)
    else:
        raise ValueError
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "setinactiveamnt_a"))
async def setinactiveamnt_a(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Введите количество ответов, которые будут сниматься за день неактива:",
    )
    await state.clear()
    await state.set_state(states.Settings.setinactiveamnt_answers.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats"))
async def serverchats(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, reply_markup=keyboard.serverchats(), text="Чаты"
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats_objective"))
async def serverchats_objective(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.serverchats_objective(),
        text="Норматив",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "objective_admins"))
async def objective_admins(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.objective_admins.state)
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type == "serverchats_additionalreplies")
)
async def serverchats_additionalreplies(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Доп. ответы",
        reply_markup=keyboard.serverchats_additionalreplies(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "additionalreplies_admins"))
async def additionalreplies_admins(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.additionalreplies.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats_inactive"))
async def serverchats_inactive(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Неактивы",
        reply_markup=keyboard.serverchats_inactive(),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats_coins"))
async def serverchats_coins(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.coins.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats_punishments"))
async def serverchats_punishments(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.punishments.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "inactive_support"))
async def inactive_support(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.inactive_support.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "inactive_leaders"))
async def inactive_leaders(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.inactive_leaders.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "inactive_admins"))
async def inactive_admins(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.inactive_admins.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "serverchats_forms"))
async def serverchats_forms(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id, text='Введите ID канала/темы(через "/"):'
    )
    await state.clear()
    await state.set_state(states.ServerChats.forms.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "formproof_y"))
async def formproof_y(query: CallbackQuery, state: FSMContext):
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text="Отправьте ссылку(-и, через запятую или пробел) на доказательства:",
    )
    await state.set_state(states.Forms.proof.state)
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "formproof_send"))
async def formproof_send(query: CallbackQuery, state: FSMContext):
    user = Users.get(Users.telegram_id == query.from_user.id)
    form = (await state.get_data())["form"]
    form = Forms.create(form=form, fromtgid=user.telegram_id)
    text = f"""
[📗 #{str(form.get_id()).zfill(4)}] Новая форма от <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n
<code>{form.form}</code>
"""
    chat = Chats.get(Chats.setting == "forms")
    await query.bot.send_message(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        text=text,
        reply_markup=keyboard.form(form.get_id()),
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"✅ Форма №{str(form.get_id()).zfill(4)} отправлена.",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("form_")))
async def form_(query: CallbackQuery):
    text = query.message.html_text
    form = Forms.get_by_id(int(query.data.split(":")[-1].split("_")[-1]))
    admin = Users.get(Users.telegram_id == query.from_user.id)
    if "🔎" in text:
        text = text[: text.find("🔎") - 3]
    text += (
        f"""\n
❓ Статус: <b>{"Отказано" if "disapprove" in query.data.split(":")[-1] else "Одобрено"}</b>
👤 Ответственный: <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>"""
        + (
            f"\n🔎 Доказательства: {', '.join(ast.literal_eval(form.proofs))}"
            if form.proofs
            else ""
        )
        + f"""
🕒 Дата обработки: <code>{formatts(time.time())}</code>"""
    )
    await query.message.edit_text(text)
    try:
        await query.bot.send_message(
            chat_id=form.fromtgid,
            text=f"❌ Форма №{str(form.get_id()).zfill(4)} была отказана администратором "
            f'<a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>.'
            if "disapprove" in query.data.split(":")[-1]
            else f"✅ Форма №{str(form.get_id()).zfill(4)} была одобрена администратором "
            f'<a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>.',
        )
    except Exception:
        pass


@router.callback_query(keyboard.Callback.filter(F.type.startswith("inactiverequest_")))
async def inactiverequest_(query: CallbackQuery):
    text = query.message.html_text
    try:
        ir = InactiveRequests.get_by_id(int(query.data.split("_")[-1]))
    except Exception:
        await query.bot.answer_callback_query(
            query.id, text="⚠️ Данное заявление уже было обработано."
        )
        return
    user = Users.get(Users.telegram_id == ir.tgid)
    admin = Users.get(Users.telegram_id == query.from_user.id)
    if "disapprove" in query.data.split(":")[-1]:
        text += f'\n\n🔴 Заявление было отказано — <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>'
        Inactives.create(
            nickname=user.nickname,
            role=user.role,
            start=ir.start,
            end=ir.end,
            status="Отказан",
            reason=ir.reason,
            fraction=user.fraction,
        )
        markup = None
    else:
        text += f'\n\n🟢 Заявление было одобрено — <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>'
        Inactives.create(
            nickname=user.nickname,
            role=user.role,
            start=ir.start,
            end=ir.end,
            status="Одобрен",
            reason=ir.reason,
            fraction=user.fraction,
        )
        user.inactivestart = formatedtotts(ir.start)
        user.inactiveend = formatedtotts(ir.end)
        user.save()
        if user.fraction:
            apa = "баллы"
        elif user.role in SUPPORT_ROLES:
            apa = "аски"
        else:
            apa = "ответы"
        markup = keyboard.inactiveapa(user.telegram_id, apa)
    ir.delete_instance()
    await query.message.edit_text(text, reply_markup=markup)
    try:
        await query.bot.send_message(
            chat_id=ir.tgid,
            text=f'❌ <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> отказал вам в неактиве '
            f"№{str(ir.get_id()).zfill(4)}."
            if "disapprove" in query.data.split(":")[-1]
            else f'✅ <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> одобрил вам неактив '
            f"№{str(ir.get_id()).zfill(4)}.",
        )
    except Exception:
        pass
    sheets.main(composition=True, inactives=True)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("inactiveapa_")))
async def inactiveapa_(query: CallbackQuery):
    text = query.message.html_text
    data = query.message.text.strip().split()
    admin = Users.get(Users.telegram_id == query.from_user.id)
    user = Users.get(Users.telegram_id == int(query.data.split(":")[-1].split("_")[-1]))
    w = f"{data[data.index('Количество') + 2]} {data[data.index('Количество') + 1][:-1]}"
    user.apa -= int(w.split()[0])
    user.save()
    text += f"\n🟢 Снято <code>{w}</code>"
    await query.message.edit_text(text)
    try:
        await query.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id='
            f'{admin.telegram_id}">{admin.nickname}</a> снял вам <code>{w}</code>.',
        )
    except Exception:
        pass
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("additionalreply_")))
async def additionalreply_(query: CallbackQuery, state: FSMContext):
    text = query.message.html_text
    admin = Users.get(Users.telegram_id == query.from_user.id)
    if "disapprove" in query.data.split(":")[-1]:
        text += f'\n\n🔴 Заявление было отказано — <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>'
        try:
            await query.bot.send_message(
                chat_id=int(query.data.split(":")[-1].split("_")[-1]),
                text=f'❌ <a href="tg://user?id={admin.telegram_id}">'
                f"{admin.nickname}</a> отказал вам в дополнительных ответах.",
            )
        except Exception:
            pass
        return await query.message.edit_text(text)
    await state.set_state(states.Reports.sendadditionalreplyw.state)
    msg = await query.bot.send_message(
        chat_id=query.message.chat.id,
        message_thread_id=query.message.message_thread_id,
        text="❓ Введите количество выдаваемых ответов:",
    )
    await state.update_data(
        msg=msg, edit=query.message, user=int(query.data.split(":")[-1].split("_")[-1])
    )


@router.callback_query(
    keyboard.Callback.filter(F.type.startswith("reportssendobjective_"))
)
async def reportssendobjective_(query: CallbackQuery, state: FSMContext):
    text = query.message.html_text
    admin = Users.get(Users.telegram_id == query.from_user.id)
    if "disapprove" in query.data.split(":")[-1]:
        text += f'\n\n🔴 Заявление было отказано — <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>'
        try:
            await query.bot.send_message(
                chat_id=int(query.data.split(":")[-1].split("_")[-1]),
                text=f'❌ <a href="tg://user?id={admin.telegram_id}">'
                f"{admin.nickname}</a> отказал вашу заявку на норматив.",
            )
        except Exception:
            pass
        return await query.message.edit_caption(caption=text)
    elif "approve" in query.data.split(":")[-1]:
        await state.set_state(states.Reports.sendobjectivewa.state)
    else:
        await state.set_state(states.Reports.sendobjectivew.state)
    msg = await query.bot.send_message(
        chat_id=query.message.chat.id,
        message_thread_id=query.message.message_thread_id,
        text="❓ Введите количество выдаваемых ответов:",
    )
    await state.update_data(
        msg=msg, edit=query.message, user=int(query.data.split(":")[-1].split("_")[-1])
    )


@router.callback_query(keyboard.Callback.filter(F.type == "usersinactiveset_y"))
async def usersinactiveset_y(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = Users.get_by_id(data["uid"])
    user.apa -= data["w"]
    user.save()
    admin = Users.get(Users.telegram_id == query.from_user.id)
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"✅ Вы успешно сняли <code>{data['p']}</code> <code>{data['user']}</code>.",
    )
    try:
        await query.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>'
            f" снял вам <code>{data['p']}</code>, "
            f"теперь у вас <code>{user.apa} {data['p'].split()[-1]}</code>.",
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("promote_")))
async def promote_(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = Users.get_or_none(Users.telegram_id == data["uid"])
    if user is None or not checkrole(
        Users.get_or_none(Users.telegram_id == query.from_user.id), user
    ):
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="⚠️ Вы не можете повысить данного пользователя.",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return
    user.role = ROLES[int(query.data.split(":")[-1].split("_")[-1])]
    user.promoted = int(time.time())
    user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.promote_days(),
        text=f'✅ Вы успешно установили должность "<code>{user.role}</code>" '
        f'администратору <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>. Аннулировать дни нормы?',
    )
    try:
        admin = Users.get(Users.telegram_id == query.from_user.id)
        await query.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📗 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}'
            f'</a> повысил вас до должности "<code>{user.role}</code>".',
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg, user=user)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("promotedays")))
async def promotedays(query: CallbackQuery, state: FSMContext):
    user = (await state.get_data())["user"]
    if query.data.split(":")[-1].endswith("_y"):
        user.objective_completed = 0
        user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        reply_markup=keyboard.promote_answers(),
        text="Аннулировать ответы?",
    )
    await state.clear()
    await state.update_data(msg=msg, user=user)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("promoteanswers")))
async def promoteanswers(query: CallbackQuery, state: FSMContext):
    user = (await state.get_data())["user"]
    if query.data.split(":")[-1].endswith("_y"):
        user.apa = 0
        user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'✅ Вы успешно повысили администратора <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.callback_query(keyboard.Callback.filter(F.type == "to_admin"))
async def to_admin(message: Message, state: FSMContext):
    user = (await state.get_data())["user"]
    admin = (await state.get_data())["admin"]
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.promote("to_admin"),
        text="Выберите новую должность:",
    )
    await state.clear()
    await state.update_data(msg=msg, uid=user.telegram_id, adminuid=admin.telegram_id)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("to_admin_")))
async def to_admin_(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    admin = Users.get_or_none(Users.telegram_id == data["adminuid"])
    user = Users.get_or_none(Users.telegram_id == data["uid"])
    if user.fraction:
        struct = "l"
    elif user.role in SUPPORT_ROLES:
        struct = "s"
    else:
        struct = "a"
    Removed.create(
        nickname=user.nickname,
        role=user.role,
        appointed=user.appointed,
        name=user.name,
        age=calcage(user.age),
        city=user.city,
        discord_id=user.discord_id,
        telegram_id=user.telegram_id,
        reason="На админку.",
        forum=user.forum,
        whoremoved=admin.nickname,
        vk=user.vk,
        date=formatts(time.time()),
        fraction=user.fraction,
        struct=struct,
    ).save()
    user.role = ROLES[int(query.data.split(":")[-1].split("_")[-1])]
    user.fraction = None
    user.apa = 0
    user.appointed = int(time.time())
    user.rebuke = 0
    user.warn = 0
    user.verbal = 0
    user.inactivestart = None
    user.inactiveend = None
    user.save()
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'✅ Вы успешно установили должность "<code>{user.role}</code>" '
        f'администратору <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    try:
        admin = Users.get(Users.telegram_id == query.from_user.id)
        await query.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📗 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}'
            f'</a> назначил вас на пост "<code>{user.role}</code>".',
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg, user=user)
    sheets.main(composition=True)


@router.callback_query(
    keyboard.Callback.filter(
        F.type.in_(keyboard.COINS_SUBBUTTONS.keys()) | (F.type == "coins")
    )
)
async def coins(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"""
<b>➡️ Никнейм: {user.nickname}</b>
<b>🪙 Количество монеток: <code>{user.coins} штук.</code></b>
<b>📅 Последнее использование: <code>{datetime.fromtimestamp(user.coins_last_spend).strftime("%d.%m.%Y / %H:%M") if user.coins_last_spend else "нет"}</code></b>

<b>💬 Здесь вы можете обменять свои заработанные монетки на определенные призы, ниже вы можете ознакомится со всеми категориями.</b>

<b>1️⃣ Наказания </b>
├─ <code>#1.1</code> 🪙    5 | Снять устное предупреждение
├─ <code>#1.2</code> 🪙   15 | Снять предупреждение
├─ <code>#1.3</code> 🪙   25 | Снять выговор
└─ <code>#1.4</code> 🪙  100 | Снять все наказания

<b>2️⃣ Иммунитеты</b>
├─ <code>#2.1</code> 🪙     8 | Устное предупреждение
├─ <code>#2.2</code> 🪙    18 | Предупреждение
├─ <code>#2.3</code> 🪙    28 | Выговор
└─ <code>#2.</code>4 🪙    50 | Любое первое наказание

<b>3️⃣ Игровая валюта (рулетка)</b>
├─ <code>#3.1</code> 🪙     5 | От 100 000 до 300 000
├─ <code>#3.2</code> 🪙    15 | От 300 000 до 500 000
└─ <code>#3.3</code> 🪙    30 | От 500 000 до 1 000 000

<b>4️⃣ Росписи</b>
├─ <code>#4.1</code> 🪙    80 | Роспись от спец. администрации
├─ <code>#4.2</code> 🪙    60 | Роспись от команды проекта
└─ <code>#4.3</code> 🪙    20 | Роспись от руководство сервера

<b>5️⃣ Ответы</b>
├─ <code>#5.1</code> 🪙    15 | От 500 до 1000 ответов
├─ <code>#5.2</code> 🪙    30 | От 1000 до 2000 ответов
├─ <code>#5.3</code> 🪙    50 | x2 ответов на 3 дня
└─ <code>#5.4</code> 🪙     5 | Добить норматив
 
<b>6️⃣ Нормативы</b>
├─ <code>#6.1</code> 🪙    50 | Специальный норматив 7 дней
├─ <code>#6.2</code> 🪙    10 | Освобождение от норматива
├─ <code>#6.3</code> 🪙    40 | Понижение норматива на 30 минут
└─ <code>#6.4</code> 🪙     3 | Неактив 1 день

<b>7️⃣ Дополнительные</b>
├─ <code>#7.1</code> 🪙    30 | Стикер-пак VK (10 голосов)
└─ <code>#7.2</code> 🪙    10 | Доступ к автопарку семьи
""",
        reply_markup=keyboard.coins(query.data.split(":")[-1]),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "punishments_menu"))
async def punishments_menu(query: CallbackQuery, state: FSMContext):
    await query.answer()
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if user.rebuke + user.warn + user.verbal == 0:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text=f"<b>👍 {user.nickname}, у вас нету активных наказаний.</b>",
            reply_markup=keyboard.back(),
        )
    else:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="<b>📕 Выберите тип наказания для отправки заявление на снятие.</b>",
            reply_markup=keyboard.punishments_menu(user.rebuke, user.warn, user.verbal),
        )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(
    keyboard.Callback.filter(F.type.startswith("punishments_menu_request_"))
)
async def punishments_menu_request(query: CallbackQuery, state: FSMContext):
    from_user = Users.get(Users.telegram_id == query.from_user.id)
    punishments_chat = Chats.get(Chats.setting == "punishments")
    punishment_short = query.data.split("_")[-1]
    request = PunishmentsRequests.create(
        telegram_id=query.from_user.id, punishment=punishment_short
    )
    punishment = {
        "rebuke": "Выговор",
        "warn": "Предупреждение",
        "verbal": "Устное предупреждение",
    }[punishment_short]
    await query.bot.send_message(
        chat_id=int(f"-100{punishments_chat.chat_id}"),
        message_thread_id=punishments_chat.thread_id,
        reply_markup=keyboard.punishment_request(),
        text=f"""<b>📗 [#{request.get_id()}] Снятие наказаний

👤 Администратор: <a href="tg://user?id={from_user.telegram_id}">{from_user.nickname}</a>
🌐 Должность: <code>{from_user.role}</code>
📙 Тип наказание: {punishment}
💎 Количество ответов: {from_user.apa}
🕒 Дата отправки: {formatts(time.time())}</b>""",
    )
    punishment = {
        "rebuke": "выговора",
        "warn": "предупреждения",
        "verbal": "устного предупреждения",
    }[punishment_short]
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"<b>✅ Заявление на снятие <code>{punishment}</code> было успешно отправлено, ожидайте рассмотрение.</b>",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("coins_buy_")))
async def coins_buy(query: CallbackQuery, state: FSMContext):
    user = Users.get_or_none(Users.telegram_id == query.from_user.id)
    if time.time() - user.coins_last_spend < 86400 * 7:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="<b>⚠️ Ваша последняя покупка была совершене менее 7 дней назад.</b>",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return

    category = f"coins_{'_'.join(query.data.split(':')[-1].split('_')[2:-1])}"
    lot = COINS_SUBBUTTONS[category][query.data.split(":")[-1].split("_")[-1]]
    if user.coins < lot[1]:
        msg = await query.bot.send_message(
            chat_id=query.from_user.id,
            text="<b>⚠️ У вас не хватает монеток.</b>",
        )
        await state.clear()
        await state.update_data(msg=msg)
        return

    req = CoinsRequests.create(telegram_id=query.from_user.id, lot_name=lot[0])
    chat = Chats.get(Chats.setting == "coins")
    await query.bot.send_message(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        text=f"""<b>📗 [<code>#{str(req.get_id()).zfill(3)}</code>] Монетки — <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n
🪙 Количество монеток: <code>{user.coins - lot[1]}</code>
💬 Выбранный приз: "<code>{lot[0]}</code>"
📅 Дата отправки: <code>{datetime.now().strftime("%d.%m.%Y")}</code></b>""",
        reply_markup=keyboard.coins_request(),
    )

    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f'<b>✅ Заявления на получение "<code>{lot[0]}</code>" было отправлено, ожидайте рассмотрение.</b>',
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type == "stats_coins"))
async def stats_coins(query: CallbackQuery, state: FSMContext):
    user = (await state.get_data())["user"]
    logs = (
        CoinsLog.select()
        .where(CoinsLog.telegram_id == str(user.telegram_id))
        .order_by(CoinsLog.date.desc())
        .limit(25)
    )
    msg = await query.bot.send_message(
        chat_id=query.from_user.id,
        text=f"""
<b>➡️ Никнейм: {user.nickname}</b>
<b>🪙 Количество монеток: <code>{user.coins} штук.</code></b>
<b>📅 Последнее использование: <code>{datetime.fromtimestamp(user.coins_last_spend).strftime("%d.%m.%Y / %H:%M") if user.coins_last_spend else "нет"}</code></b>

<b>💬 Последние <code>{len(logs)}</code> купленных призов администратором</b>\n\n
"""
        + "\n".join(
            [
                f"{k}. {log.lot_name} - {datetime.fromtimestamp(log.date).strftime('%d.%m.%Y / %H:%M')}"
                for k, log in enumerate(logs, start=1)
            ]
        ),
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.callback_query(keyboard.Callback.filter(F.type.startswith("coins_request_")))
async def coins_request(query: CallbackQuery, state: FSMContext):
    await query.message.delete_reply_markup()
    admin = Users.get(Users.telegram_id == query.from_user.id)
    req_id = int(query.message.text.replace("📗 [#", "").split("]")[0])
    req = CoinsRequests.get_by_id(req_id)
    if "n" not in query.data.split(":")[-1].split("_"):
        user = Users.get(Users.telegram_id == str(req.telegram_id))
        user.coins_last_spend = int(time.time())
        for category in COINS_SUBBUTTONS.values():
            for _, (text, value) in category.items():
                if text == req.lot_name:
                    user.coins -= value
        user.save()
    text = query.message.html_text + (
        f"""\n
❓ Статус: <b>{"Отказано" if "n" in query.data.split(":")[-1].split("_") else "Одобрено"}</b>
👤 Ответственный: <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>\n
🕒 Дата обработки: <code>{formatts(time.time())}</code>"""
    )
    try:
        await query.bot.send_message(
            chat_id=req.telegram_id,
            text=f'<b>❌ Заявления на получение "<code>{req.lot_name}</code>" была отклонена администратором - </b><a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>.'
            if "n" in query.data.split(":")[-1].split("_")
            else f'<b>✅ Заявления на получение "<code>{req.lot_name}</code>" была одобрена администратором - </b><a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>.',
        )
    except Exception:
        pass
    await query.message.edit_text(text)


@router.callback_query(
    keyboard.Callback.filter(F.type.startswith("punishment_request_"))
)
async def punishment_request_(query: CallbackQuery, state: FSMContext):
    req_id = int(query.message.text.replace("📗 [#", "").split("]")[0])
    req = PunishmentsRequests.get_by_id(req_id)
    if "decline" not in query.data.split(":")[-1].split("_"):
        user = Users.get(Users.telegram_id == str(req.telegram_id))
        setattr(user, req.punishment, max(getattr(user, req.punishment) - 1, 0))
        user.save()

        admin = Users.get(Users.telegram_id == query.from_user.id)
        _punishment = {
            "rebuke": "Выговор",
            "warn": "Предупреждение",
            "verbal": "Устное предупреждение",
        }[str(req.punishment)]
        await query.message.edit_text(
            query.message.html_text
            + f"""\n
❓ Статус: <b>Одобрено</b>
👤 Ответственный: <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>\n
➡️ Для отчёта: <code>📗 {user.nickname} снял {_punishment} - {formatts(time.time())} | Рассмотрел - {admin.nickname}</code>"""
        )
        try:
            await query.bot.send_message(
                chat_id=req.telegram_id,
                text=f'📗 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> одобрил заявление на снятие "<code>{_punishment}</code>".',
            )
        except Exception:
            pass

        await state.clear()
    else:
        msg = await query.bot.send_message(
            chat_id=query.message.chat.id,
            message_thread_id=query.message.message_thread_id,
            text="<b>Введите причину:</b>",
        )
        await state.clear()
        await state.set_state(states.PunishmentsMenu.reason.state)
        await state.update_data(msg=msg, original_query=query, prequest=req)


@router.message(states.PunishmentsMenu.reason)
async def punishments_menu_reason(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass

    if not message.text:  # 2lazy2think (im so sry)
        await state.clear()
        return

    admin = Users.get(Users.telegram_id == message.from_user.id)
    query: CallbackQuery = (await state.get_data())["original_query"]
    request = (await state.get_data())["prequest"]
    await query.message.edit_text(
        query.message.html_text
        + f"""\n
❓ Статус: <b>Отказано</b>
💬 Причина: {message.text}
👤 Ответственный: <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a>"""
    )
    try:
        _punishment = {
            "rebuke": "Выговор",
            "warn": "Предупреждение",
            "verbal": "Устное предупреждение",
        }[str(request.punishment)]
        await message.bot.send_message(
            chat_id=request.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> отказал заявление на снятие "<code>{_punishment}</code>" по причине "{message.text}".',
        )
    except Exception:
        pass

    await state.clear()


@router.message(states.Reports.sendobjectivew)
@router.message(states.Reports.sendobjectivewa)
async def _reportssendobjectivew_wa(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip().isdigit():
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            text="⚠️ Введите число.\n❓ Введите количество выдаваемых ответов:",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == (await state.get_data())["user"])
    user.apa += int(message.text.strip())
    admin = Users.get(Users.telegram_id == message.from_user.id)
    text = (
        f'✅ <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> принял вашу заявку на норматив. '
        f"Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        user.objective_completed += 1
        text += " + 1 день норматива"
    try:
        await message.bot.send_message(chat_id=user.telegram_id, text=text + "</code>.")
    except Exception:
        pass
    user.save()
    edit: Message = (await state.get_data())["edit"]
    text = edit.html_text + (
        f'\n\n🟢 Заявление было одобрено — <a href="tg://user?id={admin.telegram_id}">'
        f"{admin.nickname}</a>\n🟢 Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        text += " + 1 день норматива"
    await edit.edit_caption(caption=text + "</code>.")
    sheets.main(composition=True)
    await state.clear()


@router.message(states.Reports.sendobjectivew)
@router.message(states.Reports.sendobjectivewa)
async def reportssendobjectivew_wa_(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip().isdigit():
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            text="⚠️ Введите число.\n❓ Введите количество выдаваемых ответов:",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == (await state.get_data())["user"])
    user.apa += int(message.text.strip())
    admin = Users.get(Users.telegram_id == message.from_user.id)
    text = (
        f'✅ <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> принял вашу заявку на норматив. '
        f"Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        user.objective_completed += 1
        text += " + 1 день норматива"
    try:
        await message.bot.send_message(chat_id=user.telegram_id, text=text + "</code>.")
    except Exception:
        pass
    user.save()
    edit: Message = (await state.get_data())["edit"]
    text = edit.html_text + (
        f'\n\n🟢 Заявление было одобрено — <a href="tg://user?id={admin.telegram_id}">'
        f"{admin.nickname}</a>\n🟢 Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        text += " + 1 день норматива"
    await edit.edit_caption(caption=text + "</code>.")
    sheets.main(composition=True)
    await state.clear()


@router.message(states.Reports.sendobjectivew)
@router.message(states.Reports.sendobjectivewa)
async def reportssendobjectivew_wa(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip().isdigit():
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            text="⚠️ Введите число.\n❓ Введите количество выдаваемых ответов:",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == (await state.get_data())["user"])
    user.apa += int(message.text.strip())
    admin = Users.get(Users.telegram_id == message.from_user.id)
    text = (
        f'✅ <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> принял вашу заявку на норматив. '
        f"Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        user.objective_completed += 1
        text += " + 1 день норматива"
    try:
        await message.bot.send_message(chat_id=user.telegram_id, text=text + "</code>.")
    except Exception:
        pass
    user.save()
    edit: Message = (await state.get_data())["edit"]
    text = edit.html_text + (
        f'\n\n🟢 Заявление было одобрено — <a href="tg://user?id={admin.telegram_id}">'
        f"{admin.nickname}</a>\n🟢 Начислено <code>{message.text.strip()} ответов"
    )
    if await state.get_state() == states.Reports.sendobjectivewa.state:
        text += " + 1 день норматива"
    await edit.edit_caption(caption=text + "</code>.")
    sheets.main(composition=True)
    await state.clear()


@router.message(states.Reports.sendadditionalreplyw)
async def reportssendadditionalreplyw(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip().isdigit():
        msg = await message.bot.send_message(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            text="⚠️ Введите число.\n❓ Введите количество выдаваемых ответов:",
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == (await state.get_data())["user"])
    user.apa += int(message.text.strip())
    user.save()
    edit: Message = (await state.get_data())["edit"]
    admin = Users.get(Users.telegram_id == message.from_user.id)
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'✅ <a href="tg://user?id={admin.telegram_id}">'
            f"{admin.nickname}</a> одобрил вашу заявку на доп. ответы. "
            f"Начислено <code>{message.text.strip()} ответов</code>.",
        )
    except Exception:
        pass
    await edit.edit_text(
        text=edit.html_text
        + f'\n\n🟢 Заявление было одобрено — <a href="tg://user?id={admin.telegram_id}">'
        f"{admin.nickname}</a>\n🟢 Начислено <code>{message.text.strip()} ответов</code>."
    )
    sheets.main(composition=True)
    await state.clear()


@router.message(states.APA.change)
async def apachange(message: Message, state: FSMContext):
    await message.delete()

    admin = Users.get(Users.telegram_id == message.from_user.id)
    if admin.fraction:
        apa = "баллов"
    elif admin.role in SUPPORT_ROLES:
        apa = "асков"
    else:
        apa = "ответов"
    stext, fdata = "", message.text.split("\n")
    for c, text in enumerate(fdata):
        data = [i for i in re.split(r"[, \n]", text.strip()) if i != ""]
        splitter = 0
        users = []
        for i in data:
            if i[0] in ("+", "-") or i.isdigit():
                splitter = data.index(i)
                break
            users.append(i)
        if len(data) < 2 or not splitter or not data[splitter][1:].isdigit():
            continue
        nicks = set()
        failed = set()
        reason = (
            ""
            if splitter == (len(data) - 1)
            else f' по причине: "{",".join(data[splitter + 1 :])}"'
        )
        for i in data[:splitter]:
            user = Users.get_or_none(Users.nickname == i.replace(",", ""))
            if user is None or not checkrole(admin, user):
                stext += (
                    f"{f'[{c + 1}]. ' if len(fdata) > 1 else ''}⚠️ Пользователя с никнеймом {i.replace(',', '')} "
                    f"не существует.\n\n"
                )
                continue
            if user.nickname in nicks:
                continue
            user.apa += int(data[splitter])
            user.save()
            nicks.add(user.nickname)
            try:
                await message.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"{'📗' if '-' not in data[splitter] else '📕'} <code>{admin.nickname}</code> "
                    f"{'выдал' if '-' not in data[splitter] else 'снял'} вам <code>{data[splitter]} {apa}</code>, "
                    f"теперь у вас <code>{user.apa} {apa}</code>{reason}.",
                )
            except Exception:
                failed.add(user.nickname)
        if nicks:
            stext += (
                f"{f'[{c + 1}]. ' if len(fdata) > 1 else ''} ✅ Вы успешно "
                f"{'выдали' if '-' not in data[splitter] else 'сняли'} <code>{data[splitter]} {apa}</code> "
                f"<code>{'</code>, <code>'.join(nicks)}</code>{reason}.\n"
            )
            if failed:
                stext += f"⚠️ Не удалось отправить уведомление <code>{'</code>, <code>'.join(failed)}</code>.\n\n"
            else:
                stext += "\n"
    msg = await message.bot.send_message(chat_id=message.from_user.id, text=stext)

    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.message(StatesGroupHandle(states.ServerChats))
async def serverchats_state(message: Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state is None:
        return
    await message.delete()

    data = message.text.strip().split("/")
    if len(data) > 2 or not all(i.isdigit() for i in data):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text='⚠️ Неверные данные.\nВведите ID канала/темы(через "/"):',
        )
        await state.update_data(msg=msg)
        return
    chid = int(data[0])
    threadid = int(data[1]) if len(data) == 2 else None
    Chats.delete().where(
        Chats.setting == curr_state.replace("ServerChats:", "")
    ).execute()
    Chats.create(
        setting=curr_state.replace("ServerChats:", ""), chat_id=chid, thread_id=threadid
    )
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f"✅ Вы успешно установили новый чат для отправки уведомлений класса <code>{curr_state}</code>.",
    )

    await state.clear()
    await state.update_data(msg=msg)


@router.message(StatesGroupHandle(states.Punishments))
async def punishments_state(message: Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state is None:
        return
    await message.delete()

    stext, fdata = "", message.text.split("\n")
    for c, ftext in enumerate(fdata):
        action = curr_state[-1]
        data = ftext.strip().split()
        user = Users.get_or_none(Users.nickname == data[0])
        text = "⚠️ Неверные данные."
        if not user:
            check = False
        elif len(data) > 1:
            if data[1] != "-":
                check = True
            elif data[1] in ("+", "-"):
                text = "⚠️ У пользователя нет наказаний такого типа."
                if action == "v":
                    check = user.verbal >= 1
                elif action == "w":
                    check = user.warn >= 1
                else:
                    check = user.rebuke >= 1
            else:
                check = False
        else:
            check = False
        if not check or not checkrole(
            Users.get_or_none(Users.telegram_id == message.from_user.id), user
        ):
            stext += (f"[{c + 1}]. " if len(fdata) > 1 else "") + text + "\n\n"
            continue
        if action == "v":
            user.verbal += int(data[1] + "1")
            action = "одно устное предупреждение"
        elif action == "w":
            user.warn += int(data[1] + "1")
            action = "одно предупреждение"
        else:
            user.rebuke += int(data[1] + "1")
            action = "один выговор"
        if user.verbal >= 2:
            user.warn += user.verbal // 2
            user.verbal -= (user.verbal // 2) * 2
        if user.warn >= 2:
            user.rebuke += user.warn // 2
            user.warn -= (user.warn // 2) * 2
        user.save()
        reason = (' по причине: "' + " ".join(data[2:]) + '"') if len(data) > 2 else ""
        try:
            await message.bot.send_message(
                chat_id=user.telegram_id,
                text=f"{'📗' if data[1] == '-' else '📕'} Администратор <code>"
                f"{Users.get(Users.telegram_id == message.from_user.id).nickname}</code> "
                f"{'снял' if data[1] == '-' else 'выдал'} вам <code>{action}</code>{reason}.",
            )
        except Exception:
            pass
        stext += (
            f"{f'[{c + 1}]. ' if len(fdata) > 1 else ''}✅ Вы успешно "
            f"{'сняли' if '-' in data[1] else 'выдали'} <code>{action}</code>"
            f' пользователю <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.\n\n'
        )
    msg = await message.bot.send_message(chat_id=message.from_user.id, text=stext)
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True)


@router.message(StatesGroupHandle(states.Settings))
async def settings(message: Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state is None:
        return
    await message.delete()

    if curr_state.endswith("points"):
        action = "количество баллов, которые будут сниматься за день неактива"
        setting, new = Settings_l.get_or_create(
            setting="inactiveamnt_points", defaults={"val": 0}
        )
    elif curr_state.endswith("asks"):
        action = "количество асков, которые будут сниматься за день неактива"
        setting, new = Settings_s.get_or_create(
            setting="inactiveamnt_asks", defaults={"val": 0}
        )
    elif curr_state.endswith("answers"):
        action = "количество ответов, которые будут сниматься за день неактива"
        setting, new = Settings_a.get_or_create(
            setting="inactiveamnt_answers", defaults={"val": 0}
        )
    elif curr_state.endswith("_d"):
        action = "количество дней, требуемых для перевода в администрацию"
        setting, new = Settings_s.get_or_create(
            setting="transferamnt_d", defaults={"val": 0}
        )
    elif curr_state.endswith("_a"):
        action = "количество асков, требуемых для перевода в администрацию"
        setting, new = Settings_s.get_or_create(
            setting="transferamnt_a", defaults={"val": 0}
        )
    else:
        raise ValueError

    if not message.text.strip().isdigit():
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text=f"⚠️ Введите число.\nВведите {action}:"
        )
        await state.update_data(msg=msg)
        if new:
            setting.delete_instance()
        return
    setting.val = int(message.text.strip())
    setting.save()
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f"✅ Вы успешно установили новое {action} - <code>{message.text.strip()}</code>.",
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(StatesGroupHandle(states.ServerSheets))
async def serversheets_s(message: Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state is None:
        return
    await message.delete()

    if curr_state.endswith("s"):
        setting, new = Sheets.get_or_create(setting="s", defaults={"val": "0"})
    elif curr_state.endswith("l"):
        setting, new = Sheets.get_or_create(setting="l", defaults={"val": "0"})
    elif curr_state.endswith("a"):
        setting, new = Sheets.get_or_create(setting="a", defaults={"val": "0"})
    else:
        raise ValueError
    setting.val = message.text.strip()
    setting.save()
    msg = await message.bot.send_message(
        chat_id=message.from_user.id, text="✅ Вы успешно установили новый Google ID."
    )
    await state.clear()
    await state.update_data(msg=msg)


@router.message(states.UsersInactive.set)
async def usersinactiveset(message: Message, state: FSMContext):
    await message.delete()

    data = message.text.strip().replace(" - ", " ").split()
    try:
        if len(data) != 3:
            raise ValueError
        user = Users.get_or_none(Users.nickname == data[0])
        if user is None:
            raise ValueError
        start = datetime.strptime(data[1], "%d.%m.%Y")
        end = datetime.strptime(data[2], "%d.%m.%Y")
        if start.timestamp() > end.timestamp():
            raise ValueError
    except Exception:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text="⚠️ Неверные данные или формат.\nВведите никнейм, дату начала и дату окончания. Пример: "
            '"Andrey_Mal 15.12.2024 20.12.2024"',
        )
        await state.update_data(msg=msg)
        return
    admin = Users.get(Users.telegram_id == message.from_user.id)
    if not checkrole(admin, user):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text=f'⚠️ Пользователя с никнеймом "{data[0]}" не существует.\n'
            f'Введите никнейм, дату начала и дату окончания. Пример: "Andrey_Mal 15.12.2024 20.12.2024"',
        )
        await state.update_data(msg=msg)
        return
    if user.role in SUPPORT_ROLES:
        w = Settings_s.get(Settings_s.setting == "inactiveamnt_asks").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('аск', 'аска', 'асков'))}"
        sla = "агенту поддержки"
    elif user.fraction:
        w = Settings_l.get(Settings_l.setting == "inactiveamnt_points").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('балл', 'балла', 'баллов'))}"
        sla = "лидеру фракции"
    else:
        w = Settings_a.get(Settings_a.setting == "inactiveamnt_answers").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('ответ', 'ответа', 'ответов'))}"
        sla = "администратору"
    Inactives.create(
        nickname=user.nickname,
        role=user.role,
        fraction=user.fraction,
        start=formatts(start.timestamp()),
        end=formatts(end.timestamp()),
        status="Одобрен",
    ).save()
    user.inactivestart = start.timestamp()
    user.inactiveend = end.timestamp()
    user.save()
    days = ceil((end.timestamp() - start.timestamp()) / 86400)
    text = (
        f'✅ Вы успешно выдали неактив {sla} <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>. '
        f"Хотите снять <code>{p}</code> за неактив сроком в "
        f"<code>{days} {plural_word(days, ('день', 'дня', 'дней'))}</code>?"
    )
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📗 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}'
            f"</a> выдал вам неактив сроком в "
            f"<code>{days} {plural_word(days, ('день', 'дня', 'дней'))}</code> (<code>"
            f"{formatts(start.timestamp())} - {formatts(end.timestamp())}</code>).",
        )
    except Exception:
        text = "⚠️ Пользователя не удалось уведомить.\n" + text
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.usersinactiveset(),
        text=text,
    )
    await state.clear()
    await state.update_data(
        msg=msg, w=w, user=f"{sla} {user.nickname}", uid=user.get_id(), p=p
    )
    sheets.main(composition=True, inactives=True)


@router.message(states.UsersInactive.remove)
async def usersinactiverm(message: Message, state: FSMContext):
    await message.delete()

    data = message.text.strip().replace(" - ", " ").split()
    user = Users.get_or_none(Users.nickname == data[0])
    admin = Users.get(Users.telegram_id == message.from_user.id)
    if (
        user is None
        or not user.inactiveend
        or user.inactiveend < time.time()
        or not checkrole(admin, user)
    ):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text="⚠️ Неверные данные или у пользователя нет действующего неактива.\nВведите никнейм:",
        )
        await state.update_data(msg=msg)
        return
    Inactives.delete().where(
        Inactives.nickname == user.nickname,
        Inactives.start == formatts(user.inactivestart),
        Inactives.end == formatts(user.inactiveend),
    ).execute()
    user.inactivestart = None
    user.inactiveend = None
    user.save()
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id={admin.telegram_id}">'
            f"{admin.nickname}</a> снял вам действующий неактив.",
        )
    except Exception:
        pass
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f'✅ Вы успешно сняли неактив пользователю <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    await state.clear()
    await state.update_data(msg=msg, uid=user.get_id())
    sheets.main(composition=True, inactives=True)


@router.message(states.Inactives.take)
async def inactivestake(message: Message, state: FSMContext):
    await message.delete()

    data = message.text.strip().replace(" - ", " ").split()
    try:
        if len(data) not in (1, 2):
            raise ValueError
        start = datetime.strptime(data[0], "%d.%m.%Y")
        end = datetime.strptime(
            data[1 if len(data) > 2 else 0], "%d.%m.%Y"
        ) + timedelta(1)
        if start.timestamp() > end.timestamp():
            raise ValueError
    except Exception:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text='⚠️ Неверные данные или формат.\nВведите дату неактива (формат: "15.12.2024 - 18.12.2024"):',
        )
        await state.update_data(msg=msg)
        return
    user = Users.get_or_none(Users.telegram_id == message.from_user.id)
    if user.role in SUPPORT_ROLES:
        w = Settings_s.get(Settings_s.setting == "inactiveamnt_asks").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('аск', 'аска', 'асков'))}"
    elif user.fraction:
        w = Settings_l.get(Settings_l.setting == "inactiveamnt_points").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('балл', 'балла', 'баллов'))}"
    else:
        w = Settings_a.get(Settings_a.setting == "inactiveamnt_answers").val * ceil(
            (end.timestamp() - start.timestamp()) / 86400
        )
        p = f"{w} {plural_word(w, ('ответ', 'ответа', 'ответов'))}"
    days = int((end.timestamp() - start.timestamp()) / 86400)
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.inactive_take_yon(),
        text=f"Вы уверены, что хотите взять неактив на {days} {plural_word(days, ('день', 'дня', 'дней'))}?\nУ вас будет снято {p}.",
    )
    await state.clear()
    await state.update_data(msg=msg, w=w, start=start, end=end)


@router.message(states.Inactives.reason)
async def inactivesreason(message: Message, state: FSMContext):
    await message.delete()

    data = await state.get_data()
    user = Users.get(Users.telegram_id == message.from_user.id)
    if user.fraction:
        chat = Chats.get(Chats.setting == "inactive_leaders")
        apa = "баллов"
    elif user.role in SUPPORT_ROLES:
        chat = Chats.get(Chats.setting == "inactive_support")
        apa = "асков"
    else:
        chat = Chats.get(Chats.setting == "inactive_admins")
        apa = "ответов"
    start = formatts(data["start"].timestamp())
    end = formatts(data["end"].timestamp() - 1)
    ir = InactiveRequests.create(
        start=start,
        end=end,
        w=data["w"],
        reason=message.text.strip(),
        tgid=user.telegram_id,
    )
    iid = Inactives.select().order_by(Inactives.id.desc())
    if len(iid) > 0:
        iid = iid[0].get_id() + 1
    else:
        iid = 1
    await message.bot.send_message(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        reply_markup=keyboard.inactiverequest(ir.get_id()),
        text=f"""
📗 [#{str(iid).zfill(4)}] Заявление на неактив — <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n
🕘 Начало неактива: <code>{start}</code>
🕘 Конец неактива: <code>{end}</code>
📚 Причина: <code>{ir.reason}</code>
🟣 Количество {apa}: <code>{ir.w}</code>""",
    )
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f"✅ Заявка №{f'{ir.get_id()}'.zfill(4)} отправлена.",
    )

    await state.clear()
    await state.update_data(msg=msg)


@router.message(states.Reports.sendadditionalreply)  # type: ignore
@media_group_handler(only_album=False)  # type: ignore
async def reportssendadditionalreply(messages: List[Message], state: FSMContext):
    for message in messages:
        try:
            await message.delete()
        except Exception:
            pass

    message: Message = messages[-1]
    user = Users.get(Users.telegram_id == message.from_user.id)
    media = MediaGroupBuilder()
    for obj in messages:
        if obj.photo:
            file_id = obj.photo[-1].file_id
        else:
            file_id: str = getattr(obj, obj.content_type).file_id
        media.add(media=file_id, type=obj.content_type)  # type: ignore
    chat = Chats.get(Chats.setting == "additionalreplies")
    msg = await message.bot.send_media_group(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        media=media.build(),
    )
    await msg[0].reply(
        text=f"""
📗 Дополнительные ответы — <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>
👤 Должность: <code>{user.role}</code>
🕘 Дата: <code>{datetime.now().strftime("%d.%m.%Y / %H:%M")}</code>
""",
        reply_markup=keyboard.additionalreply(user.telegram_id),
    )
    msg = await message.bot.send_message(
        chat_id=message.from_user.id, text="✅ Заявка отправлена."
    )

    await state.clear()
    await state.update_data(msg=msg)


@router.message(states.Reports.sendobjective)  # type: ignore
@media_group_handler(only_album=False)  # type: ignore
async def reportssendobjective(messages: List[Message], state: FSMContext):
    for message in messages:
        try:
            await message.delete()
        except Exception:
            pass

    message = messages[-1]
    if len(messages) > 1 or messages[0].photo is None:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text='⚠️ Вы можете отправить только одну картинку.\nОтправьте скриншот из "/astats":',
        )
        await state.update_data(msg=msg)
        return
    user = Users.get(Users.telegram_id == message.from_user.id)
    chat = Chats.get(Chats.setting == "objective_admins")
    edit = await message.bot.send_photo(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        caption=f"""
📗 Норматив от  — <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>
👤 Должность: <code>{user.role}</code>
🕘 Дата: <code>{datetime.now().strftime("%d.%m.%Y / %H:%M")}</code>
"""
        + (
            "\n❗ Повторный норматив, требуется проверка."
            if Objectives.get_or_none(
                Objectives.telegram_id == user.telegram_id,
                Objectives.time
                > datetime.now().replace(hour=0, minute=0, second=0).timestamp(),
            )
            else ""
        ),
        photo=messages[0].photo[-1].file_id,
        reply_markup=keyboard.reportssendobjective(user.telegram_id),
    )
    Objectives.create(telegram_id=user.telegram_id, time=int(time.time()))
    msg = await message.bot.send_message(
        chat_id=message.from_user.id, text="✅ Заявка отправлена."
    )

    await state.clear()
    await state.update_data(msg=msg, edit=edit)


@router.message(states.Forms.create)
async def formscreate(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip().startswith("/"):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id, text="⚠️ Неверная форма.\nВведите форму:"
        )
        await state.update_data(msg=msg)
        return

    user = Users.get(Users.telegram_id == message.from_user.id)
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.formproof_yon(),
        text="Прикрепить доказательства?",
    )
    await state.clear()
    await state.update_data(
        msg=msg,
        form=message.text.strip()
        + f" by {user.nickname[0].upper()}.{user.nickname.split('_')[-1]}",
    )


@router.message(states.Forms.proof)
async def formsproof(message: Message, state: FSMContext):
    await message.delete()

    if not message.text or not message.text.strip():
        data = None
    else:
        data = [i for i in re.split(r"[, \n]", message.text.strip()) if i != ""]
    if not data or not all(
        validators.url(i) or validators.url("https://" + i) for i in data
    ):
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text="⚠️ Вы не отправили ни одной ссылки.\nОтправьте ссылку(-и, через запятую или пробел) на доказательства:",
        )
        await state.update_data(msg=msg)
        return
    data = [f'<a href="{i}">ссылка №{k + 1}</a>' for k, i in enumerate(data)]
    user = Users.get(Users.telegram_id == message.from_user.id)
    form = (await state.get_data())["form"]
    form = Forms.create(form=form, proofs=f"{data}", fromtgid=user.telegram_id)
    text = f"""
[📗 #{str(form.get_id()).zfill(4)}] Новая форма от <a href="tg://user?id={user.telegram_id}">{user.nickname}</a>\n
<code>{form.form}</code>\n\n 🔎 Доказательства: {", ".join(data)}.
"""
    chat = Chats.get(Chats.setting == "forms")
    await message.bot.send_message(
        chat_id=int(f"-100{chat.chat_id}"),
        message_thread_id=chat.thread_id,
        text=text,
        reply_markup=keyboard.form(form.get_id()),
    )
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f"✅ Форма #{str(form.get_id()).zfill(4)} отправлена.",
    )

    await state.clear()
    await state.update_data(msg=msg)


@router.message(states.Promote.promote)
async def promotepromote(message: Message, state: FSMContext):
    await message.delete()

    user = Users.get_or_none(Users.nickname == message.text.strip())
    if not user:
        msg = await message.bot.send_message(
            chat_id=message.from_user.id,
            text="⚠️ Администратора с таким никнеймом не существует.\nВведите никнейм администратора:",
        )
        await state.update_data(msg=msg)
        return
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        reply_markup=keyboard.promote(),
        text="Выберите новую должность:",
    )
    await state.clear()
    await state.update_data(msg=msg, uid=user.telegram_id)


@router.message(states.Stats.remove)
async def statsremove(message: Message, state: FSMContext):
    await message.delete()

    user = Users.get_by_id((await state.get_data())["user"])
    reason = message.text.strip()
    admin = Users.get(Users.telegram_id == message.from_user.id)
    if admin.fraction:
        struct = "l"
    elif admin.role in SUPPORT_ROLES:
        struct = "s"
    else:
        struct = "a"
    Removed.create(
        nickname=user.nickname,
        role=user.role,
        appointed=user.appointed,
        name=user.name,
        age=calcage(user.age),
        city=user.city,
        discord_id=user.discord_id,
        telegram_id=user.telegram_id,
        reason=reason,
        forum=user.forum,
        whoremoved=admin.nickname,
        vk=user.vk,
        date=formatts(time.time()),
        fraction=user.fraction,
        struct=struct,
    ).save()
    user.delete_instance()
    msg = await message.bot.send_message(
        chat_id=message.from_user.id,
        text=f"✅ Вы успешно сняли пользователя "
        f'<a href="tg://user?id={user.telegram_id}">{user.nickname}</a>.',
    )
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f'📕 Администратор <a href="tg://user?id={admin.telegram_id}">{admin.nickname}</a> снял вас с '
            f"должности.",
        )
    except Exception:
        pass
    await state.clear()
    await state.update_data(msg=msg)
    sheets.main(composition=True, removed=True)
