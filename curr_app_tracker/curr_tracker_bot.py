import discord
from discord.ext import commands, tasks
import datetime
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import platform
import signal
import sys

# Platform-specific imports for getting active window
if platform.system() == "Windows":
    import win32gui
    import win32process
    import psutil
elif platform.system() == "Darwin":  # macOS
    from AppKit import NSWorkspace
elif platform.system() == "Linux":
    import subprocess

load_dotenv()

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Track current active app
current_app = None
session_start = None
previous_app = None
grace_period_start = None
MIN_SESSION_DURATION = 120  # Only log sessions longer than this (in seconds)
GRACE_PERIOD = 120  # If we return within this time, continue the session (in seconds)

# Applications to track - add your apps here!
TRACKED_APPS = {
    # Browsers
    "chrome.exe",
    "firefox.exe",
    # Development
    "Code.exe",  # VS Code
    "idea64.exe",
    "pycharm64.exe",
    # Communication
    "Discord.exe",
    "Teams.exe",
    # Games
    "VALORANT-Win64-Shipping.exe",
    "Minecraft.exe",
    "RocketLeague.exe",
    # Media
    "Spotify.exe",
    "stremio-shell-ng.exe",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_all_rows(query_fn):
    """Fetch all rows from Supabase using pagination, bypassing the 100 row default limit."""
    all_rows = []
    page = 0
    page_size = 1000
    while True:
        start = page * page_size
        end = (page + 1) * page_size - 1
        response = query_fn(start, end)
        all_rows.extend(response.data)
        if len(response.data) < page_size:
            break
        page += 1
    return all_rows


def parse_duration_to_seconds(duration_str):
    """Parse HH:MM:SS string to total seconds."""
    try:
        h, m, s = map(int, duration_str.split(':'))
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


def format_duration(seconds):
    """Format seconds as a human-readable string like 2h 15m."""
    total_minutes = seconds // 60
    if total_minutes >= 60:
        return f"{total_minutes // 60}h {total_minutes % 60}m"
    return f"{total_minutes}m"


def get_active_window_name():
    """Get the name of the currently active/focused window."""
    try:
        if platform.system() == "Windows":
            window = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(window)
            process = psutil.Process(pid)
            return process.name()
        elif platform.system() == "Darwin":
            active_app = NSWorkspace.sharedWorkspace().activeApplication()
            return active_app['NSApplicationName'] + ".app"
        elif platform.system() == "Linux":
            result = subprocess.run(
                ['xdotool', 'getactivewindow', 'getwindowname'],
                capture_output=True, text=True
            )
            return result.stdout.strip()
    except Exception as e:
        print(f"Error getting active window: {e}")
        return None


def should_track(app_name):
    """Check if app should be tracked (case-insensitive, Steam games included)."""
    if not app_name:
        return False

    try:
        if platform.system() == "Windows":
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info['name'] == app_name and proc.info['exe']:
                    if 'steam' in proc.info['exe'].lower() and 'steamapps' in proc.info['exe'].lower():
                        return True
    except Exception:
        pass

    tracked_lower = {app.lower() for app in TRACKED_APPS}
    return app_name.lower() in tracked_lower


def log_session(app, start_time, end_time):
    """Log a completed session to the database."""
    duration = (end_time - start_time).total_seconds()

    if duration <= MIN_SESSION_DURATION:
        print(f"Skipped (too short): {app} - {duration:.0f}s")
        return

    try:
        session_date = start_time.strftime("%Y-%m-%d")
        start_formatted = start_time.strftime("%H:%M:%S")
        end_formatted = end_time.strftime("%H:%M:%S")

        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        data = {
            "user_id": str(bot.user.id),
            "application_name": app,
            "session_date": session_date,
            "start_time": start_formatted,
            "end_time": end_formatted,
            "duration": duration_formatted
        }
        supabase.table("app_usage").insert(data).execute()
        print(f"Logged: {app} - {duration_formatted}")
    except Exception as e:
        print(f"Error logging {app}: {e}")


def build_app_totals(rows):
    """Sum durations per app from a list of rows."""
    app_totals = {}
    for row in rows:
        app = row['application_name']
        app_totals[app] = app_totals.get(app, 0) + parse_duration_to_seconds(row['duration'])
    return app_totals


def build_message(title, app_totals):
    """Build a formatted message string from app totals dict."""
    sorted_apps = sorted(app_totals.items(), key=lambda x: x[1], reverse=True)
    message = f"**{title} ({len(sorted_apps)} apps):**\n"
    for app, seconds in sorted_apps:
        message += f"• {app}: {format_duration(seconds)}\n"
    return message


async def send_long_message(ctx, message):
    """Send a message, splitting it if it exceeds Discord's 2000 char limit."""
    while len(message) > 2000:
        await ctx.send(message[:2000])
        message = message[2000:]
    await ctx.send(message)


# ── Bot events ────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f'{bot.user} is now tracking active windows!')
    track_active_window.start()


def shutdown_handler(signum, frame):
    """Handle shutdown gracefully and log current session."""
    global current_app, session_start, previous_app, grace_period_start

    print("\nShutting down bot...")

    if current_app and session_start:
        log_session(current_app, session_start, datetime.datetime.now())
        print(f"Logged final session: {current_app}")

    print("Bot stopped successfully")
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


# ── Background task ───────────────────────────────────────────────────────────

@tasks.loop(seconds=10)
async def track_active_window():
    """Monitor active window and log when it changes."""
    global current_app, session_start, previous_app, grace_period_start

    active_app = get_active_window_name()

    if not should_track(active_app):
        if current_app and not grace_period_start:
            app_still_running = False
            try:
                if platform.system() == "Windows":
                    for proc in psutil.process_iter(['name']):
                        if proc.info['name'] == current_app:
                            app_still_running = True
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
                pass

            if app_still_running:
                previous_app = current_app
                grace_period_start = datetime.datetime.now()
                current_app = None
                print(f"Grace period started for {previous_app}")
            else:
                log_session(current_app, session_start, datetime.datetime.now())
                current_app = None
                session_start = None

        if grace_period_start:
            elapsed = (datetime.datetime.now() - grace_period_start).total_seconds()
            if elapsed > GRACE_PERIOD:
                if previous_app:
                    log_session(previous_app, session_start, grace_period_start)
                current_app = None
                session_start = None
                previous_app = None
                grace_period_start = None
        return

    if grace_period_start and active_app == previous_app:
        print(f"Returned to {active_app} within grace period - continuing session")
        current_app = previous_app
        previous_app = None
        grace_period_start = None
        return

    if grace_period_start:
        log_session(previous_app, session_start, grace_period_start)
        previous_app = None
        grace_period_start = None

    if active_app != current_app:
        if current_app:
            log_session(current_app, session_start, datetime.datetime.now())
        current_app = active_app
        session_start = datetime.datetime.now()
        print(f"Now tracking: {current_app}")


# ── Commands ──────────────────────────────────────────────────────────────────

@bot.command()
async def stats(ctx, app_name: str = None):
    """Get usage statistics. Use !stats for all apps, or !stats <appname> for one."""
    try:
        if app_name:
            rows = fetch_all_rows(
                lambda s, e: supabase.table("app_usage").select("application_name, duration")
                    .ilike("application_name", app_name).range(s, e).execute()
            )
            if not rows:
                await ctx.send(f"No data found for **{app_name}**")
                return
            total_seconds = sum(parse_duration_to_seconds(r['duration']) for r in rows)
            await ctx.send(f"**{rows[0]['application_name']}**: {format_duration(total_seconds)} total")

        else:
            rows = fetch_all_rows(
                lambda s, e: supabase.table("app_usage").select("application_name, duration")
                    .range(s, e).execute()
            )
            if not rows:
                await ctx.send("No usage data found!")
                return
            app_totals = build_app_totals(rows)
            await send_long_message(ctx, build_message("All Applications", app_totals))

    except Exception as e:
        await ctx.send(f"Error fetching stats: {e}")


@bot.command()
async def today(ctx):
    """Get today's usage statistics."""
    try:
        today_date = datetime.datetime.now().strftime("%Y-%m-%d")
        rows = fetch_all_rows(
            lambda s, e: supabase.table("app_usage").select("application_name, duration")
                .eq("session_date", today_date).range(s, e).execute()
        )
        if not rows:
            await ctx.send("No usage data for today!")
            return
        app_totals = build_app_totals(rows)
        await send_long_message(ctx, build_message("Today's Usage", app_totals))

    except Exception as e:
        await ctx.send(f"Error fetching today's stats: {e}")


@bot.command()
async def week(ctx):
    """Get this week's usage statistics."""
    try:
        today = datetime.datetime.now()
        week_start = (today - datetime.timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        today_date = today.strftime("%Y-%m-%d")
        rows = fetch_all_rows(
            lambda s, e: supabase.table("app_usage").select("application_name, duration")
                .gte("session_date", week_start).lte("session_date", today_date).range(s, e).execute()
        )
        if not rows:
            await ctx.send("No usage data for this week!")
            return
        app_totals = build_app_totals(rows)
        await send_long_message(ctx, build_message("This Week's Usage", app_totals))

    except Exception as e:
        await ctx.send(f"Error fetching weekly stats: {e}")


@bot.command()
async def apps(ctx):
    """List all unique applications that have been tracked."""
    try:
        rows = fetch_all_rows(
            lambda s, e: supabase.table("app_usage").select("application_name")
                .range(s, e).execute()
        )
        if not rows:
            await ctx.send("No applications tracked yet!")
            return
        unique_apps = sorted(set(row['application_name'] for row in rows))
        message = f"**Tracked Applications ({len(unique_apps)} total):**\n"
        for app in unique_apps:
            message += f"• {app}\n"
        await send_long_message(ctx, message)

    except Exception as e:
        await ctx.send(f"Error fetching apps: {e}")


# ── Run ───────────────────────────────────────────────────────────────────────

try:
    bot.run(os.getenv("DISCORD_TOKEN"))
except KeyboardInterrupt:
    shutdown_handler(None, None)