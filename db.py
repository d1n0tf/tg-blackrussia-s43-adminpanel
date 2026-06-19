import time

from peewee import (
    AutoField,
    BigIntegerField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from config import DATABASE

dbhandle = SqliteDatabase(DATABASE)


def current_timestamp() -> int:
    return int(time.time())


class Users(Model):
    nickname = TextField()
    role = TextField(null=True)
    fraction = TextField(null=True)
    appointed = BigIntegerField()
    promoted = BigIntegerField(null=True)
    objective_completed = BigIntegerField(null=True, default=0)
    apa = BigIntegerField(default=0)
    rebuke = BigIntegerField(default=0)
    warn = BigIntegerField(default=0)
    verbal = BigIntegerField(default=0)
    inactivestart = BigIntegerField(null=True)
    inactiveend = BigIntegerField(null=True)
    name = TextField()
    age = BigIntegerField()
    city = TextField()
    discord_id = BigIntegerField()
    telegram_id = BigIntegerField()
    forum = TextField()
    vk = TextField()
    coins = IntegerField(default=0)
    coins_last_spend = BigIntegerField(default=0)

    class Meta:
        database = dbhandle
        table_name = "users"


class Fractions(Model):
    name = TextField()
    nickname = TextField()
    trust9 = TextField()
    online = BigIntegerField()
    workers = BigIntegerField()
    lastupdate = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "fractions"


class Removed(Model):
    nickname = TextField()
    role = TextField(null=True)
    fraction = TextField(null=True)
    appointed = BigIntegerField()
    name = TextField()
    age = BigIntegerField()
    city = TextField()
    discord_id = BigIntegerField()
    telegram_id = BigIntegerField()
    forum = TextField()
    vk = TextField()
    whoremoved = TextField()
    reason = TextField(null=True)
    date = TextField()
    struct = TextField()

    class Meta:
        database = dbhandle
        table_name = "removed"


class Inactives(Model):
    id = AutoField()
    nickname = TextField()
    role = TextField(null=True)
    fraction = TextField(null=True)
    start = TextField()
    end = TextField()
    status = TextField()
    reason = TextField(null=True)
    requested_by = BigIntegerField(null=True)
    processed_by = BigIntegerField(null=True)
    processed_at = BigIntegerField(null=True)
    process_comment = TextField(null=True)
    request_id = IntegerField(null=True)
    penalty_amount = IntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "inactives"


class Chats(Model):
    setting = TextField()
    chat_id = BigIntegerField()
    thread_id = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "chats"


class Sheets(Model):
    setting = TextField()
    val = TextField()

    class Meta:
        database = dbhandle
        table_name = "sheets"


class Settings_s(Model):  # noqa
    setting = TextField()
    val = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "settingss"


class Settings_l(Model):  # noqa
    setting = TextField()
    val = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "settingsl"


class Settings_a(Model):  # noqa
    setting = TextField()
    val = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "settingsa"


class Forms(Model):
    form = TextField()
    proofs = TextField(null=True)
    fromtgid = BigIntegerField()
    status = TextField(null=True)
    processed_by = BigIntegerField(null=True)
    processed_at = BigIntegerField(null=True)
    result = TextField(null=True)
    created_at = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "forms"


class InactiveRequests(Model):
    tgid = TextField()
    reason = TextField()
    start = TextField()
    end = TextField()
    w = BigIntegerField()
    status = TextField(null=True)
    processed_by = BigIntegerField(null=True)
    processed_at = BigIntegerField(null=True)
    process_comment = TextField(null=True)
    created_at = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "inactiverequests"


class SpecialAccesses(Model):
    telegram_id = TextField()
    role = TextField()

    class Meta:
        database = dbhandle
        table_name = "specialaccess"


class Objectives(Model):
    telegram_id = TextField()
    time = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "objectives"


class CoinsLog(Model):
    telegram_id = TextField()
    lot_name = TextField()
    date = BigIntegerField()

    class Meta:
        database = dbhandle
        table_name = "coinslog"


class CoinsRequests(Model):
    telegram_id = TextField()
    lot_name = TextField()

    class Meta:
        database = dbhandle
        table_name = "coinsrequests"


class PunishmentsRequests(Model):
    telegram_id = TextField()
    punishment = TextField()
    status = TextField(null=True)
    processed_by = BigIntegerField(null=True)
    processed_at = BigIntegerField(null=True)
    reason = TextField(null=True)
    answers_penalty = IntegerField(null=True)
    created_at = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "punishmentsrequests"


class WebCredentials(Model):
    user = ForeignKeyField(Users, backref="web_credentials", unique=True)
    password_hash = TextField(null=True)
    invite_token = TextField(null=True, unique=True)
    invite_created_by = BigIntegerField(null=True)
    invite_created_at = BigIntegerField(null=True)
    invite_used_at = BigIntegerField(null=True)
    last_login_at = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "webcredentials"


class Reports(Model):
    id = AutoField()
    user = ForeignKeyField(Users, backref="reports")
    report_type = TextField()
    report_date = TextField()
    attachments = TextField(null=True)
    status = TextField(default="pending")
    checked_by = BigIntegerField(null=True)
    result = TextField(null=True)
    credited_amount = IntegerField(default=0)
    counts_for_objective = IntegerField(default=0)
    created_at = BigIntegerField(default=current_timestamp)
    processed_at = BigIntegerField(null=True)

    class Meta:
        database = dbhandle
        table_name = "reports"


class PunishmentEntries(Model):
    id = AutoField()
    user = ForeignKeyField(Users, backref="punishment_entries")
    scope = TextField()
    punishment_type = TextField()
    reason = TextField()
    issued_by = BigIntegerField()
    issued_at = BigIntegerField(default=current_timestamp)
    removed_at = BigIntegerField(null=True)
    removed_by = BigIntegerField(null=True)
    removed_reason = TextField(null=True)
    source = TextField(default="web")

    class Meta:
        database = dbhandle
        table_name = "punishmententries"


ALL_MODELS = (
    Users,
    Fractions,
    Removed,
    Inactives,
    Chats,
    Sheets,
    Settings_s,
    Settings_l,
    Settings_a,
    Forms,
    InactiveRequests,
    SpecialAccesses,
    Objectives,
    CoinsLog,
    CoinsRequests,
    PunishmentsRequests,
    WebCredentials,
    Reports,
    PunishmentEntries,
)


def ensure_columns(table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {
        row[1]
        for row in dbhandle.execute_sql(f'PRAGMA table_info("{table_name}")').fetchall()
    }
    for column_name, ddl in columns.items():
        if column_name not in existing_columns:
            dbhandle.execute_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'
            )


def ensure_index(index_name: str, table_name: str, columns: str) -> None:
    dbhandle.execute_sql(
        f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns})'
    )


