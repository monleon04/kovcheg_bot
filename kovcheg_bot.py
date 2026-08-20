from __future__ import annotations

import asyncio
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kovcheg")

LOG_CHANNEL_ID = 765168122583580682
YEAR_SUMMARY_CHANNEL_ID = 1195782317503942797
ADMIN_CODE = "-kovchegadmin"
VOICE_XP_PER_SECOND = 0.75
MAX_LEVEL = 150
MESSAGE_COOLDOWN = 5 * 60
DATA_VERSION = 3

LEVEL_ROLES = [
    "💦спущенка💦", "🧌гретчин🧌", "🎤 макан🎤", "🧽пизденочка🧽",
    "🦑 днище🦑", "🏳️‍🌈 гомосикс🏳️‍🌈", "🐦‍🔥покемон🐦‍🔥", "🍑впопикс🍑",
    "🚬барыга🚬", "💃 королева дранок💃", "🥋джедай🥋", "☂️хранитель☂️",
    "♠️темный рыцарь♠️", "𖤍 викинг 𖤍", "🛡️ титан 🛡️",
]

ENTERPRISES = {
    1: {"income": 300, "cost": 250_000},
    2: {"income": 350, "cost": 500_000},
    3: {"income": 400, "cost": 1_000_000},
    4: {"income": 450, "cost": 1_500_000},
    5: {"income": 500, "cost": 2_000_000},
}

UNIT_COSTS = {
    "swordsmen": ("мечник", 50),
    "archers": ("лучник", 45),
    "siege": ("осадное орудие", 150),
    "trebuchets": ("требушет", 300),
    "cavalry": ("конница", 180),
    "marines": ("морской десант", 240),
}

IDEOLOGIES = {
    "democracy": {
        "name": "Демократия", "social": 12, "trade": 0.15, "production": 0,
        "war": -0.10, "defense": 0.15, "fatigue": 1.35,
        "description": "Сильная социалка и торговля, но война требует общественного одобрения."
    },
    "communism": {
        "name": "Коммунизм", "social": -8, "trade": -0.05, "production": 0.20,
        "war": 0.12, "defense": 0.05, "fatigue": 0.90,
        "description": "Больше производства и военная мобилизация ценой социальной напряжённости."
    },
    "fascism": {
        "name": "Фашизм", "social": -18, "trade": -0.10, "production": 0.15,
        "war": 0.22, "defense": 0.08, "fatigue": 0.72,
        "description": "Сильная война и производство; война временно сглаживает внутренние дебафы."
    },
}
MERCENARY_COMPANIES = {
    "viking": ("Викинг-Молот", 8_000, 0.18, 2_500),
    "blackwater": ("Чёрный Берег", 15_000, 0.30, 5_500),
    "red_legion": ("Красный Легион", 28_000, 0.48, 10_000),
    "sky_guard": ("Небесная Гвардия", 45_000, 0.72, 18_000),
}

ACTIVE_COUNTRIES = [
    ("kingdom_bog", "Королевство — Бог", "Ковчег-Сити", 3_490_000, 35, 10_000, 290_000),
    ("united_hell", "Объединённые Силы Ада", "Пердянск", 2_900_000, 40, 10_000, 175_000),
    ("military_theocracy", "Теократия Милитаристкий Союз", "Копейск", 2_950_000, 36, 10_000, 474_000),
    ("republic_bredy", "Республика Бреды", "Асгард", 3_060_000, 36, 10_000, 233_000),
    ("uganda_union", "Племенной Союз Уганда Блядская", "Стойло", 3_300_000, 38, 10_000, 617_000),
    ("criminal_theocracy", "Теократия Криминальные Кайфули", "ЧКПЗ", 2_600_000, 24, 10_000, 113_000),
    ("honduras_federation", "Федерация Гондурас", "гАвно", 1_560_000, 20, 10_000, 0),
    ("beer_union", "Пивной Союз Дикая Охота Крепкая", "Алконавск", 1_600_000, 17, 10_000, 3_355),
]
PASSIVE_NAMES = [
    "Федерация Полуфабрикат", "Фрутопрайд", "Племенной Союз Вор Членов",
    "Федерация Мавыга", "Королевство Биполерка", "Республика Скайнет",
    "Империя Булат", "Республика Французики", "Теократия Гооол",
    "Республика Соник", "Федерация Остров Эпштейна",
]
ALL_COUNTRIES: dict[str, dict] = {
    key: {
        "key": key, "name": name, "capital": capital, "population": population,
        "provinces": provinces, "army": army, "treasury": treasury, "active": 1,
    }
    for key, name, capital, population, provinces, army, treasury in ACTIVE_COUNTRIES
}
for index, name in enumerate(PASSIVE_NAMES, 1):
    ALL_COUNTRIES[f"passive_{index}"] = {
        "key": f"passive_{index}", "name": name, "capital": "Неизвестная столица",
        "population": 1_000_000 + index * 37_000, "provinces": 12 + index,
        "army": 5_000, "treasury": 25_000 + index * 10_000, "active": 0,
    }
ACTIVE_CHOICES = [
    app_commands.Choice(name=item[1][:100], value=item[0]) for item in ACTIVE_COUNTRIES
]
ALL_CHOICES = ACTIVE_CHOICES + [
    app_commands.Choice(name=item["name"][:100], value=item["key"])
    for item in ALL_COUNTRIES.values() if not item["active"]
]


def fmt(value: int | float) -> str:
    return f"{int(value):,}".replace(",", " ")


def step_xp(level: int) -> int:
    """Increasing XP intervals; later levels deliberately take much longer."""
    return round(2_500 * (level ** 1.55))


XP_THRESHOLDS = [0]
for level in range(1, MAX_LEVEL):
    XP_THRESHOLDS.append(XP_THRESHOLDS[-1] + step_xp(level))


def level_for_xp(xp: float) -> int:
    current = 1
    for index, threshold in enumerate(XP_THRESHOLDS, 1):
        if xp >= threshold:
            current = index
        else:
            break
    return min(current, MAX_LEVEL)


def country_data(key: str) -> dict:
    return ALL_COUNTRIES.get(key, {"name": key, "capital": "—"})  # only display fallback


class Database:
    def __init__(self, path: str = "kovcheg.sqlite3"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self._bootstrap()

    def _bootstrap(self) -> None:
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        current = self.one("SELECT value FROM meta WHERE key = 'data_version'")
        if not current or int(current["value"]) < DATA_VERSION:
            # This is the requested major reset. It runs once, then the new state persists.
            for table in ("users", "countries", "wars", "relations", "alliances",
                          "alliance_members", "alliance_invites", "repairs"):
                self.db.execute(f"DROP TABLE IF EXISTS {table}")
            self.db.execute("DELETE FROM meta")
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES ('data_version', ?)", (str(DATA_VERSION),)
            )
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                xp REAL NOT NULL DEFAULT 0, coins INTEGER NOT NULL DEFAULT 0,
                voice_seconds INTEGER NOT NULL DEFAULT 0, messages INTEGER NOT NULL DEFAULT 0,
                last_message_reward INTEGER NOT NULL DEFAULT 0,
                country_key TEXT, gamba_count INTEGER NOT NULL DEFAULT 0,
                year_xp REAL NOT NULL DEFAULT 0, year_voice_seconds INTEGER NOT NULL DEFAULT 0,
                year_messages INTEGER NOT NULL DEFAULT 0, year_wins INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS countries (
                guild_id INTEGER NOT NULL, country_key TEXT NOT NULL,
                name TEXT NOT NULL, capital TEXT NOT NULL, population INTEGER NOT NULL,
                max_provinces INTEGER NOT NULL, provinces INTEGER NOT NULL,
                treasury INTEGER NOT NULL, active INTEGER NOT NULL, owner_id INTEGER,
                army INTEGER NOT NULL, morale INTEGER NOT NULL DEFAULT 100,
                swordsmen INTEGER NOT NULL DEFAULT 0, archers INTEGER NOT NULL DEFAULT 0,
                siege INTEGER NOT NULL DEFAULT 0, trebuchets INTEGER NOT NULL DEFAULT 0,
                cavalry INTEGER NOT NULL DEFAULT 0, marines INTEGER NOT NULL DEFAULT 0,
                fleet INTEGER NOT NULL DEFAULT 0, shipyard INTEGER NOT NULL DEFAULT 0,
                generals INTEGER NOT NULL DEFAULT 0, industry_level INTEGER NOT NULL DEFAULT 0,
                capital_fort INTEGER NOT NULL DEFAULT 0, province_fort INTEGER NOT NULL DEFAULT 0,
                conquered_provinces INTEGER NOT NULL DEFAULT 0,
                last_income_at REAL NOT NULL DEFAULT 0,
                ideology TEXT NOT NULL DEFAULT 'democracy',
                quality_of_life INTEGER NOT NULL DEFAULT 60,
                approval INTEGER NOT NULL DEFAULT 60,
                crime INTEGER NOT NULL DEFAULT 15,
                stability INTEGER NOT NULL DEFAULT 70,
                last_social_at REAL NOT NULL DEFAULT 0,
                war_exhaustion INTEGER NOT NULL DEFAULT 0,
                active_party TEXT NOT NULL DEFAULT 'Гражданская коалиция',
                PRIMARY KEY (guild_id, country_key)
            );
            CREATE TABLE IF NOT EXISTS wars (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                attacker TEXT NOT NULL, defender TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', channel_id INTEGER,
                pending_side TEXT, pending_troops INTEGER, pending_target TEXT,
                pending_at REAL, attacker_stance TEXT DEFAULT 'unknown',
                defender_stance TEXT DEFAULT 'unknown', defender_bonus INTEGER DEFAULT 0,
                attacker_bonus INTEGER DEFAULT 0, province_wins INTEGER DEFAULT 0,
                peace_attacker INTEGER DEFAULT 0, peace_defender INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS relations (
                guild_id INTEGER NOT NULL, country_a TEXT NOT NULL, country_b TEXT NOT NULL,
                relation_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY (guild_id, country_a, country_b, relation_type)
            );
            CREATE TABLE IF NOT EXISTS alliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                name TEXT NOT NULL, owner_country TEXT NOT NULL, tax_amount INTEGER DEFAULT 0,
                last_tax_at REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS alliance_members (
                alliance_id INTEGER NOT NULL, country_key TEXT NOT NULL,
                PRIMARY KEY (alliance_id, country_key)
            );
            CREATE TABLE IF NOT EXISTS alliance_invites (
                alliance_id INTEGER NOT NULL, country_key TEXT NOT NULL,
                PRIMARY KEY (alliance_id, country_key)
            );
            CREATE TABLE IF NOT EXISTS mercenary_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                country_key TEXT NOT NULL, company_key TEXT NOT NULL,
                units INTEGER NOT NULL, power REAL NOT NULL,
                daily_cost INTEGER NOT NULL, hired_at REAL NOT NULL,
                expires_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS political_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                country_key TEXT NOT NULL, name TEXT NOT NULL, effect TEXT NOT NULL,
                support INTEGER NOT NULL DEFAULT 10, created_at REAL NOT NULL,
                ideology TEXT NOT NULL DEFAULT 'democracy', leader_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS alliance_roles (
                alliance_id INTEGER NOT NULL, country_key TEXT NOT NULL,
                role TEXT NOT NULL, PRIMARY KEY (alliance_id, country_key)
            );
            CREATE TABLE IF NOT EXISTS repairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
                country_key TEXT NOT NULL, ready_at REAL NOT NULL
            );
            """
        )
        # Migrations are additive: existing game worlds are not wiped on upgrade.
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(alliances)").fetchall()}
        for name, definition in (
            ("goal_name", "TEXT NOT NULL DEFAULT ''"),
            ("goal_treasury", "INTEGER NOT NULL DEFAULT 0"),
            ("goal_reward", "INTEGER NOT NULL DEFAULT 0"),
            ("goal_progress", "INTEGER NOT NULL DEFAULT 0"),
            ("shared_army", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                self.db.execute(f"ALTER TABLE alliances ADD COLUMN {name} {definition}")
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(countries)").fetchall()}
        for name, definition in (
            ("ideology", "TEXT NOT NULL DEFAULT 'democracy'"),
            ("quality_of_life", "INTEGER NOT NULL DEFAULT 60"),
            ("approval", "INTEGER NOT NULL DEFAULT 60"),
            ("crime", "INTEGER NOT NULL DEFAULT 15"),
            ("stability", "INTEGER NOT NULL DEFAULT 70"),
            ("last_social_at", "REAL NOT NULL DEFAULT 0"),
            ("war_exhaustion", "INTEGER NOT NULL DEFAULT 0"),
            ("active_party", "TEXT NOT NULL DEFAULT 'Гражданская коалиция'"),
            ("vector_change_at", "REAL NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                self.db.execute(f"ALTER TABLE countries ADD COLUMN {name} {definition}")
        movement_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(political_movements)").fetchall()}
        for name, definition in (
            ("ideology", "TEXT NOT NULL DEFAULT 'democracy'"),
            ("leader_id", "INTEGER"),
        ):
            if name not in movement_columns:
                self.db.execute(f"ALTER TABLE political_movements ADD COLUMN {name} {definition}")
        self.db.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        cursor = self.db.execute(query, params)
        self.db.commit()
        return cursor

    def one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.db.execute(query, params).fetchone()

    def all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.db.execute(query, params).fetchall()

    def ensure_user(self, guild_id: int, user_id: int) -> sqlite3.Row:
        self.execute("INSERT OR IGNORE INTO users (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        return self.one("SELECT * FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))

    def ensure_guild(self, guild_id: int) -> None:
        now = time.time()
        for data in ALL_COUNTRIES.values():
            self.execute(
                """
                INSERT OR IGNORE INTO countries
                (guild_id, country_key, name, capital, population, max_provinces, provinces,
                 treasury, active, army, last_income_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, data["key"], data["name"], data["capital"], data["population"],
                 data["provinces"], data["provinces"], data["treasury"], data["active"],
                 data["army"], now),
            )

    def country_for_user(self, guild_id: int, user_id: int) -> Optional[sqlite3.Row]:
        return self.one(
            """SELECT c.* FROM countries c JOIN users u
               ON u.guild_id = c.guild_id AND u.country_key = c.country_key
               WHERE u.guild_id = ? AND u.user_id = ?""", (guild_id, user_id)
        )

    def sync_owner_balance(self, guild_id: int, country_key: str) -> Optional[sqlite3.Row]:
        country = self.one(
            "SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild_id, country_key)
        )
        if country and country["owner_id"]:
            user = self.ensure_user(guild_id, country["owner_id"])
            if user["coins"] != country["treasury"]:
                self.execute(
                    "UPDATE countries SET treasury = ? WHERE guild_id = ? AND country_key = ?",
                    (user["coins"], guild_id, country_key),
                )
                country = self.one(
                    "SELECT * FROM countries WHERE guild_id = ? AND country_key = ?",
                    (guild_id, country_key),
                )
        return country

    def change_account(self, guild_id: int, country_key: str, delta: int) -> bool:
        country = self.sync_owner_balance(guild_id, country_key)
        if not country or not country["owner_id"] or country["treasury"] + delta < 0:
            return False
        self.execute(
            "UPDATE users SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
            (delta, guild_id, country["owner_id"]),
        )
        self.execute(
            "UPDATE countries SET treasury = treasury + ? WHERE guild_id = ? AND country_key = ?",
            (delta, guild_id, country_key),
        )
        return True

    def country_relations(self, guild_id: int, key: str, relation_type: str) -> list[sqlite3.Row]:
        return self.all(
            """SELECT * FROM relations WHERE guild_id = ? AND relation_type = ?
               AND status = 'accepted' AND (country_a = ? OR country_b = ?)""",
            (guild_id, relation_type, key, key),
        )


class KovchegBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.db = Database()
        self.voice_sessions: dict[tuple[int, int], float] = {}
        self.synced = False
        self.last_summary_year: dict[int, int] = {}
        self.last_reset_year: dict[int, int] = {}

    async def setup_hook(self):
        await self.add_cog(GameCog(self))
        self.voice_tick.start()
        self.economy_tick.start()
        self.annual_tick.start()

    async def send_system(self, guild: Optional[discord.Guild], title: str, text: str,
                          color: discord.Color = discord.Color.blurple()):
        if not guild:
            return
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=discord.Embed(title=title, description=text,
                                                        color=color, timestamp=discord.utils.utcnow()))
            except discord.HTTPException:
                log.exception("Unable to send system notification")

    async def level_role(self, guild: discord.Guild, member: discord.Member, notify: bool = False):
        user = self.db.ensure_user(guild.id, member.id)
        level = level_for_xp(user["xp"])
        role_name = LEVEL_ROLES[(level - 1) // 10]
        target = discord.utils.get(guild.roles, name=role_name)
        if not target:
            await self.send_system(guild, "Роль уровня не найдена",
                                   f"Для {member.mention} отсутствует роль `{role_name}`.", discord.Color.red())
            return
        old = [role for role in member.roles if role.name in LEVEL_ROLES]
        try:
            if target not in member.roles:
                await member.add_roles(target, reason=f"Уровень {level}")
            for role in old:
                if role != target:
                    await member.remove_roles(role, reason="Синхронизация уровня")
            if notify and target not in old:
                await self.send_system(guild, "Повышение уровня",
                                       f"{member.mention} достиг уровня **{level}** и получил роль {role_name}.",
                                       discord.Color.green())
        except discord.Forbidden:
            await self.send_system(guild, "Не удалось изменить роль",
                                   f"Роль `{role_name}` выше роли бота или у бота нет Manage Roles.",
                                   discord.Color.red())

    async def add_voice_xp(self, guild_id: int, user_id: int, seconds: float):
        if seconds <= 0:
            return
        user = self.db.ensure_user(guild_id, user_id)
        before = level_for_xp(user["xp"])
        gained = seconds * VOICE_XP_PER_SECOND
        self.db.execute(
            """UPDATE users SET xp = xp + ?, voice_seconds = voice_seconds + ?,
               year_xp = year_xp + ?, year_voice_seconds = year_voice_seconds + ?
               WHERE guild_id = ? AND user_id = ?""",
            (gained, int(seconds), gained, int(seconds), guild_id, user_id),
        )
        guild = self.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        if guild and member and level_for_xp(user["xp"] + gained) > before:
            await self.level_role(guild, member, True)

    @tasks.loop(seconds=15)
    async def voice_tick(self):
        now = time.time()
        for key, started in list(self.voice_sessions.items()):
            guild = self.get_guild(key[0])
            member = guild.get_member(key[1]) if guild else None
            # A solo AFK voice channel must not generate endless XP.
            if not member or not member.voice or not member.voice.channel or sum(
                1 for item in member.voice.channel.members if not item.bot
            ) < 2:
                self.voice_sessions[key] = now
                continue
            self.voice_sessions[key] = now
            await self.add_voice_xp(key[0], key[1], now - started)

    @voice_tick.before_loop
    async def before_voice(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=1)
    async def economy_tick(self):
        now = time.time()
        for guild in self.guilds:
            self.db.ensure_guild(guild.id)
            # Enterprises pay hourly and trade contracts add +100 per enterprise level.
            for country in self.db.all("SELECT * FROM countries WHERE guild_id = ?", (guild.id,)):
                if country["owner_id"] and country["industry_level"]:
                    elapsed_hours = int((now - country["last_income_at"]) // 3600)
                    if elapsed_hours:
                        ideology = IDEOLOGIES.get(country["ideology"], IDEOLOGIES["democracy"])
                        income = round(ENTERPRISES[country["industry_level"]]["income"] * (1 + ideology["production"]) + (
                            100 if self.db.country_relations(guild.id, country["country_key"], "trade") else 0
                        ) * (1 + ideology["trade"] if self.db.country_relations(guild.id, country["country_key"], "trade") else 1))
                        self.db.change_account(guild.id, country["country_key"], income * elapsed_hours)
                        self.db.execute(
                            "UPDATE countries SET last_income_at = ? WHERE guild_id = ? AND country_key = ?",
                            (country["last_income_at"] + elapsed_hours * 3600, guild.id, country["country_key"]),
                        )
                elif not country["owner_id"]:
                    elapsed_hours = int((now - country["last_income_at"]) // 3600)
                    if elapsed_hours:
                        self.db.execute(
                            "UPDATE countries SET treasury = treasury + ?, last_income_at = ? "
                            "WHERE guild_id = ? AND country_key = ?",
                            (
                                1_000 * elapsed_hours,
                                country["last_income_at"] + elapsed_hours * 3600,
                                guild.id,
                                country["country_key"],
                            ),
                        )
                if country["morale"] < 100:
                    self.db.execute(
                        "UPDATE countries SET morale = MIN(100, morale + 2) WHERE guild_id = ? AND country_key = ?",
                        (guild.id, country["country_key"]),
                    )
                await self.update_social(guild, country)
                await self.expire_mercenaries(guild, country)
            await self.complete_repairs(guild)
            await self.resolve_due_battles(guild)

    async def update_social(self, guild: discord.Guild, country: sqlite3.Row):
        now = time.time()
        if now - country["last_social_at"] < 3600:
            return
        ideology = IDEOLOGIES.get(country["ideology"], IDEOLOGIES["democracy"])
        wars = self.db.one(
            "SELECT COUNT(*) AS n FROM wars WHERE guild_id = ? AND status = 'active' AND (attacker = ? OR defender = ?)",
            (guild.id, country["country_key"], country["country_key"]),
        )["n"]
        exodus = max(0, country["crime"] - 45) + max(0, 55 - country["quality_of_life"])
        exhaustion = min(8, wars * 2 + country["war_exhaustion"] // 12)
        population_delta = int(country["population"] * max(-0.0008, 0.001 + country["quality_of_life"] / 100000 - exodus / 100000))
        approval_delta = ideology["social"] // 6 - wars - country["crime"] // 35
        self.db.execute(
            """UPDATE countries SET population = MAX(1000, population + ?),
               quality_of_life = MAX(0, MIN(100, quality_of_life + ?)),
               approval = MAX(0, MIN(100, approval + ?)),
               stability = MAX(0, MIN(100, (quality_of_life + approval + (100 - crime)) / 3)),
               war_exhaustion = MAX(0, war_exhaustion - 2), last_social_at = ?
               WHERE guild_id = ? AND country_key = ?""",
            (population_delta, 1 if not wars and country["crime"] < 40 else -1,
             approval_delta - exhaustion, now, guild.id, country["country_key"]),
        )
        # Популярность партий меняется сама: совпадение с текущим вектором
        # помогает, а кризисы и войны ускоряют падение поддержки.
        movements = self.db.all(
            "SELECT * FROM political_movements WHERE guild_id = ? AND country_key = ?",
            (guild.id, country["country_key"]),
        )
        for movement in movements:
            drift = random.choice([-2, -1, 0, 0, 1, 2])
            if movement["ideology"] == country["ideology"]:
                drift += 1
            if wars:
                drift -= 1
            self.db.execute(
                "UPDATE political_movements SET support = MAX(0, MIN(100, support + ?)) WHERE id = ?",
                (drift, movement["id"]),
            )
        candidates = self.db.all(
            "SELECT * FROM political_movements WHERE guild_id = ? AND country_key = ? "
            "ORDER BY support DESC LIMIT 2",
            (guild.id, country["country_key"]),
        )
        if candidates and candidates[0]["support"] >= 35 and random.random() < 0.35:
            winner = candidates[0]
            self.db.execute(
                "UPDATE countries SET active_party = ?, ideology = ?, approval = MAX(0, approval - 4) "
                "WHERE guild_id = ? AND country_key = ?",
                (winner["name"], winner["ideology"], guild.id, country["country_key"]),
            )

    async def expire_mercenaries(self, guild: discord.Guild, country: sqlite3.Row):
        contracts = self.db.all(
            "SELECT * FROM mercenary_contracts WHERE guild_id = ? AND country_key = ? AND status = 'active' AND expires_at <= ?",
            (guild.id, country["country_key"], time.time()),
        )
        for contract in contracts:
            self.db.execute("UPDATE countries SET army = MAX(0, army - ?) WHERE guild_id = ? AND country_key = ?",
                            (contract["units"], guild.id, country["country_key"]))
            self.db.execute("UPDATE mercenary_contracts SET status = 'expired' WHERE id = ?", (contract["id"],))

    @economy_tick.before_loop
    async def before_economy(self):
        await self.wait_until_ready()

    async def complete_repairs(self, guild: discord.Guild):
        rows = self.db.all("SELECT * FROM repairs WHERE guild_id = ? AND ready_at <= ?",
                           (guild.id, time.time()))
        for repair in rows:
            self.db.execute(
                "UPDATE countries SET provinces = MIN(max_provinces, provinces + 1) WHERE guild_id = ? AND country_key = ?",
                (guild.id, repair["country_key"]),
            )
            self.db.execute("DELETE FROM repairs WHERE id = ?", (repair["id"],))

    async def resolve_due_battles(self, guild: discord.Guild):
        rows = self.db.all("SELECT * FROM wars WHERE guild_id = ? AND pending_at IS NOT NULL AND pending_at <= ?",
                           (guild.id, time.time()))
        for war in rows:
            await self.resolve_battle(guild, war["id"])

    @tasks.loop(minutes=1)
    async def annual_tick(self):
        now = datetime.now(timezone.utc)
        for guild in self.guilds:
            year = now.year
            if now.month == 12 and now.day == 31 and now.hour == 23 and now.minute >= 55 and self.last_summary_year.get(guild.id) != year:
                await self.post_year_summary(guild, year)
                self.last_summary_year[guild.id] = year
            if now.month == 1 and now.day == 1 and self.last_reset_year.get(guild.id) != year:
                await self.reset_year(guild, year)
                self.last_reset_year[guild.id] = year

    @annual_tick.before_loop
    async def before_annual(self):
        await self.wait_until_ready()

    async def post_year_summary(self, guild: discord.Guild, year: int):
        channel = guild.get_channel(YEAR_SUMMARY_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return
        users = self.db.all("SELECT * FROM users WHERE guild_id = ? ORDER BY year_xp DESC LIMIT 10", (guild.id,))
        lines = [f"**{i}.** <@{row['user_id']}> — {level_for_xp(row['year_xp'])} ур., "
                 f"{row['year_xp']:.0f} XP" for i, row in enumerate(users, 1)]
        voice = self.db.all("SELECT * FROM users WHERE guild_id = ? ORDER BY year_voice_seconds DESC LIMIT 3", (guild.id,))
        chats = self.db.all("SELECT * FROM users WHERE guild_id = ? ORDER BY year_messages DESC LIMIT 3", (guild.id,))
        countries = self.db.all(
            "SELECT * FROM countries WHERE guild_id = ? ORDER BY conquered_provinces DESC, army DESC LIMIT 3",
            (guild.id,),
        )
        await channel.send(
            f"## Итоги {year} — Ковчег открывает летопись года\n\n"
            f"### Уровни и опыт\n{chr(10).join(lines) or 'Нет данных'}\n\n"
            f"### Голосовые часы\n" +
            "\n".join(f"• <@{r['user_id']}> — {r['year_voice_seconds'] // 3600} ч" for r in voice) +
            f"\n\n### Сообщения\n" +
            "\n".join(f"• <@{r['user_id']}> — {fmt(r['year_messages'])}" for r in chats) +
            f"\n\n### Страны года\n" +
            "\n".join(f"• {r['name']} — захвачено провинций: {r['conquered_provinces']}" for r in countries)
        )

    async def reset_year(self, guild: discord.Guild, year: int):
        for table in ("users", "countries", "wars", "relations", "alliances",
                      "alliance_members", "alliance_invites", "repairs"):
            self.db.execute(f"DELETE FROM {table} WHERE guild_id = ?", (guild.id,))
        self.db.ensure_guild(guild.id)
        await self.send_system(guild, "Новый игровой год", f"Начался {year} год. Все показатели пересчитаны с нуля.",
                               discord.Color.gold())

    async def resolve_battle(self, guild: discord.Guild, war_id: int):
        war = self.db.one("SELECT * FROM wars WHERE id = ?", (war_id,))
        if not war or war["status"] != "active" or not war["pending_side"]:
            return
        attacker_key = war["attacker"] if war["pending_side"] == "attacker" else war["defender"]
        defender_key = war["defender"] if war["pending_side"] == "attacker" else war["attacker"]
        attacker = self.db.sync_owner_balance(guild.id, attacker_key)
        defender = self.db.sync_owner_balance(guild.id, defender_key)
        if not attacker or not defender:
            return
        troops = min(war["pending_troops"], attacker["army"])
        attack_units = attacker["swordsmen"] + attacker["archers"] + attacker["cavalry"] + attacker["marines"]
        if attack_units <= 0:
            attack_units = troops
        siege_bonus = attacker["siege"] * 2 + attacker["trebuchets"] * 4
        fleet_bonus = attacker["fleet"] * 0.5 if attacker["shipyard"] else 0
        attacker_ideology = IDEOLOGIES.get(attacker["ideology"], IDEOLOGIES["democracy"])
        defender_ideology = IDEOLOGIES.get(defender["ideology"], IDEOLOGIES["democracy"])
        alliance = self.db.one(
            """SELECT a.* FROM alliances a JOIN alliance_members m ON m.alliance_id = a.id
               WHERE a.guild_id = ? AND m.country_key = ?""", (guild.id, attacker_key))
        shared_army = alliance["shared_army"] if alliance else 0
        defense_bonus = (defender["capital_fort"] if war["pending_target"] == "capital" else defender["province_fort"]) * 0.08
        defense_bonus += (war["defender_bonus"] if war["pending_side"] == "attacker" else war["attacker_bonus"]) * 0.15
        attack_power = (troops + min(shared_army, troops // 2)) * random.uniform(.8, 1.2) * (1 + attacker_ideology["war"])
        attack_power += siege_bonus + fleet_bonus
        defense_power = defender["army"] * (1 + defense_bonus + defender_ideology["defense"]) * (0.75 + defender["morale"] / 400)
        won = attack_power >= defense_power * random.uniform(.72, 1.15)
        attacker_losses = max(1, int(troops * random.uniform(.06, .18)))
        defender_losses = max(1, int(defender["army"] * random.uniform(.04, .14)))
        self.db.execute(
            "UPDATE countries SET army = MAX(0, army - ?), morale = MAX(0, morale - ?) WHERE guild_id = ? AND country_key = ?",
            (attacker_losses, 8 if not won else 5, guild.id, attacker_key),
        )
        self.db.execute(
            "UPDATE countries SET army = MAX(0, army - ?), morale = MAX(0, morale - ?) WHERE guild_id = ? AND country_key = ?",
            (defender_losses, 6 if won else 3, guild.id, defender_key),
        )
        self.db.execute(
            "UPDATE countries SET war_exhaustion = MIN(100, war_exhaustion + ?), approval = MAX(0, approval - ?) "
            "WHERE guild_id = ? AND country_key IN (?, ?)",
            (8 if not won else 4, 5 if not won else 2, guild.id, attacker_key, defender_key),
        )
        target = war["pending_target"]
        message = f"⚔️ **Сражение завершено!**\nПотери: {country_data(attacker_key)['name']} — {fmt(attacker_losses)}, "
        message += f"{country_data(defender_key)['name']} — {fmt(defender_losses)}.\n"
        if won:
            self.db.execute("UPDATE wars SET province_wins = province_wins + 1 WHERE id = ?", (war_id,))
            if target == "province" and war["province_wins"] + 1 >= 3:
                self.db.execute("UPDATE countries SET provinces = MAX(1, provinces - 1) WHERE guild_id = ? AND country_key = ?",
                                 (guild.id, defender_key))
                self.db.execute("UPDATE countries SET conquered_provinces = conquered_provinces + 1 WHERE guild_id = ? AND country_key = ?",
                                 (guild.id, attacker_key))
                repair_cost = 100_000
                repair_paid = False
                if defender["owner_id"]:
                    repair_paid = self.db.change_account(guild.id, defender_key, -repair_cost)
                else:
                    repair_paid = defender["treasury"] >= repair_cost
                    if repair_paid:
                        self.db.execute(
                            "UPDATE countries SET treasury = treasury - ? WHERE guild_id = ? AND country_key = ?",
                            (repair_cost, guild.id, defender_key),
                        )
                if repair_paid:
                    self.db.execute("INSERT INTO repairs (guild_id, country_key, ready_at) VALUES (?, ?, ?)",
                                     (guild.id, defender_key, time.time() + 3600))
                    message += f"🏰 Провинция пала после трёх побед! На восстановление списано {fmt(repair_cost)} кок, срок — 1 час.\n"
                else:
                    message += f"🏚️ Провинция пала после трёх побед, но у страны нет {fmt(repair_cost)} кок на восстановление.\n"
            if target == "capital":
                self.db.execute("UPDATE wars SET status = 'won' WHERE id = ?", (war_id,))
                message += "👑 Столица взята! Война завершена.\n"
                winner = self.db.ensure_user(guild.id, attacker["owner_id"]) if attacker["owner_id"] else None
                if winner:
                    self.db.execute("UPDATE users SET year_wins = year_wins + 1 WHERE guild_id = ? AND user_id = ?",
                                     (guild.id, attacker["owner_id"]))
        if not won and defender["army"] - defender_losses <= 0:
            self.db.execute("UPDATE wars SET status = 'won' WHERE id = ?", (war_id,))
            message += "🏳️ Армия обороны разбита. Война завершена.\n"
        channel = guild.get_channel(war["channel_id"]) or guild.get_channel(LOG_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            await channel.send(message)
        self.db.execute(
            """UPDATE wars SET pending_side = NULL, pending_troops = NULL,
               pending_target = NULL, pending_at = NULL, defender_bonus = 0,
               attacker_bonus = 0 WHERE id = ?""", (war_id,)
        )

    async def on_ready(self):
        for guild in self.guilds:
            self.db.ensure_guild(guild.id)
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        self.voice_sessions.setdefault((guild.id, member.id), time.time())
        if not self.synced:
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            self.synced = True
        log.info("Бот готов: %s", self.user)

    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        user = self.db.ensure_user(message.guild.id, message.author.id)
        self.db.execute("UPDATE users SET messages = messages + 1, year_messages = year_messages + 1 WHERE guild_id = ? AND user_id = ?",
                        (message.guild.id, message.author.id))
        # До выбора страны участник не копит активы.
        if not user["country_key"]:
            return
        if int(time.time()) - user["last_message_reward"] >= MESSAGE_COOLDOWN:
            reward = random.randint(500, 800)
            self.db.change_account(message.guild.id, user["country_key"], reward)
            self.db.execute("UPDATE users SET last_message_reward = ? WHERE guild_id = ? AND user_id = ?",
                            (int(time.time()), message.guild.id, message.author.id))

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        if before.channel is None and after.channel is not None:
            self.voice_sessions[key] = time.time()
        elif before.channel is not None and after.channel is None:
            await self.add_voice_xp(member.guild.id, member.id, time.time() - self.voice_sessions.pop(key, time.time()))
        elif before.channel != after.channel:
            await self.add_voice_xp(member.guild.id, member.id, time.time() - self.voice_sessions.pop(key, time.time()))
            self.voice_sessions[key] = time.time()


class GameCog(commands.Cog):
    def __init__(self, bot: KovchegBot):
        self.bot = bot

    async def guild(self, interaction: discord.Interaction) -> Optional[discord.Guild]:
        if not interaction.guild:
            await interaction.response.send_message("Команда работает только на сервере.", ephemeral=True)
            return None
        self.bot.db.ensure_guild(interaction.guild.id)
        self.bot.db.ensure_user(interaction.guild.id, interaction.user.id)
        return interaction.guild

    async def country(self, interaction: discord.Interaction, owner: bool = False) -> Optional[sqlite3.Row]:
        row = self.bot.db.country_for_user(interaction.guild_id, interaction.user.id)
        if not row:
            await interaction.response.send_message("Сначала выберите страну командой `/vybrat`.", ephemeral=True)
            return None
        if owner and (not row["active"] or row["owner_id"] != interaction.user.id):
            await interaction.response.send_message("Нужна активная страна под вашим управлением.", ephemeral=True)
            return None
        return self.bot.db.sync_owner_balance(interaction.guild_id, row["country_key"])

    async def admin(self, interaction: discord.Interaction, code: str) -> bool:
        guild = await self.guild(interaction)
        if not guild:
            return False
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == guild.owner_id):
            await interaction.response.send_message("Нужны права администратора.", ephemeral=True)
            return False
        if code != ADMIN_CODE:
            await interaction.response.send_message("Неверный защитный код.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="pomosh", description="Показать команды Ковчега")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "**Ковчег — команды**\n"
            "`kartochka`, `balans`, `perevod`, `gamba`, `lideri`\n"
            "`vybrat`, `sostoyanie`, `reyting`, `proverka`\n"
            "`obyavit_voynu`, `napast`, `oborona`, `peregovory`, `mir`, `voyna`\n"
            "`nanat`, `ukrepit`, `predpriyatie`, `verf`, `flot`, `general`\n"
            "`torgovlya`, `torgovlya_prinyat`, `dogovor`\n"
            "`soyuz_sozdat`, `soyuz_priglasit`, `soyuz_prinyat`, `soyuz_vyiti`, "
            "`soyuz_isklyuchit`, `soyuz_nalog`, `soyuz_sobrat`, `soyuz_status`, `soyuz_cel`, "
            "`soyuz_vklad`, `soyuz_nagrada`, `soyuz_rol`, `soyuz_armiya`, `soyuz_zapros`\n"
            "`socialka`, `ideologiya`, `partii`, `dvizhenie`, `prodvinut_partiyu`, "
            "`naemniki`, `naemnik_nanyat`\n"
            "Админ-команды: `admin_balans`, `admin_dobavit_balans`, `admin_xp`, "
            "`admin_uroven`, `admin_armiya`, `admin_moral`, `admin_provincii`, "
            "`admin_predpriyatie`, `admin_dobavit_predpriyatie`, `admin_resursy`, "
            "`admin_naselenie`, `admin_kazna`, `admin_user_stat`, `admin_politika`, "
            "`admin_vektor`, `admin_sbros`.\n"
            "Названия slash-команд оставлены в транслитерации: Discord не принимает кириллицу "
            "в именах application-команд; все описания и параметры переведены на русский."
        )

    @app_commands.command(name="kartochka", description="Показать карточку и единый баланс участника")
    @app_commands.describe(member="Участник")
    async def card(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        guild = await self.guild(interaction)
        if not guild:
            return
        member = member or interaction.user
        user = self.bot.db.ensure_user(guild.id, member.id)
        level = level_for_xp(user["xp"])
        country = self.bot.db.country_for_user(guild.id, member.id)
        next_xp = XP_THRESHOLDS[level] if level < MAX_LEVEL else XP_THRESHOLDS[-1]
        trades = alliances = "Нет"
        if country:
            trade_rows = self.bot.db.country_relations(guild.id, country["country_key"], "trade")
            trades = ", ".join(country_data(r["country_b"] if r["country_a"] == country["country_key"] else r["country_a"])["name"] for r in trade_rows) or "Нет"
            alliance = await self.alliance_row(guild.id, country["country_key"])
            if alliance:
                members = self.bot.db.all(
                    "SELECT country_key FROM alliance_members WHERE alliance_id = ? AND country_key != ?",
                    (alliance["id"], country["country_key"]),
                )
                alliances = alliance["name"] + (
                    "\n" + ", ".join(country_data(row["country_key"])["name"] for row in members)
                    if members else ""
                )
        embed = discord.Embed(title=f"Карточка {member.display_name}", color=discord.Color.blurple())
        embed.add_field(name="Уровень", value=f"{level} / {MAX_LEVEL}")
        embed.add_field(name="Опыт", value=f"{user['xp']:.0f} XP\nДо следующего: {max(0, next_xp - user['xp']):.0f}")
        embed.add_field(name="Единый баланс", value=f"{fmt(user['coins'])} кок")
        embed.add_field(name="Голос", value=f"{user['voice_seconds'] // 3600} ч {(user['voice_seconds'] % 3600) // 60} мин")
        embed.add_field(name="Сообщения", value=fmt(user["messages"]))
        embed.add_field(name="Страна", value=country["name"] if country else "Не выбрана", inline=False)
        embed.add_field(name="Союз", value=alliances, inline=False)
        embed.add_field(name="Торговля", value=trades, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balans", description="Показать единый баланс Ковчег-Коинов")
    @app_commands.describe(member="Участник")
    async def balance(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        guild = await self.guild(interaction)
        if guild:
            member = member or interaction.user
            user = self.bot.db.ensure_user(guild.id, member.id)
            await interaction.response.send_message(f"Баланс {member.mention}: **{fmt(user['coins'])} кок**.")

    @app_commands.command(name="perevod", description="Перевести кок другому участнику")
    @app_commands.describe(member="Получатель", amount="Сумма")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.country(interaction)
        if not source or amount <= 0 or member.bot or member.id == interaction.user.id:
            return
        receiver = self.bot.db.country_for_user(guild.id, member.id)
        if not receiver:
            await interaction.response.send_message("Получатель должен выбрать страну.", ephemeral=True)
            return
        if not self.bot.db.change_account(guild.id, source["country_key"], -amount):
            await interaction.response.send_message("Недостаточно кок.", ephemeral=True)
            return
        self.bot.db.change_account(guild.id, receiver["country_key"], amount)
        await interaction.response.send_message(f"{interaction.user.mention} перевёл {member.mention} **{fmt(amount)} кок**.")

    @app_commands.command(name="vybrat", description="Навсегда выбрать активную страну")
    @app_commands.describe(country="Страна", ideology="Начальный политический вектор")
    @app_commands.choices(country=ACTIVE_CHOICES)
    @app_commands.choices(ideology=[
        app_commands.Choice(name=data["name"], value=key) for key, data in IDEOLOGIES.items()])
    async def choose(self, interaction: discord.Interaction, country: app_commands.Choice[str],
                     ideology: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        user = self.bot.db.ensure_user(guild.id, interaction.user.id)
        if user["country_key"]:
            await interaction.response.send_message("Выбор уже сделан и не меняется.", ephemeral=True)
            return
        selected = self.bot.db.one("SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value))
        if not selected or selected["owner_id"]:
            await interaction.response.send_message("Эта страна уже занята.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE users SET country_key = ?, coins = ? WHERE guild_id = ? AND user_id = ?",
                            (country.value, selected["treasury"], guild.id, interaction.user.id))
        self.bot.db.execute("UPDATE countries SET owner_id = ?, treasury = ?, ideology = ? WHERE guild_id = ? AND country_key = ?",
                            (interaction.user.id, selected["treasury"], ideology.value, guild.id, country.value))
        await self.bot.level_role(guild, interaction.user)
        await interaction.response.send_message(
            f"{interaction.user.mention}, вы выбрали **{selected['name']}**. "
            f"Начальный вектор: **{IDEOLOGIES[ideology.value]['name']}**. "
            f"Ваш стартовый баланс: **{fmt(selected['treasury'])} кок**."
        )

    @app_commands.command(name="sostoyanie", description="Показать состояние страны")
    @app_commands.describe(country="Страна")
    @app_commands.choices(country=ALL_CHOICES)
    async def status(self, interaction: discord.Interaction, country: Optional[app_commands.Choice[str]] = None):
        guild = await self.guild(interaction)
        if not guild:
            return
        row = self.bot.db.country_for_user(guild.id, interaction.user.id) if not country else self.bot.db.one(
            "SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value)
        )
        if not row:
            await interaction.response.send_message("Страна не найдена.", ephemeral=True)
            return
        row = self.bot.db.sync_owner_balance(guild.id, row["country_key"])
        wars = self.bot.db.all("SELECT * FROM wars WHERE guild_id = ? AND status = 'active' AND (attacker = ? OR defender = ?)",
                               (guild.id, row["country_key"], row["country_key"]))
        trades = self.bot.db.country_relations(guild.id, row["country_key"], "trade")
        alliance = await self.alliance_row(guild.id, row["country_key"])
        owner = f"<@{row['owner_id']}>" if row["owner_id"] else "Наместник"
        embed = discord.Embed(title=row["name"], color=discord.Color.dark_gold())
        embed.add_field(name="Управляет", value=owner)
        embed.add_field(name="Столица", value=row["capital"])
        embed.add_field(name="Население", value=fmt(row["population"]))
        ideology = IDEOLOGIES.get(row["ideology"], IDEOLOGIES["democracy"])
        embed.add_field(name="Социалка", value=f"Качество жизни {row['quality_of_life']}%\n"
                        f"Одобрение власти {row['approval']}%\nПреступность {row['crime']}%\n"
                        f"Стабильность {row['stability']}%\nВектор: {ideology['name']}")
        embed.add_field(name="Провинции", value=f"{row['provinces']} / {row['max_provinces']}")
        embed.add_field(name="Казна / баланс", value=f"{fmt(row['treasury'])} кок")
        embed.add_field(name="Армия", value=f"{fmt(row['army'])}\nБоевой дух: {row['morale']}%")
        embed.add_field(name="Состав", value=f"Мечники {fmt(row['swordsmen'])}\nЛучники {fmt(row['archers'])}\nОсадные {fmt(row['siege'])}\nТребушеты {fmt(row['trebuchets'])}")
        embed.add_field(name="Предприятия", value=f"Ур. {row['industry_level']}\nУкрепление столицы {row['capital_fort']}\nПровинции {row['province_fort']}")
        embed.add_field(name="Войны", value=str(len(wars)) if wars else "Нет")
        alliance_text = "Нет"
        if alliance:
            members = self.bot.db.all(
                "SELECT country_key FROM alliance_members WHERE alliance_id = ? AND country_key != ?",
                (alliance["id"], row["country_key"]),
            )
            alliance_text = alliance["name"] + (
                "\n" + ", ".join(country_data(member["country_key"])["name"] for member in members)
                if members else ""
            )
        embed.add_field(name="Союз", value=alliance_text, inline=False)
        embed.add_field(name="Торговые отношения", value=", ".join(country_data(r["country_b"] if r["country_a"] == row["country_key"] else r["country_a"])["name"] for r in trades) or "Нет", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lideri", description="Топ участников сервера по уровню")
    async def server_leaders(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        rows = self.bot.db.all("SELECT * FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT 10", (guild.id,))
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i]} **{i + 1}.** <@{r['user_id']}> — уровень {level_for_xp(r['xp'])}, {r['xp']:.0f} XP"
                 if i < 3 else f"**{i + 1}.** <@{r['user_id']}> — уровень {level_for_xp(r['xp'])}, {r['xp']:.0f} XP"
                 for i, r in enumerate(rows)]
        await interaction.response.send_message("## Лидеры сервера\n" + "\n".join(lines) + "\n\nОпыт для каждого следующего уровня увеличивается.")

    @app_commands.command(name="reyting", description="Рейтинг стран")
    @app_commands.describe(category="Категория")
    @app_commands.choices(category=[
        app_commands.Choice(name="Казна / ВВП", value="treasury"),
        app_commands.Choice(name="Армия", value="army"),
        app_commands.Choice(name="Население", value="population"),
    ])
    async def ranking(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if guild:
            rows = self.bot.db.all(f"SELECT * FROM countries WHERE guild_id = ? ORDER BY {category.value} DESC LIMIT 10", (guild.id,))
            await interaction.response.send_message(f"**Рейтинг: {category.name}**\n" + "\n".join(f"{i}. {r['name']} — {fmt(r[category.value])}" for i, r in enumerate(rows, 1)))

    @app_commands.command(name="socialka", description="Показать демографию, социалку и отношение населения")
    @app_commands.choices(country=ALL_CHOICES)
    async def social_status(self, interaction: discord.Interaction, country: Optional[app_commands.Choice[str]] = None):
        guild = await self.guild(interaction)
        if not guild:
            return
        row = self.bot.db.country_for_user(guild.id, interaction.user.id) if not country else self.bot.db.one(
            "SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value))
        if not row:
            await interaction.response.send_message("Сначала выберите страну.", ephemeral=True)
            return
        ideology = IDEOLOGIES.get(row["ideology"], IDEOLOGIES["democracy"])
        wars = self.bot.db.one("SELECT COUNT(*) AS n FROM wars WHERE guild_id = ? AND status = 'active' AND (attacker = ? OR defender = ?)",
                               (guild.id, row["country_key"], row["country_key"]))["n"]
        await interaction.response.send_message(
            f"## Социальный профиль: {row['name']}\n"
            f"👥 Население: **{fmt(row['population'])}**\n"
            f"🌿 Качество жизни: **{row['quality_of_life']}%** | 🏛️ Одобрение: **{row['approval']}%**\n"
            f"🚨 Преступность: **{row['crime']}%** | ⚖️ Стабильность: **{row['stability']}%**\n"
            f"🧭 Вектор: **{ideology['name']}**\n{ideology['description']}\n"
            f"🔥 Активных войн: **{wars}**, усталость: **{row['war_exhaustion']}%**")

    @app_commands.command(name="ideologiya", description="Выбрать политический вектор страны")
    @app_commands.choices(ideology=[
        app_commands.Choice(name=data["name"], value=key) for key, data in IDEOLOGIES.items()])
    async def ideology(self, interaction: discord.Interaction, ideology: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        if not source:
            return
        if source["ideology"] == ideology.value:
            await interaction.response.send_message("Этот политический вектор уже установлен.", ephemeral=True)
            return
        if time.time() - source["vector_change_at"] < 7 * 24 * 3600:
            await interaction.response.send_message("Менять вектор можно не чаще одного раза в 7 дней.", ephemeral=True)
            return
        if source["stability"] < 25:
            await interaction.response.send_message("Стабильность слишком низкая для смены режима.", ephemeral=True)
            return
        party = self.bot.db.one(
            "SELECT * FROM political_movements WHERE guild_id = ? AND country_key = ? "
            "AND ideology = ? ORDER BY support DESC LIMIT 1",
            (guild.id, source["country_key"], ideology.value),
        )
        if not party or party["support"] < 30:
            await interaction.response.send_message(
                "Нужна партия с выбранным вектором и поддержкой не менее 30%. "
                "Создайте её через `/dvizhenie` или продвигайте через `/prodvinut_partiyu`.",
                ephemeral=True,
            )
            return
        self.bot.db.execute(
            "UPDATE countries SET ideology = ?, active_party = ?, vector_change_at = ?, "
            "approval = MAX(0, approval - 12), stability = MAX(0, stability - 8) "
            "WHERE guild_id = ? AND country_key = ?",
            (ideology.value, party["name"], time.time(), guild.id, source["country_key"]),
        )
        await interaction.response.send_message(
            f"🏛️ Вектор изменён через одобрение партии **{party['name']}** "
            f"(поддержка {party['support']}%). Одобрение власти снизилось на 12 пунктов.\n"
            f"{IDEOLOGIES[ideology.value]['description']}"
        )

    @app_commands.command(name="partii", description="Показать партии и локальные движения страны")
    async def parties(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.country(interaction) if guild else None
        if not source:
            return
        rows = self.bot.db.all("SELECT * FROM political_movements WHERE guild_id = ? AND country_key = ? ORDER BY support DESC LIMIT 8",
                               (guild.id, source["country_key"]))
        text = f"## Политическая жизнь — {source['name']}\n"
        text += f"Правящая партия: **{source['active_party']}**\n\n"
        text += "\n".join(
            f"• **{r['name']}** — {IDEOLOGIES.get(r['ideology'], IDEOLOGIES['democracy'])['name']}, "
            f"поддержка {r['support']}% ({r['effect']})"
            for r in rows
        ) or "Партий пока нет."
        await interaction.response.send_message(text)

    @app_commands.command(name="dvizhenie", description="Создать локальное политическое движение")
    @app_commands.describe(name="Название партии", effect="Чего требует партия", ideology="Вектор партии")
    @app_commands.choices(ideology=[
        app_commands.Choice(name=data["name"], value=key) for key, data in IDEOLOGIES.items()])
    async def movement(self, interaction: discord.Interaction, name: str, effect: str,
                       ideology: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        if not source:
            return
        count = self.bot.db.one("SELECT COUNT(*) AS n FROM political_movements WHERE guild_id = ? AND country_key = ?",
                                (guild.id, source["country_key"]))["n"]
        if count >= 8:
            await interaction.response.send_message("В стране уже слишком много активных движений.", ephemeral=True)
            return
        self.bot.db.execute(
            "INSERT INTO political_movements (guild_id, country_key, name, effect, ideology, leader_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild.id, source["country_key"], name[:60], effect[:180], ideology.value,
             interaction.user.id, time.time()),
        )
        self.bot.db.execute("UPDATE countries SET approval = MAX(0, approval - 2), stability = MAX(0, stability - 1) WHERE guild_id = ? AND country_key = ?",
                            (guild.id, source["country_key"]))
        await interaction.response.send_message(
            f"📣 Партия **{name[:60]}** создана. Вектор: **{IDEOLOGIES[ideology.value]['name']}**. "
            "Её поддержка будет меняться со временем."
        )

    @app_commands.command(name="prodvinut_partiyu", description="Продвинуть партию и увеличить её популярность")
    @app_commands.describe(name="Название партии", amount="Сколько кок потратить на продвижение")
    async def promote_party(self, interaction: discord.Interaction, name: str, amount: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        if not source:
            return
        amount = max(1_000, min(100_000, amount))
        party = self.bot.db.one(
            "SELECT * FROM political_movements WHERE guild_id = ? AND country_key = ? "
            "AND lower(name) = lower(?)",
            (guild.id, source["country_key"], name[:60]),
        )
        if not party:
            await interaction.response.send_message("Партия не найдена в вашей стране.", ephemeral=True)
            return
        if not self.bot.db.change_account(guild.id, source["country_key"], -amount):
            await interaction.response.send_message("Недостаточно кок.", ephemeral=True)
            return
        points = max(1, min(20, amount // 5_000))
        self.bot.db.execute(
            "UPDATE political_movements SET support = MIN(100, support + ?) WHERE id = ?",
            (points, party["id"]),
        )
        await interaction.response.send_message(
            f"📣 Продвижение партии **{party['name']}** завершено: +{points}% популярности за {fmt(amount)} кок."
        )

    @app_commands.command(name="naemniki", description="Показать доступные ЧВК и контракты")
    async def mercenaries(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.country(interaction) if guild else None
        if not source:
            return
        lines = ["## ЧВК (контракт на 24 часа)"]
        for key, (name, units, power, cost) in MERCENARY_COMPANIES.items():
            lines.append(f"• `{key}` **{name}** — {fmt(units)} бойцов, сила ×{power:.2f}, {fmt(cost)} кок")
        active = self.bot.db.all("SELECT * FROM mercenary_contracts WHERE guild_id = ? AND country_key = ? AND status = 'active'",
                                 (guild.id, source["country_key"]))
        if active:
            lines.append("\nАктивные контракты:\n" + "\n".join(
                f"• {MERCENARY_COMPANIES[r['company_key']][0]} — {fmt(r['units'])} бойцов, до <t:{int(r['expires_at'])}:R>" for r in active))
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="naemnik_nanyat", description="Нанять ЧВК на 24 часа")
    @app_commands.choices(company=[app_commands.Choice(name=data[0], value=key) for key, data in MERCENARY_COMPANIES.items()])
    async def hire_mercenary(self, interaction: discord.Interaction, company: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        if not source:
            return
        name, units, power, cost = MERCENARY_COMPANIES[company.value]
        if not self.bot.db.change_account(guild.id, source["country_key"], -cost):
            await interaction.response.send_message(f"Нужно {fmt(cost)} кок.", ephemeral=True)
            return
        self.bot.db.execute(
            "INSERT INTO mercenary_contracts (guild_id, country_key, company_key, units, power, daily_cost, hired_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild.id, source["country_key"], company.value, units, power, cost, time.time(), time.time() + 86400))
        self.bot.db.execute("UPDATE countries SET army = army + ?, morale = MIN(100, morale + 4) WHERE guild_id = ? AND country_key = ?",
                            (units, guild.id, source["country_key"]))
        await interaction.response.send_message(f"💰 ЧВК **{name}** нанята на сутки. Армия получила **{fmt(units)}** бойцов.")

    @app_commands.command(name="peregovory", description="Показать состояние переговоров по войне")
    async def negotiations(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.country(interaction) if guild else None
        if not source:
            return
        war = self.active_war(guild.id, source["country_key"])
        if not war:
            await interaction.response.send_message("Активных переговоров нет.", ephemeral=True)
            return
        attacker = country_data(war["attacker"])["name"]
        defender = country_data(war["defender"])["name"]
        await interaction.response.send_message(
            f"🕊️ Переговоры: **{attacker}** против **{defender}**.\n"
            f"Причина: {war['reason']}\n"
            f"Голосов за мир: {war['peace_attacker'] + war['peace_defender']} / 2.\n"
            "Выберите `/mir`, чтобы предложить мир, или `/voyna`, чтобы продолжить войну."
        )

    @app_commands.command(name="gamba", description="Шуточная команда про гамбу")
    async def gamba(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        user = self.bot.db.ensure_user(guild.id, interaction.user.id)
        count = user["gamba_count"] + 1
        self.bot.db.execute("UPDATE users SET gamba_count = ? WHERE guild_id = ? AND user_id = ?", (count, guild.id, interaction.user.id))
        phrases = [
            "Какая гамба? Ты че? Абёбаный?",
            "Я не казиныч, хватит писать эту команду. Я похожа на Фрутольва?",
            "Зачем ты опять про эту гамбу пишешь? Иди покрути кейсы, лудик.",
            "Гамба сама себя не проиграет, но я тебе с этим не помогу.",
            "Ковчег-Коины — это экономика, а не казино. Выдохни.",
        ]
        await interaction.response.send_message(phrases[min(count - 1, len(phrases) - 1)])

    @app_commands.command(name="proverka", description="Исправить роли уровней и проверить данные")
    async def check(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Нужны права управления сервером.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        fixed = 0
        for member in guild.members:
            if member.bot:
                continue
            user = self.bot.db.ensure_user(guild.id, member.id)
            before = [r.name for r in member.roles if r.name in LEVEL_ROLES]
            await self.bot.level_role(guild, member)
            if before != [LEVEL_ROLES[(level_for_xp(user["xp"]) - 1) // 10]]:
                fixed += 1
        await interaction.followup.send(f"Проверка завершена. Исправлено ролей: {fixed}.", ephemeral=True)
        await self.bot.send_system(guild, "Администраторская проверка", f"{interaction.user.mention} проверил роли и уровни.")

    async def active_country(self, interaction: discord.Interaction) -> Optional[sqlite3.Row]:
        return await self.country(interaction, owner=True)

    def active_war(self, guild_id: int, key: str) -> Optional[sqlite3.Row]:
        return self.bot.db.one("SELECT * FROM wars WHERE guild_id = ? AND status = 'active' AND (attacker = ? OR defender = ?) ORDER BY id DESC LIMIT 1",
                               (guild_id, key, key))

    @app_commands.command(name="obyavit_voynu", description="Объявить войну и указать причину")
    @app_commands.describe(country="Цель", reason="Причина")
    @app_commands.choices(country=ALL_CHOICES)
    async def declare_war(self, interaction: discord.Interaction, country: app_commands.Choice[str], reason: str):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        target = self.bot.db.one("SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value))
        if not source or not target or source["country_key"] == target["country_key"] or self.active_war(guild.id, source["country_key"]):
            return
        trade = self.bot.db.country_relations(guild.id, source["country_key"], "trade")
        alliance = await self.alliance_row(guild.id, source["country_key"])
        connected_keys = {
            relation["country_b"] if relation["country_a"] == source["country_key"] else relation["country_a"]
            for relation in trade
        }
        if alliance:
            connected_keys.update(
                member["country_key"]
                for member in self.bot.db.all(
                    "SELECT country_key FROM alliance_members WHERE alliance_id = ?",
                    (alliance["id"],),
                )
            )
        if target["country_key"] in connected_keys:
            await interaction.response.send_message(
                "Действующий союз или торговый договор запрещает объявлять войну этой стране.",
                ephemeral=True,
            )
            return
        ideology = IDEOLOGIES.get(source["ideology"], IDEOLOGIES["democracy"])
        if source["ideology"] == "democracy" and source["approval"] < 50:
            await interaction.response.send_message("Демократия не получила одобрение конгресса и общества на войну (нужно 50% одобрения).", ephemeral=True)
            return
        self.bot.db.execute("INSERT INTO wars (guild_id, attacker, defender, reason, channel_id) VALUES (?, ?, ?, ?, ?)",
                            (guild.id, source["country_key"], target["country_key"], reason[:500], interaction.channel_id))
        self.bot.db.execute("UPDATE countries SET approval = MAX(0, approval - 8), war_exhaustion = MIN(100, war_exhaustion + 8) WHERE guild_id = ? AND country_key = ?",
                            (guild.id, source["country_key"]))
        mention = f"<@{target['owner_id']}>" if target["owner_id"] else "Наместник"
        await interaction.response.send_message(f"🚨 {mention}, **{source['name']}** объявляет войну **{target['name']}**!\nПричина: {reason}\nОтправить войска: `/napast`.")

    @app_commands.command(name="napast", description="Отправить войска; бой начнётся через минуту")
    @app_commands.describe(troops="Число войск", target="Цель", stance="Тактика")
    @app_commands.choices(target=[
        app_commands.Choice(name="Провинция", value="province"),
        app_commands.Choice(name="Столица", value="capital"),
    ], stance=[
        app_commands.Choice(name="Осада своей территории", value="defend_own"),
        app_commands.Choice(name="Контратака", value="counter"),
        app_commands.Choice(name="Вторжение на территорию врага", value="invade"),
    ])
    async def attack(self, interaction: discord.Interaction, troops: int, target: app_commands.Choice[str], stance: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source or troops <= 0:
            return
        war = self.active_war(guild.id, source["country_key"])
        if not war or war["pending_at"]:
            await interaction.response.send_message("Нет доступной войны или предыдущий бой ещё готовится.", ephemeral=True)
            return
        target_country = self.bot.db.sync_owner_balance(guild.id, war["defender"] if war["attacker"] == source["country_key"] else war["attacker"])
        if target.value == "capital" and (source["conquered_provinces"] < 5 or source["siege"] + source["trebuchets"] <= 0):
            await interaction.response.send_message("Для атаки столицы нужны 5 захваченных провинций и осадное оружие.", ephemeral=True)
            return
        if troops > source["army"]:
            await interaction.response.send_message("У страны недостаточно войск.", ephemeral=True)
            return
        side = "attacker" if war["attacker"] == source["country_key"] else "defender"
        self.bot.db.execute("UPDATE wars SET pending_side = ?, pending_troops = ?, pending_target = ?, pending_at = ?, "
                            "attacker_stance = CASE WHEN ? = 'attacker' THEN ? ELSE attacker_stance END, "
                            "defender_stance = CASE WHEN ? = 'defender' THEN ? ELSE defender_stance END WHERE id = ?",
                            (side, troops, target.value, time.time() + 60, side, stance.value, side, stance.value, war["id"]))
        await interaction.response.send_message(f"⚔️ Войска выступают через **1 минуту**. Цель: **{target.name}**, тактика: **{stance.name}**.")

    @app_commands.command(name="oborona", description="Выбрать оборону своей территории")
    @app_commands.describe(style="Тактика обороны")
    @app_commands.choices(style=[
        app_commands.Choice(name="Держать провинции", value="hold"),
        app_commands.Choice(name="Контратака", value="counter"),
        app_commands.Choice(name="Выйти навстречу врагу", value="sortie"),
    ])
    async def defense(self, interaction: discord.Interaction, style: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source:
            return
        war = self.active_war(guild.id, source["country_key"])
        if not war or war["defender"] != source["country_key"]:
            await interaction.response.send_message("Оборона доступна стране, на которую напали.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE wars SET defender_bonus = 1, defender_stance = ? WHERE id = ?", (style.value, war["id"]))
        await interaction.response.send_message(f"🛡️ {source['name']} укрепляет позиции: **{style.name}**. Гарнизон получит бонус.")

    async def peace_vote(self, interaction: discord.Interaction, peace: bool):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.country(interaction)
        if not source:
            return
        war = self.active_war(guild.id, source["country_key"])
        if not war:
            await interaction.response.send_message("Активной войны нет.", ephemeral=True)
            return
        field = "peace_attacker" if war["attacker"] == source["country_key"] else "peace_defender"
        self.bot.db.execute(f"UPDATE wars SET {field} = ? WHERE id = ?", (1 if peace else 0, war["id"]))
        updated = self.bot.db.one("SELECT * FROM wars WHERE id = ?", (war["id"],))
        if peace and updated["peace_attacker"] and updated["peace_defender"]:
            self.bot.db.execute("UPDATE wars SET status = 'peace' WHERE id = ?", (war["id"],))
            await interaction.response.send_message("🤝 Обе стороны выбрали мир. Война окончена.")
        else:
            await interaction.response.send_message("Голос записан. " + ("Нужно согласие второй стороны." if peace else "Боевые действия продолжаются."))

    @app_commands.command(name="mir", description="Выбрать мир на переговорах")
    async def peace(self, interaction: discord.Interaction):
        await self.peace_vote(interaction, True)

    @app_commands.command(name="voyna", description="Продолжить войну")
    async def war_continue(self, interaction: discord.Interaction):
        await self.peace_vote(interaction, False)

    @app_commands.command(name="nanat", description="Нанять войска из населения")
    @app_commands.describe(unit="Класс войск", amount="Количество")
    @app_commands.choices(unit=[app_commands.Choice(name=name, value=key) for key, (name, _) in UNIT_COSTS.items()])
    async def recruit(self, interaction: discord.Interaction, unit: app_commands.Choice[str], amount: int):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source or amount <= 0:
            return
        population_cost = amount * (2 if unit.value in ("swordsmen", "archers") else 5)
        name, cost = UNIT_COSTS[unit.value]
        total = amount * cost
        if source["population"] < population_cost or not self.bot.db.change_account(guild.id, source["country_key"], -total):
            await interaction.response.send_message(f"Нужно {fmt(total)} кок и достаточно населения.", ephemeral=True)
            return
        self.bot.db.execute(f"UPDATE countries SET {unit.value} = {unit.value} + ?, population = population - ?, army = army + ? WHERE guild_id = ? AND country_key = ?",
                            (amount, population_cost, amount, guild.id, source["country_key"]))
        await interaction.response.send_message(f"Нанято: **{fmt(amount)} {name}** за **{fmt(total)} кок**.")

    @app_commands.command(name="general", description="Нанять генерала за 50 000 кок")
    async def general(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if source and self.bot.db.change_account(guild.id, source["country_key"], -50_000):
            self.bot.db.execute("UPDATE countries SET generals = generals + 1 WHERE guild_id = ? AND country_key = ?", (guild.id, source["country_key"]))
            await interaction.response.send_message("Генерал нанят. Он даёт бонус армии и осаде столицы.")
        elif source:
            await interaction.response.send_message("Недостаточно кок.", ephemeral=True)

    @app_commands.command(name="verf", description="Построить верфь")
    async def shipyard(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if source and source["shipyard"]:
            await interaction.response.send_message("Верфь уже построена.", ephemeral=True)
        elif source and self.bot.db.change_account(guild.id, source["country_key"], -500_000):
            self.bot.db.execute("UPDATE countries SET shipyard = 1 WHERE guild_id = ? AND country_key = ?", (guild.id, source["country_key"]))
            await interaction.response.send_message("⚓ Верфь построена. Теперь можно строить флот.")
        elif source:
            await interaction.response.send_message("Нужно 500 000 кок.", ephemeral=True)

    @app_commands.command(name="flot", description="Построить корабли на верфи")
    @app_commands.describe(amount="Количество кораблей")
    async def fleet(self, interaction: discord.Interaction, amount: int):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        total = amount * 5_000 if amount > 0 else 0
        if not source or not source["shipyard"]:
            await interaction.response.send_message("Сначала постройте верфь.", ephemeral=True)
        elif not self.bot.db.change_account(guild.id, source["country_key"], -total):
            await interaction.response.send_message(f"Нужно {fmt(total)} кок.", ephemeral=True)
        else:
            self.bot.db.execute("UPDATE countries SET fleet = fleet + ? WHERE guild_id = ? AND country_key = ?", (amount, guild.id, source["country_key"]))
            await interaction.response.send_message(f"Построено кораблей: {fmt(amount)}.")

    @app_commands.command(name="ukrepit", description="Укрепить столицу или провинции")
    @app_commands.describe(location="Место укрепления")
    @app_commands.choices(location=[
        app_commands.Choice(name="Столица", value="capital"),
        app_commands.Choice(name="Провинции", value="province"),
    ])
    async def fortify(self, interaction: discord.Interaction, location: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source:
            return
        cost = 100_000 * (source["capital_fort"] + 1 if location.value == "capital" else source["province_fort"] + 1)
        field = "capital_fort" if location.value == "capital" else "province_fort"
        if self.bot.db.change_account(guild.id, source["country_key"], -cost):
            self.bot.db.execute(f"UPDATE countries SET {field} = {field} + 1 WHERE guild_id = ? AND country_key = ?", (guild.id, source["country_key"]))
            await interaction.response.send_message(f"Укрепления улучшены. Стоимость: {fmt(cost)} кок.")
        else:
            await interaction.response.send_message(f"Нужно {fmt(cost)} кок.", ephemeral=True)

    @app_commands.command(name="predpriyatie", description="Построить предприятие с доходом в час")
    async def enterprise(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source or source["industry_level"] >= 5:
            await interaction.response.send_message("Достигнут максимум 5 уровня.", ephemeral=True)
            return
        next_level = source["industry_level"] + 1
        item = ENTERPRISES[next_level]
        if self.bot.db.change_account(guild.id, source["country_key"], -item["cost"]):
            self.bot.db.execute("UPDATE countries SET industry_level = ?, last_income_at = ? WHERE guild_id = ? AND country_key = ?", (next_level, time.time(), guild.id, source["country_key"]))
            await interaction.response.send_message(f"Предприятие уровня {next_level}: доход **{item['income']} кок/час**, стоимость **{fmt(item['cost'])} кок**.")
        else:
            await interaction.response.send_message(f"Нужно {fmt(item['cost'])} кок.", ephemeral=True)

    @app_commands.command(name="torgovlya", description="Предложить торговый договор")
    @app_commands.describe(country="Страна-партнёр")
    @app_commands.choices(country=ACTIVE_CHOICES)
    async def trade(self, interaction: discord.Interaction, country: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        target = self.bot.db.one("SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value))
        if not source or not target or not target["owner_id"]:
            return
        a, b = sorted((source["country_key"], target["country_key"]))
        self.bot.db.execute("INSERT OR REPLACE INTO relations (guild_id, country_a, country_b, relation_type, status) VALUES (?, ?, ?, 'trade', 'pending')", (guild.id, a, b))
        await interaction.response.send_message(f"📜 <@{target['owner_id']}>, вам предлагают торговый договор от **{source['name']}**. Принять: `/torgovlya_prinyat`.")

    @app_commands.command(name="torgovlya_prinyat", description="Принять торговый договор")
    @app_commands.describe(country="Страна-предложитель")
    @app_commands.choices(country=ACTIVE_CHOICES)
    async def trade_accept(self, interaction: discord.Interaction, country: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        if not guild:
            return
        source = await self.active_country(interaction)
        if not source:
            return
        a, b = sorted((source["country_key"], country.value))
        row = self.bot.db.one("SELECT * FROM relations WHERE guild_id = ? AND country_a = ? AND country_b = ? AND relation_type = 'trade' AND status = 'pending'", (guild.id, a, b))
        if not row:
            await interaction.response.send_message("Предложение не найдено.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE relations SET status = 'accepted' WHERE guild_id = ? AND country_a = ? AND country_b = ? AND relation_type = 'trade'", (guild.id, a, b))
        await interaction.response.send_message("🤝 Торговый договор заключён. Доход предприятий увеличен на 100 кок/час.")

    @app_commands.command(name="dogovor", description="Показать правила договоров")
    async def contract(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.country(interaction) if guild else None
        if source:
            await interaction.response.send_message("Правила: нельзя оскорблять партнёра, объявлять ему войну и писать в чатах имя «Виталя». Нарушения договора ведут к его расторжению администрацией.")

    async def alliance_row(self, guild_id: int, key: str) -> Optional[sqlite3.Row]:
        return self.bot.db.one("SELECT a.* FROM alliances a JOIN alliance_members m ON m.alliance_id = a.id WHERE a.guild_id = ? AND m.country_key = ?", (guild_id, key))

    @app_commands.command(name="soyuz_sozdat", description="Создать союз")
    @app_commands.describe(name="Название")
    async def alliance_create(self, interaction: discord.Interaction, name: str):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        if not source:
            return
        if await self.alliance_row(guild.id, source["country_key"]):
            await interaction.response.send_message("Вы уже состоите в союзе.", ephemeral=True)
            return
        cursor = self.bot.db.execute("INSERT INTO alliances (guild_id, name, owner_country) VALUES (?, ?, ?)", (guild.id, name[:80], source["country_key"]))
        self.bot.db.execute("INSERT INTO alliance_members (alliance_id, country_key) VALUES (?, ?)", (cursor.lastrowid, source["country_key"]))
        await interaction.response.send_message(f"Союз **{name[:80]}** создан.")

    @app_commands.command(name="soyuz_priglasit", description="Пригласить страну в союз")
    @app_commands.describe(country="Страна")
    @app_commands.choices(country=ACTIVE_CHOICES)
    async def alliance_invite(self, interaction: discord.Interaction, country: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        target = self.bot.db.one("SELECT * FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, country.value)) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not source or not alliance or alliance["owner_country"] != source["country_key"] or not target or not target["owner_id"]:
            return
        self.bot.db.execute("INSERT OR IGNORE INTO alliance_invites (alliance_id, country_key) VALUES (?, ?)", (alliance["id"], country.value))
        await interaction.response.send_message(f"📨 <@{target['owner_id']}>, вас приглашают в союз **{alliance['name']}**. Принять: `/soyuz_prinyat`.")

    @app_commands.command(name="soyuz_prinyat", description="Принять приглашение в союз")
    async def alliance_accept(self, interaction: discord.Interaction, alliance_id: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        invite = self.bot.db.one("SELECT * FROM alliance_invites WHERE alliance_id = ? AND country_key = ?", (alliance_id, source["country_key"])) if source else None
        if not invite:
            await interaction.response.send_message("Приглашение не найдено.", ephemeral=True)
            return
        self.bot.db.execute("INSERT OR IGNORE INTO alliance_members (alliance_id, country_key) VALUES (?, ?)", (alliance_id, source["country_key"]))
        self.bot.db.execute("DELETE FROM alliance_invites WHERE alliance_id = ? AND country_key = ?", (alliance_id, source["country_key"]))
        await interaction.response.send_message("Вы вступили в союз.")

    @app_commands.command(name="soyuz_vyiti", description="Выйти из союза")
    async def alliance_leave(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance:
            return
        if alliance["owner_country"] == source["country_key"]:
            await interaction.response.send_message("Организатор не может выйти из союза.", ephemeral=True)
            return
        self.bot.db.execute("DELETE FROM alliance_members WHERE alliance_id = ? AND country_key = ?", (alliance["id"], source["country_key"]))
        await interaction.response.send_message("Вы вышли из союза.")

    @app_commands.command(name="soyuz_isklyuchit", description="Исключить страну из союза")
    @app_commands.describe(country="Страна")
    @app_commands.choices(country=ACTIVE_CHOICES)
    async def alliance_kick(self, interaction: discord.Interaction, country: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or alliance["owner_country"] != source["country_key"]:
            return
        self.bot.db.execute("DELETE FROM alliance_members WHERE alliance_id = ? AND country_key = ?", (alliance["id"], country.value))
        await interaction.response.send_message("Страна исключена из союза.")

    @app_commands.command(name="soyuz_nalog", description="Установить ежемесячный налог союза")
    @app_commands.describe(amount="Кок с участника")
    async def alliance_tax(self, interaction: discord.Interaction, amount: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or alliance["owner_country"] != source["country_key"] or amount < 0:
            return
        self.bot.db.execute("UPDATE alliances SET tax_amount = ? WHERE id = ?", (amount, alliance["id"]))
        await interaction.response.send_message(f"Налог союза: {fmt(amount)} кок в месяц.")

    @app_commands.command(name="soyuz_sobrat", description="Собрать налог союза раз в месяц")
    async def alliance_collect(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or alliance["owner_country"] != source["country_key"]:
            return
        if time.time() - alliance["last_tax_at"] < 30 * 86400:
            await interaction.response.send_message("Собрать налог можно раз в 30 дней.", ephemeral=True)
            return
        members = self.bot.db.all("SELECT country_key FROM alliance_members WHERE alliance_id = ? AND country_key != ?", (alliance["id"], source["country_key"]))
        total = 0
        for member in members:
            target = self.bot.db.sync_owner_balance(guild.id, member["country_key"])
            if target and target["owner_id"]:
                paid = min(target["treasury"], alliance["tax_amount"])
                self.bot.db.change_account(guild.id, member["country_key"], -paid)
                self.bot.db.change_account(guild.id, source["country_key"], paid)
                total += paid
        self.bot.db.execute("UPDATE alliances SET last_tax_at = ? WHERE id = ?", (time.time(), alliance["id"]))
        await interaction.response.send_message(f"Собрано {fmt(total)} кок.")

    @app_commands.command(name="soyuz_status", description="Показать состояние союза")
    async def alliance_status(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance:
            await interaction.response.send_message("Вы не состоите в союзе.")
            return
        members = self.bot.db.all("SELECT country_key FROM alliance_members WHERE alliance_id = ?", (alliance["id"],))
        roles = self.bot.db.all("SELECT * FROM alliance_roles WHERE alliance_id = ?", (alliance["id"],))
        role_text = "\n".join(f"• {country_data(r['country_key'])['name']}: {r['role']}" for r in roles) or "Роли пока не назначены."
        await interaction.response.send_message(
            f"**Союз {alliance['name']}** (ID `{alliance['id']}`)\n"
            f"Организатор: {country_data(alliance['owner_country'])['name']}\n"
            f"Налог: {fmt(alliance['tax_amount'])} кок/месяц\n"
            f"Общая армия: {fmt(alliance['shared_army'])}\n"
            f"Общая цель: {alliance['goal_name'] or 'не задана'} "
            f"({fmt(alliance['goal_progress'])}/{fmt(alliance['goal_treasury'])}, награда {fmt(alliance['goal_reward'])})\n"
            f"Участники:\n" + "\n".join(f"• {country_data(m['country_key'])['name']}" for m in members) +
            f"\n\nРоли:\n{role_text}")

    @app_commands.command(name="soyuz_cel", description="Поставить общую цель союза с наградой")
    @app_commands.describe(name="Цель", amount="Сколько кок нужно собрать", reward="Награда после выполнения")
    async def alliance_goal(self, interaction: discord.Interaction, name: str, amount: int, reward: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or alliance["owner_country"] != source["country_key"] or amount <= 0 or reward < 0:
            await interaction.response.send_message("Только глава союза может задать корректную цель.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE alliances SET goal_name = ?, goal_treasury = ?, goal_progress = 0, goal_reward = ? WHERE id = ?",
                            (name[:100], amount, reward, alliance["id"]))
        await interaction.response.send_message(f"🎯 Общая цель союза **{name[:100]}** установлена: собрать **{fmt(amount)} кок**.")

    @app_commands.command(name="soyuz_vklad", description="Внести кок в общую цель союза")
    @app_commands.describe(amount="Сколько кок внести")
    async def alliance_contribute(self, interaction: discord.Interaction, amount: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or amount <= 0 or not alliance["goal_name"]:
            await interaction.response.send_message("У союза нет активной цели или сумма неверна.", ephemeral=True)
            return
        if not self.bot.db.change_account(guild.id, source["country_key"], -amount):
            await interaction.response.send_message("Недостаточно кок.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE alliances SET goal_progress = goal_progress + ? WHERE id = ?", (amount, alliance["id"]))
        updated = self.bot.db.one("SELECT * FROM alliances WHERE id = ?", (alliance["id"],))
        await interaction.response.send_message(
            f"💠 Внесено {fmt(amount)} кок в цель **{alliance['goal_name']}**. "
            f"Прогресс: {fmt(updated['goal_progress'])} / {fmt(alliance['goal_treasury'])}.")

    @app_commands.command(name="soyuz_nagrada", description="Забрать награду за выполненную цель союза")
    async def alliance_reward(self, interaction: discord.Interaction):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or not alliance["goal_name"] or alliance["goal_progress"] < alliance["goal_treasury"] or alliance["goal_reward"] <= 0:
            await interaction.response.send_message("Цель ещё не выполнена.", ephemeral=True)
            return
        members = self.bot.db.all("SELECT country_key FROM alliance_members WHERE alliance_id = ?", (alliance["id"],))
        share = alliance["goal_reward"] // max(1, len(members))
        for member in members:
            self.bot.db.change_account(guild.id, member["country_key"], share)
        self.bot.db.execute("UPDATE alliances SET goal_name = '', goal_progress = 0, goal_treasury = 0, goal_reward = 0 WHERE id = ?", (alliance["id"],))
        await interaction.response.send_message(f"🎁 Награда получена: каждому участнику начислено **{fmt(share)} кок**.")

    @app_commands.command(name="soyuz_rol", description="Назначить роль участнику союза")
    @app_commands.choices(role=[
        app_commands.Choice(name="Сборщик налогов", value="Сборщик налогов"),
        app_commands.Choice(name="Министр войны", value="Министр войны"),
        app_commands.Choice(name="Дипломат", value="Дипломат"),
    ])
    @app_commands.describe(country="Страна участника", role="Роль")
    @app_commands.choices(country=ACTIVE_CHOICES)
    async def alliance_role(self, interaction: discord.Interaction, country: app_commands.Choice[str], role: app_commands.Choice[str]):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        member = self.bot.db.one("SELECT 1 FROM alliance_members WHERE alliance_id = ? AND country_key = ?",
                                 (alliance["id"], country.value)) if alliance else None
        if not alliance or alliance["owner_country"] != source["country_key"] or not member:
            await interaction.response.send_message("Назначать роли может только глава, и только участнику своего союза.", ephemeral=True)
            return
        self.bot.db.execute("INSERT OR REPLACE INTO alliance_roles (alliance_id, country_key, role) VALUES (?, ?, ?)",
                            (alliance["id"], country.value, role.value))
        await interaction.response.send_message(f"Роль **{role.name}** назначена стране **{country.name}**.")

    @app_commands.command(name="soyuz_armiya", description="Внести войска в общую армию союза")
    @app_commands.describe(amount="Количество войск")
    async def alliance_army(self, interaction: discord.Interaction, amount: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or amount <= 0 or amount > source["army"]:
            await interaction.response.send_message("Недостаточно войск или вы не состоите в союзе.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE countries SET army = army - ? WHERE guild_id = ? AND country_key = ?",
                            (amount, guild.id, source["country_key"]))
        self.bot.db.execute("UPDATE alliances SET shared_army = shared_army + ? WHERE id = ?", (amount, alliance["id"]))
        await interaction.response.send_message(f"🪖 В общую армию союза внесено **{fmt(amount)}** войск.")

    @app_commands.command(name="soyuz_zapros", description="Запросить войска у участников союза")
    @app_commands.describe(amount="Сколько войск запрашивается")
    async def alliance_request(self, interaction: discord.Interaction, amount: int):
        guild = await self.guild(interaction)
        source = await self.active_country(interaction) if guild else None
        alliance = await self.alliance_row(guild.id, source["country_key"]) if source else None
        if not alliance or amount <= 0:
            return
        members = self.bot.db.all("SELECT country_key FROM alliance_members WHERE alliance_id = ? AND country_key != ?",
                                  (alliance["id"], source["country_key"]))
        mentions = [f"<@{self.bot.db.one('SELECT owner_id FROM countries WHERE guild_id = ? AND country_key = ?', (guild.id, m['country_key']))['owner_id']}>"
                    for m in members if self.bot.db.one("SELECT owner_id FROM countries WHERE guild_id = ? AND country_key = ?", (guild.id, m["country_key"]))]
        await interaction.response.send_message(f"📯 **Министр войны** запрашивает **{fmt(amount)}** войск для {source['name']}.\n" + " ".join(mentions))

    async def admin_target(self, guild: discord.Guild, member: discord.Member) -> Optional[sqlite3.Row]:
        row = self.bot.db.country_for_user(guild.id, member.id)
        return row

    @app_commands.command(name="admin_balans", description="Админ: установить единый баланс")
    @app_commands.describe(code="Защитный код", member="Участник", amount="Новый баланс")
    async def admin_balance(self, interaction: discord.Interaction, code: str, member: discord.Member, amount: int):
        if not await self.admin(interaction, code):
            return
        row = await self.admin_target(interaction.guild, member)
        if not row or amount < 0:
            await interaction.response.send_message("У участника нет страны или сумма неверна.", ephemeral=True)
            return
        self.bot.db.execute("UPDATE users SET coins = ? WHERE guild_id = ? AND user_id = ?", (amount, interaction.guild.id, member.id))
        self.bot.db.execute("UPDATE countries SET treasury = ? WHERE guild_id = ? AND country_key = ?", (amount, interaction.guild.id, row["country_key"]))
        await interaction.response.send_message(f"Баланс {member.mention} установлен: {fmt(amount)} кок.", ephemeral=True)

    @app_commands.command(name="admin_dobavit_balans", description="Админ: добавить кок к балансу участника")
    @app_commands.describe(code="Защитный код", member="Участник", amount="Сколько добавить")
    async def admin_add_balance(self, interaction: discord.Interaction, code: str, member: discord.Member, amount: int):
        if not await self.admin(interaction, code):
            return
        row = await self.admin_target(interaction.guild, member)
        if not row or amount <= 0:
            await interaction.response.send_message("У участника нет страны или сумма неверна.", ephemeral=True)
            return
        self.bot.db.change_account(interaction.guild.id, row["country_key"], amount)
        await interaction.response.send_message(f"К балансу {member.mention} добавлено **{fmt(amount)} кок**.", ephemeral=True)

    @app_commands.command(name="admin_xp", description="Админ: установить опыт")
    @app_commands.describe(code="Защитный код", member="Участник", xp="Новый опыт")
    async def admin_xp(self, interaction: discord.Interaction, code: str, member: discord.Member, xp: float):
        if not await self.admin(interaction, code):
            return
        self.bot.db.ensure_user(interaction.guild.id, member.id)
        self.bot.db.execute("UPDATE users SET xp = ? WHERE guild_id = ? AND user_id = ?", (max(0, xp), interaction.guild.id, member.id))
        await self.bot.level_role(interaction.guild, member, True)
        await interaction.response.send_message(f"Опыт {member.mention} установлен: {xp:.0f} XP.", ephemeral=True)

    @app_commands.command(name="admin_uroven", description="Админ: установить уровень пользователя")
    @app_commands.describe(code="Защитный код", member="Участник", level="Новый уровень от 1 до 150")
    async def admin_level(self, interaction: discord.Interaction, code: str,
                          member: discord.Member, level: int):
        if not await self.admin(interaction, code):
            return
        level = max(1, min(MAX_LEVEL, level))
        xp = XP_THRESHOLDS[level - 1]
        self.bot.db.ensure_user(interaction.guild.id, member.id)
        self.bot.db.execute(
            "UPDATE users SET xp = ? WHERE guild_id = ? AND user_id = ?",
            (xp, interaction.guild.id, member.id),
        )
        await self.bot.level_role(interaction.guild, member, True)
        await interaction.response.send_message(
            f"Уровень {member.mention} установлен: **{level}**.", ephemeral=True
        )

    @app_commands.command(name="admin_politika", description="Админ: изменить политические значения страны")
    @app_commands.describe(code="Защитный код", country="Страна", field="Параметр",
                           amount="Новое значение")
    @app_commands.choices(country=ALL_CHOICES, field=[
        app_commands.Choice(name="Одобрение власти", value="approval"),
        app_commands.Choice(name="Качество жизни", value="quality_of_life"),
        app_commands.Choice(name="Преступность", value="crime"),
        app_commands.Choice(name="Стабильность", value="stability"),
    ])
    async def admin_politics(self, interaction: discord.Interaction, code: str,
                              country: app_commands.Choice[str],
                              field: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        amount = max(0, min(100, amount))
        self.bot.db.execute(
            f"UPDATE countries SET {field.value} = ? WHERE guild_id = ? AND country_key = ?",
            (amount, interaction.guild.id, country.value),
        )
        await interaction.response.send_message(
            f"Параметр «{field.name}» страны установлен: **{amount}%**.", ephemeral=True
        )

    @app_commands.command(name="admin_vektor", description="Админ: установить политический вектор страны")
    @app_commands.describe(code="Защитный код", country="Страна", ideology="Новый вектор")
    @app_commands.choices(country=ALL_CHOICES, ideology=[
        app_commands.Choice(name=data["name"], value=key) for key, data in IDEOLOGIES.items()])
    async def admin_vector(self, interaction: discord.Interaction, code: str,
                           country: app_commands.Choice[str],
                           ideology: app_commands.Choice[str]):
        if not await self.admin(interaction, code):
            return
        self.bot.db.execute(
            "UPDATE countries SET ideology = ?, vector_change_at = 0 WHERE guild_id = ? AND country_key = ?",
            (ideology.value, interaction.guild.id, country.value),
        )
        await interaction.response.send_message(
            f"Вектор страны установлен: **{ideology.name}**.", ephemeral=True
        )

    @app_commands.command(name="admin_armiya", description="Админ: установить армию страны")
    @app_commands.describe(code="Защитный код", country="Страна", amount="Армия")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_army(self, interaction: discord.Interaction, code: str, country: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        self.bot.db.execute("UPDATE countries SET army = MAX(0, ?) WHERE guild_id = ? AND country_key = ?", (amount, interaction.guild.id, country.value))
        await interaction.response.send_message(f"Армия страны установлена: {fmt(amount)}.", ephemeral=True)

    @app_commands.command(name="admin_moral", description="Админ: установить боевой дух страны")
    @app_commands.describe(code="Защитный код", country="Страна", amount="Боевой дух от 0 до 100")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_morale(self, interaction: discord.Interaction, code: str, country: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        amount = max(0, min(100, amount))
        self.bot.db.execute("UPDATE countries SET morale = ? WHERE guild_id = ? AND country_key = ?", (amount, interaction.guild.id, country.value))
        await interaction.response.send_message(f"Боевой дух установлен: {amount}%.", ephemeral=True)

    @app_commands.command(name="admin_provincii", description="Админ: установить число провинций")
    @app_commands.describe(code="Защитный код", country="Страна", amount="Число провинций")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_provinces(self, interaction: discord.Interaction, code: str, country: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        row = self.bot.db.one("SELECT max_provinces FROM countries WHERE guild_id = ? AND country_key = ?", (interaction.guild.id, country.value))
        if not row:
            await interaction.response.send_message("Страна не найдена.", ephemeral=True)
            return
        amount = max(1, min(row["max_provinces"], amount))
        self.bot.db.execute("UPDATE countries SET provinces = ? WHERE guild_id = ? AND country_key = ?", (amount, interaction.guild.id, country.value))
        await interaction.response.send_message(f"Провинции установлены: {amount}.", ephemeral=True)

    @app_commands.command(name="admin_predpriyatie", description="Админ: установить уровень предприятий")
    @app_commands.describe(code="Защитный код", country="Страна", level="Уровень от 0 до 5")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_enterprise(self, interaction: discord.Interaction, code: str, country: app_commands.Choice[str], level: int):
        if not await self.admin(interaction, code):
            return
        level = max(0, min(5, level))
        self.bot.db.execute("UPDATE countries SET industry_level = ?, last_income_at = ? WHERE guild_id = ? AND country_key = ?", (level, time.time(), interaction.guild.id, country.value))
        await interaction.response.send_message(f"Уровень предприятий установлен: {level}.", ephemeral=True)

    @app_commands.command(name="admin_dobavit_predpriyatie", description="Админ: добавить предприятие и установить его уровень")
    @app_commands.describe(code="Защитный код", country="Страна",
                           level="Итоговый уровень предприятий от 0 до 5")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_add_enterprise(self, interaction: discord.Interaction, code: str,
                                   country: app_commands.Choice[str], level: int):
        if not await self.admin(interaction, code):
            return
        level = max(0, min(5, level))
        self.bot.db.execute(
            "UPDATE countries SET industry_level = ?, last_income_at = ? "
            "WHERE guild_id = ? AND country_key = ?",
            (level, time.time(), interaction.guild.id, country.value),
        )
        income = ENTERPRISES[level]["income"] if level else 0
        await interaction.response.send_message(
            f"Предприятие страны **{country.name}** установлено на уровень **{level}** "
            f"(доход: {income} кок/час).", ephemeral=True
        )

    @app_commands.command(name="admin_naselenie", description="Админ: установить население страны")
    @app_commands.describe(code="Защитный код", country="Страна", amount="Новое население")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_population(self, interaction: discord.Interaction, code: str,
                               country: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        amount = max(1_000, amount)
        self.bot.db.execute(
            "UPDATE countries SET population = ? WHERE guild_id = ? AND country_key = ?",
            (amount, interaction.guild.id, country.value),
        )
        await interaction.response.send_message(
            f"Население страны установлено: {fmt(amount)}.", ephemeral=True
        )

    @app_commands.command(name="admin_kazna", description="Админ: установить казну страны")
    @app_commands.describe(code="Защитный код", country="Страна", amount="Новая казна в кок")
    @app_commands.choices(country=ALL_CHOICES)
    async def admin_treasury(self, interaction: discord.Interaction, code: str,
                             country: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        amount = max(0, amount)
        row = self.bot.db.one(
            "SELECT owner_id FROM countries WHERE guild_id = ? AND country_key = ?",
            (interaction.guild.id, country.value),
        )
        self.bot.db.execute(
            "UPDATE countries SET treasury = ? WHERE guild_id = ? AND country_key = ?",
            (amount, interaction.guild.id, country.value),
        )
        if row and row["owner_id"]:
            self.bot.db.ensure_user(interaction.guild.id, row["owner_id"])
            self.bot.db.execute(
                "UPDATE users SET coins = ? WHERE guild_id = ? AND user_id = ?",
                (amount, interaction.guild.id, row["owner_id"]),
            )
        await interaction.response.send_message(
            f"Казна страны установлена: {fmt(amount)} кок.", ephemeral=True
        )

    @app_commands.command(name="admin_resursy", description="Админ: установить военный ресурс страны")
    @app_commands.describe(code="Защитный код", country="Страна", resource="Ресурс",
                           amount="Новое значение")
    @app_commands.choices(country=ALL_CHOICES, resource=[
        app_commands.Choice(name="Мечники", value="swordsmen"),
        app_commands.Choice(name="Лучники", value="archers"),
        app_commands.Choice(name="Осадные орудия", value="siege"),
        app_commands.Choice(name="Требушеты", value="trebuchets"),
        app_commands.Choice(name="Конница", value="cavalry"),
        app_commands.Choice(name="Морской десант", value="marines"),
        app_commands.Choice(name="Флот", value="fleet"),
        app_commands.Choice(name="Верфь", value="shipyard"),
        app_commands.Choice(name="Генералы", value="generals"),
        app_commands.Choice(name="Укрепление столицы", value="capital_fort"),
        app_commands.Choice(name="Укрепление провинций", value="province_fort"),
    ])
    async def admin_resources(self, interaction: discord.Interaction, code: str,
                              country: app_commands.Choice[str],
                              resource: app_commands.Choice[str], amount: int):
        if not await self.admin(interaction, code):
            return
        amount = max(0, amount)
        self.bot.db.execute(
            f"UPDATE countries SET {resource.value} = ? WHERE guild_id = ? AND country_key = ?",
            (amount, interaction.guild.id, country.value),
        )
        await interaction.response.send_message(
            f"Ресурс «{resource.name}» установлен: {fmt(amount)}.", ephemeral=True
        )

    @app_commands.command(name="admin_user_stat", description="Админ: установить статистику пользователя")
    @app_commands.describe(code="Защитный код", member="Участник", field="Параметр",
                           amount="Новое значение")
    @app_commands.choices(field=[
        app_commands.Choice(name="Сообщения", value="messages"),
        app_commands.Choice(name="Голосовые секунды", value="voice_seconds"),
        app_commands.Choice(name="Победы", value="year_wins"),
        app_commands.Choice(name="Счётчик гамбы", value="gamba_count"),
    ])
    async def admin_user_stat(self, interaction: discord.Interaction, code: str,
                              member: discord.Member, field: app_commands.Choice[str],
                              amount: int):
        if not await self.admin(interaction, code):
            return
        self.bot.db.ensure_user(interaction.guild.id, member.id)
        self.bot.db.execute(
            f"UPDATE users SET {field.value} = ? WHERE guild_id = ? AND user_id = ?",
            (max(0, amount), interaction.guild.id, member.id),
        )
        await interaction.response.send_message(
            f"Параметр «{field.name}» пользователя {member.mention} установлен: "
            f"{max(0, amount)}.", ephemeral=True
        )

    @app_commands.command(name="admin_sbros", description="Админ: выполнить большой игровой сброс")
    @app_commands.describe(code="Защитный код")
    async def admin_reset(self, interaction: discord.Interaction, code: str):
        if not await self.admin(interaction, code):
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot.reset_year(interaction.guild, datetime.now(timezone.utc).year)
        await interaction.followup.send("Большой игровой сброс выполнен.", ephemeral=True)


bot = KovchegBot()


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Не задан DISCORD_TOKEN. Добавьте его в переменные окружения Discloud.")
    try:
        bot.run(token.strip())
    except discord.LoginFailure as error:
        raise SystemExit(
            "Discord отклонил DISCORD_TOKEN (401 Unauthorized). Создайте новый Bot Token "
            "в Developer Portal и вставьте только его значение без кавычек, DISCORD_TOKEN= и Bot."
        ) from error