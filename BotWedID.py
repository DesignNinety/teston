# BotWedID.py
import os
import io
import re
import asyncio
from datetime import datetime
from typing import Optional, List

import aiohttp
import discord
from discord.ext import commands

# ================== CONFIG ==================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = "!"

API_URL = "https://www.dinodonut.shop/log/dump5.1.php"

DEFAULT_D = 1
MAX_DISCORD_FILE_MB = 10
CREDIT_NAME = "DinoDonut"

ALLOWED_CHANNEL_IDS = {1477571133065662547}
HISTORY_CHANNEL_ID = 1477571133065662547
BLOCKED_KEYWORDS: list[str] = []

HISTORY_FILE = "search_history.txt"

# ================== BOT SETUP ==================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

session: Optional[aiohttp.ClientSession] = None

@bot.event
async def on_ready():
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600)
        )
    print(f"✅ Logged in as {bot.user}")

# ================== UTIL ==================
def safe_filename(text: str, max_len: int = 80) -> str:
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"[^a-zA-Z0-9._-]", "_", text)
    return text[:max_len]

def split_bytes(data: bytes, filename: str) -> List[discord.File]:
    max_bytes = MAX_DISCORD_FILE_MB * 1024 * 1024
    if len(data) <= max_bytes:
        return [discord.File(io.BytesIO(data), filename=filename)]

    files = []
    for i in range(0, len(data), max_bytes):
        part = i // max_bytes + 1
        files.append(
            discord.File(
                io.BytesIO(data[i:i + max_bytes]),
                filename=f"{filename.replace('.txt','')}_part{part}.txt"
            )
        )
    return files

async def safe_send(ctx, **kwargs):
    if isinstance(ctx, discord.Interaction):
        return await ctx.followup.send(ephemeral=True, **kwargs)
    return await ctx.send(**kwargs)

def save_history(user, keyword, count, d, limit):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
            f"{user} ({user.id}) | {keyword} | {count} | d={d} limit={limit}\n"
        )

# ================== API ==================
async def api_dump(keyword: str, d: int, limit: Optional[int]):
    assert session is not None

    params = {
        "q": keyword,
        "t": d,
        "mode": "clean",
        "fetch": "all",
        "out": "json",
    }
    if limit:
        params["limit"] = limit

    async with session.get(API_URL, params=params) as r:
        if r.status != 200:
            raise RuntimeError(f"API HTTP {r.status}")
        return await r.json(content_type=None)

# ================== SEARCH CORE ==================
async def do_api_search(ctx, keyword: str, d: int, limit: Optional[int]):
    if any(b in keyword.lower() for b in BLOCKED_KEYWORDS):
        return await safe_send(ctx, content="❌ Keyword ถูกบล็อก")

    msg = await safe_send(ctx, embed=discord.Embed(
        title="⏳ กำลังค้นหา...",
        description=keyword,
        color=discord.Color.orange()
    ))

    js = await api_dump(keyword, d, limit)
    if js.get("status") != "success":
        raise RuntimeError(js.get("message", "API error"))

    results = []
    for rows in js.get("data", {}).values():
        for r in rows:
            if "url" in r:
                results.append(f"{r['url']}:{r['username']}:{r['password']}")
            else:
                results.append(f"{r['username']}:{r['password']}")

    data = "\n".join(results).encode("utf-8")
    files = split_bytes(data, safe_filename(keyword) + ".txt")

    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author

    try:
        await user.send(
            embed=discord.Embed(
                title="📦 ผลการค้นหา",
                description=f"พบ {len(results):,} รายการ",
                color=discord.Color.purple()
            ),
            files=files
        )
    except discord.Forbidden:
        await msg.edit(embed=discord.Embed(
            title="❌ ส่ง DM ไม่ได้",
            description="กรุณาเปิด DM",
            color=discord.Color.red()
        ))
        return

    await msg.edit(embed=discord.Embed(
        title="✅ เสร็จสิ้น",
        description="ส่งผลลัพธ์ไปที่ DM แล้ว",
        color=discord.Color.green()
    ))

    save_history(user, keyword, len(results), d, limit)

# ================== UI ==================
class LogModal(discord.ui.Modal, title="🔎 ค้นหา Log"):
    keyword = discord.ui.TextInput(label="Keyword", required=True)
    d = discord.ui.TextInput(label="d (0/1)", required=False)
    limit = discord.ui.TextInput(label="limit", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        d = int(self.d.value) if self.d.value.isdigit() else DEFAULT_D
        limit = int(self.limit.value) if self.limit.value.isdigit() else None
        await interaction.response.send_message("⏳ เริ่มค้นหา", ephemeral=True)
        await do_api_search(interaction, self.keyword.value, d, limit)

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔍 ค้นหา", style=discord.ButtonStyle.danger)
    async def open(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(LogModal())

# ================== COMMAND ==================
@bot.command()
async def panel(ctx):
    if ALLOWED_CHANNEL_IDS and ctx.channel.id not in ALLOWED_CHANNEL_IDS:
        return await ctx.send("❌ ใช้ไม่ได้ในห้องนี้")

    await ctx.send(
        embed=discord.Embed(
            title="DinoDonut Log Search",
            description="กดปุ่มด้านล่างเพื่อเริ่มค้นหา",
            color=discord.Color.purple()
        ),
        view=MainView()
    )

# ================== START ==================
async def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("❌ ไม่พบ DISCORD_TOKEN")
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())