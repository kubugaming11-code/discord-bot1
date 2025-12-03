import os
import random
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from datetime import datetime, timedelta
from typing import Optional


# ----------------- Konfiguráció -----------------

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

bot = commands.Bot(command_prefix="/", intents=INTENTS)
# Slash parancsok a bot.tree használatával

# ----------------- Állapot / Memória (nem perzisztens) -----------------

start_time = datetime.utcnow()
warns: dict[int, dict[int, list[tuple[int, str, str]]]] = {}  
# struktúra: szerver_id -> (felhasználó_id -> lista [(moderátor_id, ok, időpont ISO), ...])

# ----------------- Segédfüggvények -----------------

def is_mod():
    """Decorator: csak moderátorok / megfelelő joggal rendelkező felhasználók használhatják."""
    def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        perms = interaction.user.guild_permissions
        return (
            perms.administrator
            or perms.kick_members
            or perms.ban_members
            or perms.manage_messages
            or perms.moderate_members
        )
    return app_commands.check(predicate)

async def get_or_create_modlog_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Megkeresi / létrehozza a mod-log csatornát."""
    for ch in guild.text_channels:
        if ch.name in ["mod-log", "mod_log", "modlog"]:
            return ch
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True)
        }
        ch = await guild.create_text_channel("mod-log", overwrites=overwrites, reason="Automatikus mod-log létrehozása")
        return ch
    except Exception:
        return None

def pretty_time_delta(td: timedelta) -> str:
    s = int(td.total_seconds())
    parts = []
    for unit, div in (("nap", 86400), ("óra", 3600), ("perc", 60), ("mp", 1)):
        if s >= div:
            val, s = divmod(s, div)
            suffix = ""
            if unit == "nap":
                suffix = "ok" if val > 1 else ""
            parts.append(f"{val} {unit}{suffix}")
    return ", ".join(parts) if parts else "0 mp"

# ----------------- Események -----------------

@bot.event
async def on_ready():
    print(f"Bejelentkezve: {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Slash parancsok szinkronizálva ({len(synced)})")
    except Exception as e:
        print("Hiba a slash parancsok szinkronizálásánál:", e)
    await bot.change_presence(activity=discord.Game(name="Grand Theft Auto VI"))

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Slash parancs hibakezelése."""
    if isinstance(error, app_commands.MissingRequiredArgument):
        await interaction.response.send_message("❌ Hiányzik egy kötelező argumentum.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Nincs meg a szükséges jogosultságod.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Csak moderátoroknak elérhető parancs.", ephemeral=True)
    elif isinstance(error, app_commands.CommandNotFound):
        # Ezt nem nagyon kell kezelni slash-nél
        await interaction.response.send_message("❌ Ismeretlen parancs.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Hiba történt: `{error}`", ephemeral=True)
        raise error

# ----------------- Slash parancsok -----------------

@bot.tree.command(name="help", description="Segítség — Parancsok listája")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Segítség — Parancsok",
        description=f"Prefix: `/` — Írd: `/help` a használathoz",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    # Általános parancsok
    embed.add_field(
        name="🤖 Általános",
        value=(
            "`/help` — Ez az üzenet\n"
            "`/ping` — Válaszidő\n"
            "`/say <szöveg>` — A bot ismétli\n"
            "`/avatar [user]` — Profilkép\n"
            "`/userinfo [user]` — Felhasználó adatai\n"
            "`/serverinfo` — Szerver adatai\n"
            "`/membercount` — Tagok száma\n"
            "`/botinfo` — Bot adatai\n"
            "`/invite` — Meghívó link\n"
            "`/uptime` — Mióta fut a bot\n"
        ),
        inline=False
    )
    embed.add_field(
        name="🛡 Moderáció (csak modoknak)",
        value=(
            "`/kick <user> [ok]` — Kirúgás\n"
            "`/ban <user> [ok]` — Kitiltás\n"
            "`/unban <név#1234 vagy ID>` — Tiltás feloldása\n"
            "`/mute <user> <perc>` — Némítás\n"
            "`/unmute <user>` — Némítás feloldása\n"
            "`/purge <szám>` — Üzenetek törlése\n"
            "`/lock` / `/unlock` — Csatorna zárolása / feloldása\n"
            "`/slowmode <mp>` — Slowmode beállítása\n"
            "`/nick <user> <új_nick>` — Becenév módosítása\n"
            "`/clear_reactions <üzenet_id>` — Reakciók törlése\n"
            "`/warn <user> [ok]` — Figyelmeztetés\n"
            "`/warnings <user>` — Figyelmeztetések listája\n"
        ),
        inline=False
    )
    embed.add_field(
        name="🎲 Szórakozás / Extra",
        value=(
            "`/8ball <kérdés>` — Véletlen válasz\n"
            "`/color [max]` — Dobás (alap 100)\n"
            "`/flip` — Pénzfeldobás\n"
            "`/roll` — Dobókocka (alap 100)\n"
            "`/choose <op1> <op2> ...` — Választás\n"
            "`/poll \"Kérdés\" op1 op2 ...` — Szavazás\n"
            "`/countdown <mp>` — Visszaszámlálás\n"
            "`/math <kifejezés>` — Egyszerű művelet\n"
            "`/reverse <szöveg>` — Szöveg visszafordítása\n"
            "`/mock <szöveg>` — Mock stílusú szöveg\n"
        ),
        inline=False
    )
    embed.set_footer(text="Üzenet generálva:")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Visszaadja a bot késleltetési idejét")
