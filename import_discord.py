import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
from datetime import datetime, timedelta
import re
import os

# ── Configuration ──────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

Tanacity_ID = 1493346154757226648
Tanacity_TRIGGERS = {"/tanacity", "discord.gg/tanacity", ".gg/tanacity"}

# ── GHOST PING CONFIGURATION (3 salons) ───────────────────────
GHOST_PING_CHANNELS = [
    1498653937405001860,   # Salon 1
    1493346312379301938,   # Salon 2
    1493346338493038653    # Salon 3
]
GHOST_PING_DURATION = 10   # Durée du ping en secondes
# ───────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_giveaways: dict[int, dict] = {}


def parse_duration(duration_str: str) -> int | None:
    pattern = re.fullmatch(r"(\d+)(s|m|h|d)", duration_str.strip().lower())
    if not pattern:
        return None
    value, unit = int(pattern.group(1)), pattern.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "Terminé"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days: parts.append(f"{days}j")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}min")
    if secs and not days: parts.append(f"{secs}s")
    return " ".join(parts) if parts else "< 1s"


def build_giveaway_embed(titre: str, remaining_seconds: int, emoji: str, host: discord.Member, role_requis=None) -> discord.Embed:
    embed = discord.Embed(
        title=f"{emoji} {titre}",
        color=discord.Color.from_rgb(114, 137, 218)
    )
    embed.add_field(name="", value=f"**Host by** {host.mention}", inline=False)
    if role_requis:
        embed.add_field(name="", value=f"**Rôle requis :** {role_requis.mention}", inline=False)
    embed.add_field(name="", value=f"**Temps restant :** {format_remaining(remaining_seconds)}", inline=False)
    return embed


# ====================== OPSECS STATUT & MESSAGE ======================
def get_custom_status(member: discord.Member) -> str | None:
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity):
            return activity.name
    return None


def has_opsecs_trigger(status_text: str | None) -> bool:
    if not status_text:
        return False
    return any(trigger in status_text.lower() for trigger in OPSECS_TRIGGERS)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if any(trigger in message.content.lower() for trigger in OPSECS_TRIGGERS):
        guild = message.guild
        if guild:
            role = guild.get_role(OPSECS_ROLE_ID)
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="Mention de .gg/opsecs")
                    await message.channel.send(f"✅ {message.author.mention} a reçu le rôle **{role.name}** !", delete_after=10)
                except:
                    pass
    await bot.process_commands(message)


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    if after.bot:
        return
    if has_opsecs_trigger(get_custom_status(before)) == has_opsecs_trigger(get_custom_status(after)):
        return

    role = after.guild.get_role(OPSECS_ROLE_ID)
    if not role:
        return
    try:
        if has_opsecs_trigger(get_custom_status(after)):
            if role not in after.roles:
                await after.add_roles(role, reason="Statut opsecs")
        else:
            if role in after.roles:
                await after.remove_roles(role, reason="Statut opsecs retiré")
    except:
        pass


# ====================== GHOST PING SUR 3 SALONS ======================
@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return

    try:
        # On crée une liste de tâches pour pinguer dans les 3 salons en parallèle
        tasks = []
        for channel_id in GHOST_PING_CHANNELS:
            channel = member.guild.get_channel(channel_id)
            if channel:
                msg = await channel.send(f"**{member.mention} vient de rejoindre le serveur !**")
                tasks.append(asyncio.create_task(delete_after_delay(msg, GHOST_PING_DURATION)))

        # Attendre que tous les messages soient supprimés
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        print(f"❌ Erreur lors du ghost ping : {e}")


