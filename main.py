import discord
from discord.ext import commands
import json
import os
import asyncio

# ==========================================
# PENGATURAN BOT
# ==========================================

import os

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN belum diatur")

DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "message_counts.json"
)

RENAME_DELAY = 10  # Jeda antarperubahan nama channel (detik)

# ==========================================
# PENGATURAN DISCORD
# ==========================================

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

message_counts = {}
channel_locks = {}
rename_queue = asyncio.Queue()
queued_channels = set()


# ==========================================
# PENYIMPANAN JUMLAH PESAN
# ==========================================

def load_counts():
    global message_counts

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                message_counts = json.load(file)

        except (json.JSONDecodeError, OSError) as error:
            print(f"Gagal membaca data: {error}")
            message_counts = {}
    else:
        message_counts = {}


def save_counts():
    temp_file = DATA_FILE + ".tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(message_counts, file, indent=2)

        os.replace(temp_file, DATA_FILE)

    except OSError as error:
        print(f"Gagal menyimpan data: {error}")


def get_count(channel_id):
    return int(message_counts.get(str(channel_id), 0))


def set_count(channel_id, count):
    message_counts[str(channel_id)] = count
    save_counts()


def get_channel_lock(channel_id):
    if channel_id not in channel_locks:
        channel_locks[channel_id] = asyncio.Lock()

    return channel_locks[channel_id]


# ==========================================
# ANTREAN PEMBARUAN NAMA CHANNEL
# ==========================================

async def queue_rename(channel):
    if channel.id not in queued_channels:
        queued_channels.add(channel.id)
        await rename_queue.put(channel)


async def update_channel_name(channel):
    while True:
        target_name = f"General-{get_count(channel.id)}"

        if channel.name == target_name:
            return

        try:
            await channel.edit(
                name=target_name,
                reason="Pembaruan jumlah pesan otomatis"
            )

            print(f"Nama channel diperbarui: {target_name}")

            await asyncio.sleep(RENAME_DELAY)

        except discord.Forbidden:
            print(
                f"Tidak punya izin mengubah nama: "
                f"#{channel.name}"
            )
            return

        except discord.HTTPException as error:
            print(
                f"Gagal mengubah nama #{channel.name}: "
                f"{error}"
            )
            return


async def rename_worker():
    while True:
        channel = await rename_queue.get()

        try:
            await update_channel_name(channel)

        except Exception as error:
            print(f"Kesalahan pembaruan channel: {error}")

        finally:
            queued_channels.discard(channel.id)
            rename_queue.task_done()


# ==========================================
# PEMINDAIAN RIWAYAT PESAN
# ==========================================

async def scan_channel(channel):
    lock = get_channel_lock(channel.id)

    async with lock:
        # Jika sudah pernah dihitung, gunakan data tersimpan.
        if str(channel.id) in message_counts:
            return

        print(f"Menghitung riwayat: #{channel.name}")

        total = 0

        try:
            async for _ in channel.history(
                limit=None,
                oldest_first=True
            ):
                total += 1

            set_count(channel.id, total)

            print(
                f"Riwayat #{channel.name}: "
                f"{total} pesan"
            )

        except discord.Forbidden:
            print(
                f"Tidak bisa membaca riwayat "
                f"#{channel.name}. Periksa izin bot."
            )

        except discord.HTTPException as error:
            print(
                f"Gagal membaca riwayat "
                f"#{channel.name}: {error}"
            )


# ==========================================
# BOT SIAP BERJALAN
# ==========================================

@bot.event
async def on_ready():
    load_counts()

    print("=" * 40)
    print(f"Bot aktif sebagai {bot.user}")
    print("Memeriksa channel server...")
    print("=" * 40)

    if not getattr(bot, "worker_started", False):
        bot.worker_started = True
        asyncio.create_task(rename_worker())

    for guild in bot.guilds:
        print(f"Server: {guild.name}")

        for channel in guild.text_channels:
            await scan_channel(channel)
            await queue_rename(channel)

    print("Pemeriksaan channel selesai.")


# ==========================================
# PESAN BARU
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not isinstance(message.channel, discord.TextChannel):
        return

    channel = message.channel
    lock = get_channel_lock(channel.id)

    async with lock:
        current_count = get_count(channel.id)

        # Jika channel belum pernah dihitung, lakukan
        # pemindaian awal sebelum menambahkan pesan baru.
        if str(channel.id) not in message_counts:
            total = 0

            try:
                async for _ in channel.history(
                    limit=None,
                    oldest_first=True
                ):
                    total += 1

                set_count(channel.id, total)

            except discord.HTTPException as error:
                print(f"Gagal menghitung riwayat: {error}")
                return

            # Pesan baru ini sudah termasuk dalam riwayat.
            current_count = total

        else:
            # Tambahkan satu untuk setiap pesan baru.
            current_count += 1
            set_count(channel.id, current_count)

        print(
            f"Pesan baru di #{channel.name} | "
            f"Total: {current_count}"
        )

    await queue_rename(channel)
    await bot.process_commands(message)


# ==========================================
# CHANNEL BARU
# ==========================================

@bot.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.TextChannel):
        set_count(channel.id, 0)
        await queue_rename(channel)


# ==========================================
# JALANKAN BOT
# ==========================================

load_counts()

if TOKEN == "MASUKKAN_TOKEN_BOT_DI_SINI":
    raise SystemExit(
        "Masukkan token bot terlebih dahulu "
        "pada variabel TOKEN."
    )

bot.run(TOKEN)
