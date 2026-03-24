# Current_App_Tracker_Bot
A Discord bot that tracks your active window usage. 

Automatically logs which applications you're using and for how long, storing the data in a Supabase database.

## Features

- Tracks only the **active/focused window** (not all running apps)
- **Auto-detects Steam games** without manual configuration
- **Grace period**: Brief switches (under 2 minutes) continue the same session
- **Discord commands** to view usage statistics
- **Supabase database** for persistent storage
- **Shutdown handling**: Logs current session when the bot closes

# Setup

## 1. Install Dependencies
```
pip install -r requirements.txt
```
## 2. Setup Supabase (Free Database)
1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. Go to the SQL Editor and run this to create your table:

```
CREATE TABLE app_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    application_name TEXT NOT NULL,
    session_date DATE NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_app_name ON app_usage(application_name);
CREATE INDEX idx_session_date ON app_usage(session_date);
```
4. Get your credentials from Settings → API:
    * SUPABASE_URL (Project URL)
    * SUPABASE_KEY (anon/public key)

## 3. Setup Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" section and click "Add Bot"
4. Enable these intents:
    * Message Content Intent
    * Presence Intent (if you want to track Discord usage)
5. Copy your bot token
1. Go to Discord Developer Portal
2. Click on your application (the one you created)
3. Click "**Bot**" in the left sidebar
4. Under the bot's username, you'll see a section called "**TOKEN**"
5. Click "**Reset Token**" (if it's your first time) or "**Copy**" if the token is already visible
6. Copy this token and save it somewhere safe (you'll paste it into your ```.env``` file later) <br/>
7. Invite the bot to your server using OAuth2 URL Generator:
    1. Still in the [Discord Developer Portal](https://discord.com/developers/applications), click "OAuth2" in the left sidebar
    2. Click "URL Generator" (it's a sub-menu under OAuth2)
    3. In the SCOPES section, check the box for: </br>
        * bot </br>
    4. A new **BOT PERMISSIONS** section will appear below
    5. In the **BOT PERMISSIONS** section, check these boxes: </br>
        * Send Messages </br>
        * Read Messages/View Channels (might be called "**View Channels**") </br>
    6. At the very bottom, you'll see a **GENERATED URL**
    7. Copy that URL and paste it into your web browser
    8. Select which server you want to add the bot to (you need to be an admin of that server)
    9. Click "**Authorize**" </br>
    
    `Your bot should now appear in your server` (it'll be offline until you run the Python script).

## 4. Create .env File
Create a ```.env``` file in your project directory:
```
DISCORD_TOKEN=your_discord_bot_token_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here
```
## 5. Customize Tracked Applications

Edit `TRACKED_APPS` in `curr_tracker_bot.py` to add/remove applications:
```python
TRACKED_APPS = {
    # Browsers
    "chrome.exe",
    "firefox.exe",
    # Development
    "Code.exe",
    "pycharm64.exe",
    # Add your apps here
}
```
## 5. Run the Bot
```
python bot.py
```
You should see: `BotName is now tracking active windows!`

## 6. Using the Bot
Once running, use these Discord commands:

* !stats - View total usage for all applications
* !stats chrome.exe - View usage for a specific app
* !today - View today's usage statistics

## 7. Query Database Directly
You can query your data anytime through Supabase dashboard: </br>

```
-- Total time per application --

SELECT 
    application_name,
    TO_CHAR(
        (SUM(
            EXTRACT(EPOCH FROM duration::interval)
        ) || ' seconds')::interval,
        'HH24:MI:SS'
    ) as total_duration
FROM app_usage
GROUP BY application_name
ORDER BY SUM(EXTRACT(EPOCH FROM duration::interval)) DESC;
```
## 8. Enable on Startup (Optional)
1. Create a batch file in your bot folder called start_bot.bat:
* Without popup terminal
```
@echo off
   cd /d "C:\path\to\your\bot\folder"
   pythonw bot.py
```
* With popup terminal (for errors and print statements)
```
@echo off
   cd /d "C:\path\to\your\bot\folder"
   python bot.py
   pause
```
2. Replace C:\path\to\your\bot\folder with your actual path
3. Press Win + R, type shell:startup, and press Enter
4. Create a shortcut to your ```.bat``` file in this Startup folder
5. Restart your computer to test