async def delete_after_delay(message: discord.Message, delay: int):
    """Supprime un message après un certain délai"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except discord.NotFound:
        pass  # Message déjà supprimé
    except discord.Forbidden:
        print(f"❌ Pas la permission de supprimer dans {message.channel.name}")
    except Exception as e:
        print(f"Erreur suppression message : {e}")


# ====================== NOUVELLE COMMANDE /message ======================
@bot.tree.command(name="message", description="Envoie un message en embed avec bande violette")
@app_commands.describe(
    texte="Le texte du message (description de l'embed)",
    titre="Titre de l'embed (optionnel)",
    image="URL de l'image à mettre en bas (optionnel)",
    channel="Salon où envoyer le message (optionnel)"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def message_cmd(
    interaction: discord.Interaction,
    texte: str,
    titre: str = None,
    image: str = None,
    channel: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)

    target_channel = channel or interaction.channel

    embed = discord.Embed(
        title=titre,
        description=texte,
        color=0x9B59B6
    )

    if image:
        embed.set_image(url=image)

    embed.set_footer(text=f"Envoyé par {interaction.user}")

    try:
        await target_channel.send(embed=embed)
        await interaction.followup.send(f"✅ Embed violet envoyé avec succès dans {target_channel.mention}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Je n'ai pas la permission d'envoyer des messages dans ce salon.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)


# ====================== COMMANDE GIVEAWAY ======================
@bot.tree.command(name="giveaway", description="Lance un giveaway avec rôle requis optionnel")
@app_commands.describe(
    titre="Titre du giveaway",
    duree="Durée (ex: 30s, 5m, 2h, 1d)",
    emoji="Emoji de participation",
    gagnants="Nombre de gagnants (défaut: 1)",
    winner="Choisir directement le gagnant (optionnel)",
    role_requis="Rôle obligatoire pour participer (optionnel)",
    message_role="Message MP si pas le rôle — utilise {@user} pour mentionner la personne"
)
async def giveaway_cmd(
    interaction: discord.Interaction,
    titre: str,
    duree: str,
    emoji: str,
    gagnants: int = 1,
    winner: discord.Member = None,
    role_requis: discord.Role = None,
    message_role: str = None
):
    await interaction.response.defer(thinking=True)

    seconds = parse_duration(duree)
    if not seconds or seconds < 10:
        await interaction.followup.send("❌ Durée invalide ou trop courte (minimum 10 secondes).", ephemeral=True)
        return
    if gagnants < 1:
        await interaction.followup.send("❌ Minimum 1 gagnant.", ephemeral=True)
        return

    embed = build_giveaway_embed(
        titre=titre,
        remaining_seconds=seconds,
        emoji=emoji,
        host=interaction.user,
        role_requis=role_requis
    )

    msg = await interaction.followup.send(embed=embed)

    try:
        await msg.add_reaction(emoji)
    except discord.HTTPException:
        await interaction.followup.send("❌ Impossible d'ajouter cet emoji.", ephemeral=True)
        return

    active_giveaways[msg.id] = {
        "titre": titre,
        "emoji": emoji,
        "end_time": datetime.utcnow() + timedelta(seconds=seconds),
        "gagnants": gagnants,
        "participants": set(),
        "host": interaction.user,
        "channel_id": interaction.channel_id,
        "role_requis": role_requis,
        "message_role": message_role,
        "manual_winner": winner
    }

    asyncio.create_task(giveaway_loop(interaction.channel_id, msg.id, seconds))


# ====================== COMMANDE ROLE_MANAGE ======================
@bot.tree.command(name="role_manage", description="Ajoute ou retire un rôle à tous les membres ayant un rôle ciblé")
@app_commands.describe(
    role_cible="Le rôle que doivent avoir les membres ciblés",
    role_action="Le rôle à ajouter ou retirer",
    action="Ajouter ou retirer le rôle"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Ajouter", value="add"),
    app_commands.Choice(name="Retirer", value="remove"),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def role_manage_cmd(
    interaction: discord.Interaction,
    role_cible: discord.Role,
    role_action: discord.Role,
    action: app_commands.Choice[str]
):
    await interaction.response.defer(thinking=True, ephemeral=True)

    bot_top_role = interaction.guild.me.top_role
    if role_action >= bot_top_role:
        await interaction.followup.send(f"❌ Je ne peux pas gérer le rôle **{role_action.name}**.", ephemeral=True)
        return

    membres_cibles = [m for m in interaction.guild.members if role_cible in m.roles]

    if not membres_cibles:
        await interaction.followup.send(f"❌ Aucun membre n'a le rôle **{role_cible.name}**.", ephemeral=True)
        return

    succes = echecs = ignores = 0

    for membre in membres_cibles:
        try:
            if action.value == "add":
                if role_action in membre.roles:
                    ignores += 1
                    continue
                await membre.add_roles(role_action, reason=f"role_manage par {interaction.user}")
            else:
                if role_action not in membre.roles:
                    ignores += 1
                    continue
                await membre.remove_roles(role_action, reason=f"role_manage par {interaction.user}")
            succes += 1
        except:
            echecs += 1

    embed = discord.Embed(title="✅ role_manage terminé", color=discord.Color.green() if echecs == 0 else discord.Color.orange())
    embed.add_field(name="Rôle ciblé", value=role_cible.mention, inline=True)
    embed.add_field(name="Rôle modifié", value=role_action.mention, inline=True)
    embed.add_field(name="Action", value="➕ Ajout" if action.value == "add" else "➖ Retrait", inline=True)
    embed.add_field(name="✅ Succès", value=str(succes), inline=True)
    embed.add_field(name="⏭️ Ignorés", value=str(ignores), inline=True)
    embed.add_field(name="❌ Échecs", value=str(echecs), inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


# ====================== FONCTIONS GIVEAWAY ======================
async def update_giveaway_embed(channel_id: int, message_id: int):
    if message_id not in active_giveaways:
        return
    gw = active_giveaways[message_id]
    try:
        channel = bot.get_channel(channel_id)
        msg = await channel.fetch_message(message_id)
        remaining = max(0, int((gw["end_time"] - datetime.utcnow()).total_seconds()))
        embed = build_giveaway_embed(gw["titre"], remaining, gw["emoji"], gw["host"], gw.get("role_requis"))
        await msg.edit(embed=embed)
    except:
        pass


async def giveaway_loop(channel_id: int, message_id: int, seconds: int):
    elapsed = 0
    while elapsed < seconds:
        await asyncio.sleep(min(30, seconds - elapsed))
        elapsed += 30
        await update_giveaway_embed(channel_id, message_id)
    await end_giveaway(channel_id, message_id)


async def end_giveaway(channel_id: int, message_id: int):
    if message_id not in active_giveaways:
        return
    gw = active_giveaways.pop(message_id)
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(message_id)
    except:
        return

    titre = gw["titre"]
    emoji = gw["emoji"]
    manual_winner = gw.get("manual_winner")

    end_embed = discord.Embed(title=f"{emoji} {titre}", description="**Giveaway terminé**", color=discord.Color.from_rgb(114, 137, 218))
    await msg.edit(embed=end_embed)

    if manual_winner:
        winner_mention = manual_winner.mention
    else:
        participants = list(gw["participants"])
        if not participants:
            await channel.send(f"😔 **{titre}** terminé sans participants.")
            return
        nb_winners = min(gw["gagnants"], len(participants))
        winner_ids = random.sample(participants, nb_winners)
        winner_mention = " ".join(f"<@{wid}>" for wid in winner_ids)

    await channel.send(f"**winner :** {winner_mention} ta 10 min pour me dm !")
    asyncio.create_task(five_min_warning(channel, winner_mention, titre))


async def five_min_warning(channel: discord.TextChannel, winner_mentions: str, titre: str):
    await asyncio.sleep(300)
    await channel.send(f"{winner_mentions} fait vite il te reste **5min** avant que je remake !")


# ====================== ON_READY ======================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")


bot.run(DISCORD_TOKEN)
