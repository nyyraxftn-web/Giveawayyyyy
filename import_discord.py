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

OPSECS_ROLE_ID = 1469989510514217023
OPSECS_TRIGGERS = {"/opsecs", "discord.gg/opsecs", ".gg/opsecs"}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_giveaways: dict[int, dict] = {}


# ====================== FONCTIONS OPSECS (statut + message) ======================
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


# ====================== COMMANDE /message (version simple) ======================
@bot.tree.command(name="message", description="Fait envoyer un message par le bot")
@app_commands.describe(
    texte="Le message que le bot doit envoyer",
    channel="Dans quel salon envoyer (optionnel)"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def message_cmd(interaction: discord.Interaction, texte: str, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)

    target_channel = channel or interaction.channel

    try:
        await target_channel.send(texte)
        await interaction.followup.send(f"✅ Message envoyé dans {target_channel.mention}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Je n'ai pas la permission d'envoyer des messages dans ce salon.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)


# ====================== Tes autres commandes (giveaway, role_manage, etc.) ======================
# Colle ici tout le reste de ton code (giveaway, role_manage, parse_duration, etc.)
# Je ne le recopie pas pour ne pas allonger inutilement, mais garde tout ce qui était avant.

# ====================== EVENTS ======================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    await bot.tree.sync()
    print("✅ Commandes slash synchronisées")


bot.run(DISCORD_TOKEN)
