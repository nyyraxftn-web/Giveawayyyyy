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

# ID du rôle .gg/opsecs à attribuer
OPSECS_ROLE_ID = 1469989510514217023

# Mots-clés qui déclenchent l'attribution du rôle
OPSECS_TRIGGERS = {"/opsecs", "discord.gg/opsecs", ".gg/opsecs"}
# ───────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

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


# ====================== DÉTECTION OPSECS ======================
@bot.event
async def on_message(message: discord.Message):
    # Ignorer les messages du bot lui-même
    if message.author.bot:
        return

    # Vérifier si le message contient un des mots-clés opsecs
    content_lower = message.content.lower().strip()
    if any(trigger in content_lower for trigger in OPSECS_TRIGGERS):
        guild = message.guild
        if guild:
            role = guild.get_role(OPSECS_ROLE_ID)
            member = message.author

            if role is None:
                await message.channel.send(
                    f"❌ Le rôle `.gg/opsecs` (ID `{OPSECS_ROLE_ID}`) est introuvable sur ce serveur.",
                    delete_after=10
                )
            elif role in member.roles:
                # Membre a déjà le rôle, on ne fait rien (pas de spam)
                pass
            else:
                try:
                    await member.add_roles(role, reason="Mention de .gg/opsecs dans un message")
                    await message.channel.send(
                        f"✅ {member.mention} a reçu le rôle **{role.name}** !",
                        delete_after=10
                    )
                except discord.Forbidden:
                    await message.channel.send(
                        "❌ Je n'ai pas la permission d'attribuer ce rôle.",
                        delete_after=10
                    )
                except discord.HTTPException as e:
                    await message.channel.send(
                        f"❌ Erreur lors de l'attribution du rôle : {e}",
                        delete_after=10
                    )

    # Permettre aux autres commandes préfixées de fonctionner normalement
    await bot.process_commands(message)


# ====================== VÉRIFICATION RÔLE ======================
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id not in active_giveaways:
        return
    if payload.user_id == bot.user.id:
        return

    gw = active_giveaways[payload.message_id]
    if str(payload.emoji) != gw["emoji"]:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member:
        return

    role_requis = gw.get("role_requis")
    message_role = gw.get("message_role")

    if role_requis and role_requis not in member.roles:
        try:
            channel = bot.get_channel(payload.channel_id)
            msg = await channel.fetch_message(payload.message_id)
            await msg.remove_reaction(payload.emoji, member)

            if message_role:
                await member.send(message_role.replace("{@user}", member.mention))
            else:
                await member.send(f"Tu dois avoir le rôle **{role_requis.name}** pour participer à ce giveaway.")
        except:
            pass
        return

    gw["participants"].add(payload.user_id)
    await update_giveaway_embed(payload.channel_id, payload.message_id)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id not in active_giveaways or payload.user_id == bot.user.id:
        return

    gw = active_giveaways[payload.message_id]
    if str(payload.emoji) != gw["emoji"]:
        return

    gw["participants"].discard(payload.user_id)
    await update_giveaway_embed(payload.channel_id, payload.message_id)


async def update_giveaway_embed(channel_id: int, message_id: int):
    if message_id not in active_giveaways:
        return
    gw = active_giveaways[message_id]

    try:
        channel = bot.get_channel(channel_id)
        msg = await channel.fetch_message(message_id)
        remaining = max(0, int((gw["end_time"] - datetime.utcnow()).total_seconds()))

        embed = build_giveaway_embed(
            titre=gw["titre"],
            remaining_seconds=remaining,
            emoji=gw["emoji"],
            host=gw["host"],
            role_requis=gw.get("role_requis")
        )
        await msg.edit(embed=embed)
    except Exception:
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

    end_embed = discord.Embed(
        title=f"{emoji} {titre}",
        description="**Giveaway terminé**",
        color=discord.Color.from_rgb(114, 137, 218)
    )
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


# ====================== COMMANDE /giveaway ======================
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


# ====================== COMMANDE /role_manage ======================
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

    # Vérifier que le bot peut gérer ces rôles (hiérarchie)
    bot_top_role = interaction.guild.me.top_role
    if role_action >= bot_top_role:
        await interaction.followup.send(
            f"❌ Je ne peux pas gérer le rôle **{role_action.name}** car il est au-dessus ou au même niveau que mon rôle.",
            ephemeral=True
        )
        return

    # Récupérer tous les membres ayant le rôle ciblé
    membres_cibles = [m for m in interaction.guild.members if role_cible in m.roles]

    if not membres_cibles:
        await interaction.followup.send(
            f"❌ Aucun membre n'a le rôle **{role_cible.name}**.",
            ephemeral=True
        )
        return

    succes = 0
    echecs = 0
    ignores = 0  # déjà ont / n'ont pas le rôle

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
        except discord.Forbidden:
            echecs += 1
        except discord.HTTPException:
            echecs += 1

    action_label = "ajouté à" if action.value == "add" else "retiré à"
    ignore_label = "avaient déjà" if action.value == "add" else "ne l'avaient pas"

    embed = discord.Embed(
        title="✅ role_manage terminé",
        color=discord.Color.green() if echecs == 0 else discord.Color.orange()
    )
    embed.add_field(name="Rôle ciblé", value=role_cible.mention, inline=True)
    embed.add_field(name="Rôle modifié", value=role_action.mention, inline=True)
    embed.add_field(name="Action", value="➕ Ajout" if action.value == "add" else "➖ Retrait", inline=True)
    embed.add_field(name=f"✅ Rôle {action_label}", value=str(succes), inline=True)
    embed.add_field(name=f"⏭️ Ignorés ({ignore_label})", value=str(ignores), inline=True)
    embed.add_field(name="❌ Échecs", value=str(echecs), inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


@role_manage_cmd.error
async def role_manage_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Tu n'as pas la permission **Gérer les rôles** pour utiliser cette commande.",
            ephemeral=True
        )


# ====================== EVENTS ======================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")


bot.run(DISCORD_TOKEN)