async def slash_ping(interaction: discord.Interaction):
    latency = bot.latency * 1000
    await interaction.response.send_message(f"Pong! 🏓 Latencia: {latency:.0f} ms")

@bot.tree.command(name="say", description="A bot ismétli a megadott szöveget")
async def slash_say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="avatar", description="Felhasználó profilképe")
async def slash_avatar(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.display_name} avatarja", color=discord.Color.green())
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="Felhasználó információi")
async def slash_userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    user = user or interaction.user
    roles = [r.mention for r in user.roles if r.name != "@everyone"]
    joined = user.joined_at.strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "Ismeretlen"
    created = user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    embed = discord.Embed(title=f"Info — {user}", color=discord.Color.blue())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Bot?", value=str(user.bot), inline=True)
    embed.add_field(name="Csatlakozott", value=joined, inline=False)
    embed.add_field(name="Regisztrálva", value=created, inline=False)
    embed.add_field(name=f"Szerepek ({len(roles)})", value=", ".join(roles) or "Nincs", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Szerver információk")
async def slash_serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    if g is None:
        await interaction.response.send_message("Csak szerverben használható.", ephemeral=True)
        return
    embed = discord.Embed(title=g.name, description=g.description or "Nincs leírás", color=discord.Color.red())
    embed.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
    embed.add_field(name="ID", value=g.id, inline=True)
    embed.add_field(name="Regisztrált", value=g.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Tagok", value=g.member_count, inline=True)
    embed.add_field(name="Csatornák", value=len(g.channels), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="membercount", description="Tagok száma a szerveren")
async def slash_membercount(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("© Nincs adat.", ephemeral=True)
        return
    await interaction.response.send_message(f"A szerveren {interaction.guild.member_count} tag van.")

@bot.tree.command(name="botinfo", description="Bot információk")
async def slash_botinfo(interaction: discord.Interaction):
    uptime = datetime.utcnow() - start_time
    embed = discord.Embed(title="Bot információk", color=discord.Color.blurple())
    embed.add_field(name="Név:", value=str(bot.user), inline=True)
    embed.add_field(name="ID:", value=bot.user.id, inline=True)
    embed.add_field(name="Futásideje:", value=pretty_time_delta(uptime), inline=True)
    embed.add_field(name="Szerverek száma:", value=len(bot.guilds), inline=True)
    embed.add_field(name="Készítette:", value="_.kkrrsak", inline=False)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="invite", description="Meghívó link a bothoz")
async def slash_invite(interaction: discord.Interaction):
    client_id = bot.user.id
    perms = discord.Permissions(permissions=8)
    url = discord.utils.oauth_url(client_id, permissions=perms)
    embed = discord.Embed(title="Meghívó a bothoz", description=f"[Kattints ide]({url})", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="uptime", description="Mennyi ideje fut a bot?")
async def slash_uptime(interaction: discord.Interaction):
    uptime = datetime.utcnow() - start_time
    await interaction.response.send_message(f"A bot {pretty_time_delta(uptime)} óta fut.")

# Moderációs parancsok

@bot.tree.command(name="kick", description="Kirúg egy felhasználót")
@is_mod()
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Nincs megadva"):
    if not interaction.guild.me.guild_permissions.kick_members:
        await interaction.response.send_message("❌ A botnak nincs kick joga.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ {member} kirúgva. Ok: {reason}")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Felhasználó kirúgva", color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Moderátor", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Ok", value=reason, inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba a kirúgás közben: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Kitilt egy felhasználót")
@is_mod()
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Nincs megadva"):
    if not interaction.guild.me.guild_permissions.ban_members:
        await interaction.response.send_message("❌ A botnak nincs ban joga.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason, delete_message_days=0)
        await interaction.response.send_message(f"✅ {member} kitiltva. Ok: {reason}")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Felhasználó kitiltva", color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Moderátor", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Ok", value=reason, inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba a kitiltás közben: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Feloldja egy felhasználó tiltását")
@is_mod()
async def slash_unban(interaction: discord.Interaction, user_identifier: str):
    if not interaction.guild.me.guild_permissions.ban_members:
        await interaction.response.send_message("❌ A botnak nincs unban joga.", ephemeral=True)
        return
    try:
        user = None
        if user_identifier.isdigit():
            user = await bot.fetch_user(int(user_identifier))
        else:
            if "#" not in user_identifier:
                await interaction.response.send_message("Adj meg név#1234 formátumot vagy ID-t!", ephemeral=True)
                return
            name, discrim = user_identifier.split("#")
            bans = await interaction.guild.bans()
            for entry in bans:
                if entry.user.name == name and entry.user.discriminator == discrim:
                    user = entry.user
                    break
        if not user:
            await interaction.response.send_message("❌ Nem található a tiltott felhasználók között.", ephemeral=True)
            return
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"✅ {user} tiltását feloldottam.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Tiltás feloldva", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{user} ({user.id})", inline=False)
            embed.add_field(name="Moderátor", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba az unban során: {e}", ephemeral=True)

@bot.tree.command(name="purge", description="Üzenetek törlése")
@is_mod()
async def slash_purge(interaction: discord.Interaction, amount: int):
    if not interaction.guild.me.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ A bot nem tud üzeneteket törölni.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("Adj meg egy pozitív számot.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount + 1)
    await interaction.response.send_message(f"✅ Törölve: {len(deleted)-1} üzenet.", ephemeral=True)
    ch = await get_or_create_modlog_channel(interaction.guild)
    if ch:
        embed = discord.Embed(title="Purge végrehajtva", color=discord.Color.dark_blue(), timestamp=datetime.utcnow())
        embed.add_field(name="Csatorna", value=interaction.channel.mention, inline=False)
        embed.add_field(name="Törölt üzenetek", value=str(len(deleted)-1), inline=False)
        embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
        await ch.send(embed=embed)

@bot.tree.command(name="mute", description="Némít egy felhasználót adott ideig")
@is_mod()
async def slash_mute(interaction: discord.Interaction, member: discord.Member, minutes: int = 10):
    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ A botnak nincs `Moderate Members` joga.", ephemeral=True)
        return
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        await member.edit(timeout=until)
        await interaction.response.send_message(f"🔇 {member.mention} némítva {minutes} percig.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Felhasználó némítva", color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Idő", value=f"{minutes} perc", inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba a némítás során: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Némítás feloldása")
@is_mod()
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ A botnak nincs `Moderate Members` joga.", ephemeral=True)
        return
    try:
        await member.edit(timeout=None)
        await interaction.response.send_message(f"🔊 {member.mention} némítását feloldottam.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Némítás feloldva", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="lock", description="Zárolja az aktuális csatornát")
@is_mod()
async def slash_lock(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    channel = channel or interaction.channel
    try:
        await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(f"🔒 {channel.mention} zárolva.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Csatorna zárolva", color=discord.Color.dark_blue(), timestamp=datetime.utcnow())
            embed.add_field(name="Csatorna", value=channel.mention, inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="unlock", description="Csatorna zárolás feloldása")
@is_mod()
async def slash_unlock(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    channel = channel or interaction.channel
    try:
        await channel.set_permissions(interaction.guild.default_role, send_messages=True)
        await interaction.response.send_message(f"🔓 {channel.mention} feloldva.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Csatorna feloldva", color=discord.Color.green(), timestamp=datetime.utcnow())
            embed.add_field(name="Csatorna", value=channel.mention, inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="slowmode", description="Csatorna slowmode beállítása")
@is_mod()
async def slash_slowmode(interaction: discord.Interaction, seconds: int = 0):
    try:
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"⏱️ Slowmode beállítva: {seconds} mp", ephemeral=True)
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Slowmode módosítva", color=discord.Color.dark_gold(), timestamp=datetime.utcnow())
            embed.add_field(name="Csatorna", value=interaction.channel.mention, inline=False)
            embed.add_field(name="Slowmode", value=f"{seconds} mp", inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="nick", description="Felhasználó becenevét módosítja")
@is_mod()
async def slash_nick(interaction: discord.Interaction, member: discord.Member, nick: Optional[str] = None):
    try:
        await member.edit(nick=nick)
        await interaction.response.send_message(f"✅ {member} beceneve megváltoztatva.")
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Nick változtatva", color=discord.Color.blurple(), timestamp=datetime.utcnow())
            embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Új nick", value=nick or "Törölve", inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="clear_reactions", description="Egy üzenet reakcióinak törlése")
@is_mod()
async def slash_clear_reactions(interaction: discord.Interaction, message_id: int):
    try:
        msg = await interaction.channel.fetch_message(message_id)
        await msg.clear_reactions()
        await interaction.response.send_message("✅ Reakciók törölve.", ephemeral=True)
        ch = await get_or_create_modlog_channel(interaction.guild)
        if ch:
            embed = discord.Embed(title="Reakciók törölve", color=discord.Color.dark_blue(), timestamp=datetime.utcnow())
            embed.add_field(name="Üzenet", value=f"[Ugrás az üzenetre]({msg.jump_url})", inline=False)
            embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
            await ch.send(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Figyelmeztet egy felhasználót")
@is_mod()
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "Nincs megadva"):
    g = interaction.guild
    if g is None:
        await interaction.response.send_message("Csak szerverben használható.", ephemeral=True)
        return
    gw = warns.setdefault(g.id, {})
    ul = gw.setdefault(member.id, [])
    ul.append((interaction.user.id, reason, datetime.utcnow().isoformat()))
    await interaction.response.send_message(f"⚠️ {member.mention} figyelmeztetve. Ok: {reason}")
    ch = await get_or_create_modlog_channel(g)
    if ch:
        embed = discord.Embed(title="Figyelmeztetés", color=discord.Color.orange(), timestamp=datetime.utcnow())
        embed.add_field(name="Felhasználó", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="Ok", value=reason, inline=False)
        embed.add_field(name="Moderátor", value=str(interaction.user), inline=False)
        await ch.send(embed=embed)

@bot.tree.command(name="warnings", description="Egy felhasználó figyelmeztetései")
@is_mod()
async def slash_warnings(interaction: discord.Interaction, member: discord.Member):
    g = interaction.guild
    if g is None:
        await interaction.response.send_message("Csak szerveren használható.", ephemeral=True)
        return
    gw = warns.get(g.id, {})
    ul = gw.get(member.id, [])
    if not ul:
        await interaction.response.send_message("Nincsenek figyelmeztetések erre a felhasználóra.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Figyelmeztetések — {member}", color=discord.Color.orange())
    for i, (moderator_id, reason, ts) in enumerate(ul, start=1):
        mod = interaction.guild.get_member(moderator_id)
        embed.add_field(name=f"{i}. {mod or moderator_id}", value=f"{reason}\n{ts}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="emojilist", description="A szerver custom emojijai")
async def slash_emojilist(interaction: discord.Interaction):
    emojis = " ".join(str(e) for e in interaction.guild.emojis) if interaction.guild else ""
    if not emojis:
        emojis = "Nincsenek custom emojik a szerveren."
    await interaction.response.send_message(emojis)

@bot.tree.command(name="roleinfo", description="Szerep információi")
async def slash_roleinfo(interaction: discord.Interaction, role: discord.Role):
    embed = discord.Embed(title=f"Szerep: {role.name}", color=role.color)
    embed.add_field(name="ID", value=role.id, inline=True)
    embed.add_field(name="Tagok száma", value=len(role.members), inline=True)
    embed.add_field(name="Létrehozva", value=role.created_at.strftime("%Y-%m-%d"), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="channelinfo", description="Csatorna információk")
async def slash_channelinfo(interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
    channel = channel or interaction.channel
    embed = discord.Embed(title=f"Csatorna: {channel.name}", color=discord.Color.blurple())
    embed.add_field(name="ID", value=channel.id, inline=True)
    embed.add_field(name="Típus", value=str(channel.type), inline=True)
    await interaction.response.send_message(embed=embed)

# Szórakoztató / extra parancsok

@bot.command(name="roll")
async def roll(ctx, max_value: int = 100):
    if max_value <= 0:
        return await ctx.send("Adj meg pozitív számot.")
    await ctx.send(f"🎲 Dobás: {random.randint(1, max_value)} / {max_value}")

@bot.tree.command(name="8ball", description="Kérdezz, és kapsz egy választ")
async def slash_8ball(interaction: discord.Interaction, question: str):
    choices = [
        "Igen", "Nem", "Talán", "Később kérdezd meg újra", "Esélyes", "Nincs rá meg a válaszom", "Abszolút","Biztosan nem", "Az esélyek jók", "Az esélyek rosszak", "Nem tudom megmondani", "Kérdezd meg újra", "Valószínűleg igen", "Valószínűleg nem", "Nem számíthatsz rá", "Igen, de csak ha...", "Nem, hacsak nem...", "Az univerzum nem akarja", "A jelek szerint igen", "A jelek szerint nem"
    ]
    await interaction.response.send_message(f"🎱 {random.choice(choices)}")

@bot.tree.command(name="color", description="Dob egy véletlenszámot 1 és max között")
async def slash_color(interaction: discord.Interaction, max_value: Optional[int] = 100):
    if max_value is None or max_value <= 0:
        await interaction.response.send_message("Adj meg pozitív számot.")
        return
    await interaction.response.send_message(f"🎲 Dobás: {random.randint(1, max_value)} / {max_value}")

@bot.tree.command(name="flip", description="Pénzfeldobás — fej vagy írás")
async def slash_flip(interaction: discord.Interaction):
    await interaction.response.send_message("🪙 " + random.choice(["Fej", "Írás"]))

@bot.tree.command(name="choose", description="Kiválaszt egy opciót")
async def slash_choose(interaction: discord.Interaction, options: str):
    opts = options.split()
    if len(opts) < 2:
        await interaction.response.send_message("Adj meg legalább 2 opciót (szóközzel elválasztva).")
        return
    await interaction.response.send_message(f"👉 A választásom: **{random.choice(opts)}**")

@bot.tree.command(name="poll", description="Szavazás indítása")
async def slash_poll(interaction: discord.Interaction, question: str, options: str):
    await interaction.response.defer()
    opts = options.split()
    if not opts:
        opts = ["Igen", "Nem"]
    if len(opts) > 10:
        await interaction.followup.send("Maximum 10 opciót adhatsz meg.")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    desc = ""
    for i, opt in enumerate(opts):
        desc += f"{emojis[i]} {opt}\n"
    embed = discord.Embed(title=f"Szavazás: {question}", description=desc, color=discord.Color.purple())
    msg = await interaction.followup.send(embed=embed)
    for i in range(len(opts)):
        await msg.add_reaction(emojis[i])

@bot.tree.command(name="countdown", description="Visszaszámlálás indítása")
async def slash_countdown(interaction: discord.Interaction, seconds: int):
    if seconds <= 0 or seconds > 3600:
        await interaction.response.send_message("Adj meg 1 és 3600 közötti másodpercek számát.", ephemeral=True)
        return
    await interaction.response.send_message(f"Visszaszámlálás: {seconds} mp")
    follow = await interaction.original_response()
    for i in range(seconds, 0, -1):
        await follow.edit(content=f"Visszaszámlálás: {i} mp")
        await asyncio.sleep(1)
    await follow.edit(content="⏰ Idő lejárt!")

@bot.tree.command(name="math", description="Egyszerű matematikai művelet")
async def slash_math(interaction: discord.Interaction, expr: str):
    allowed = "0123456789+-*/().% "
    if any(ch not in allowed for ch in expr):
        await interaction.response.send_message("Csak számok és műveleti jelek engedélyezettek.")
        return
    try:
        result = eval(expr, {"__builtins__": None}, {})
        await interaction.response.send_message(f"📐 Eredmény: `{result}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Hiba a számítás közben: {e}")

@bot.tree.command(name="reverse", description="Szöveg visszafordítása")
async def slash_reverse(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[::-1])

@bot.tree.command(name="mock", description="Mock stílusú szöveg")
async def slash_mock(interaction: discord.Interaction, text: str):
    s = ''.join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
    await interaction.response.send_message(s)

# ----------------- Futtatás -----------------

if __name__ == "__main__":
    bot.run("MTQxMzk0NjU4MjY2NzIzMTMxMg.GbjRc2.dnMZPP6cYwbQucde2Ms8s2tOWs4kyZaIU19uuM")