def init_db() -> None:
    dbhandle.connect(reuse_if_open=True)
    dbhandle.create_tables(ALL_MODELS)
    ensure_columns(
        "forms",
        {
            "status": "TEXT",
            "processed_by": "INTEGER",
            "processed_at": "INTEGER",
            "result": "TEXT",
            "created_at": "INTEGER",
        },
    )
    ensure_columns(
        "inactiverequests",
        {
            "status": "TEXT",
            "processed_by": "INTEGER",
            "processed_at": "INTEGER",
            "process_comment": "TEXT",
            "created_at": "INTEGER",
        },
    )
    ensure_columns(
        "inactives",
        {
            "requested_by": "INTEGER",
            "processed_by": "INTEGER",
            "processed_at": "INTEGER",
            "process_comment": "TEXT",
            "request_id": "INTEGER",
            "penalty_amount": "INTEGER",
        },
    )
    ensure_columns(
        "punishmentsrequests",
        {
            "status": "TEXT",
            "processed_by": "INTEGER",
            "processed_at": "INTEGER",
            "reason": "TEXT",
            "answers_penalty": "INTEGER",
            "created_at": "INTEGER",
        },
    )
    dbhandle.execute_sql("UPDATE forms SET status = 'legacy' WHERE status IS NULL")
    dbhandle.execute_sql(
        "UPDATE inactiverequests SET status = 'pending' WHERE status IS NULL"
    )
    dbhandle.execute_sql(
        "UPDATE punishmentsrequests SET status = 'pending' WHERE status IS NULL"
    )
    ensure_index("idx_users_telegram_id", "users", '"telegram_id"')
    ensure_index("idx_users_nickname", "users", '"nickname"')
    ensure_index("idx_removed_struct", "removed", '"struct"')
    ensure_index("idx_inactives_nickname", "inactives", '"nickname"')
    ensure_index("idx_inactives_request_id", "inactives", '"request_id"')
    ensure_index("idx_inactiverequests_tgid_status", "inactiverequests", '"tgid", "status"')
    ensure_index("idx_inactiverequests_period", "inactiverequests", '"tgid", "start", "end"')
    ensure_index("idx_forms_fromtgid_status", "forms", '"fromtgid", "status"')
    ensure_index("idx_punishmentsrequests_tg_status", "punishmentsrequests", '"telegram_id", "status"')
    ensure_index("idx_reports_user_status_type", "reports", '"user_id", "status", "report_type"')
    ensure_index(
        "idx_punishmententries_lookup",
        "punishmententries",
        '"user_id", "punishment_type", "removed_at", "issued_at"',
    )
