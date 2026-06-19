from aiogram.fsm.state import State, StatesGroup


class Inactives(StatesGroup):
    take = State()
    reason = State()


class Reports(StatesGroup):
    sendobjective = State()
    sendobjectivew = State()
    sendobjectivewa = State()
    sendadditionalreply = State()
    sendadditionalreplyw = State()


class Forms(StatesGroup):
    create = State()
    proof = State()


class Punishments(StatesGroup):
    v = State()
    w = State()
    r = State()


class APA(StatesGroup):
    change = State()


class UsersInactive(StatesGroup):  # noqa
    set = State()
    remove = State()


class Settings(StatesGroup):  # noqa
    setinactiveamnt_asks = State()
    setinactiveamnt_points = State()
    setinactiveamnt_answers = State()
    settransferamnt_d = State()
    settransferamnt_a = State()


class Promote(StatesGroup):
    promote = State()


class ServerChats(StatesGroup):
    forms = State()
    objective_admins = State()
    additionalreplies = State()
    inactive_support = State()
    inactive_leaders = State()
    inactive_admins = State()
    coins = State()
    punishments = State()


class ServerSheets(StatesGroup):
    s = State()
    L = State()
    a = State()


class Stats(StatesGroup):
    remove = State()


class RemoveLeader(StatesGroup):
    reason = State()


class Appoint(StatesGroup):
    s = State()
    L = State()
    a = State()


class Swatchers(StatesGroup):
    add = State()
    rem = State()


class Coins(StatesGroup):
    change = State()


class PunishmentsMenu(StatesGroup):
    reason = State()
