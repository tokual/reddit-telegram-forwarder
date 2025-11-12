# Raspberry Pi Deployment Guide

## Prerequisites

1. **Python 3.8+** installed on Raspberry Pi
2. **FFmpeg** for video audio merging:
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```
3. **yt-dlp** for reliable Reddit video downloads (installed via pip - included in requirements.txt)
4. **HandBrake CLI** for professional video encoding (required for proper Telegram display):
   ```bash
   # On Raspberry Pi / Debian / Ubuntu:
   sudo apt install handbrake-cli
   
   # On macOS with Homebrew:
   brew install handbrake
   
   # On other systems, see: https://handbrake.fr/downloads.php
   ```

## Recent Fixes

### Video Processing Pipeline (All Issues Fixed ✅)

1. **Audio Download** - Videos now download with audio merged
   - ✅ Uses yt-dlp with FFmpeg merger
   - ✅ Automatic audio+video stream selection
   - ✅ Tested and verified

2. **FFmpeg Detection** - Properly detects FFmpeg location
   - ✅ Checks multiple standard paths
   - ✅ Enriches subprocess PATH environment
   - ✅ Works on Raspberry Pi and macOS

3. **Reddit Access** - 403 errors fixed with proper headers
   - ✅ Mozilla User-Agent headers
   - ✅ CORS and Range request support
   - ✅ Verified working with v.redd.it

4. **Telegram Display** - Videos now show thumbnails with correct aspect ratio
   - ✅ HandBrake encoding with `-a 1` (audio track)
   - ✅ AAC codec with `-E aac` (proper audio)
   - ✅ Web optimization with `--optimize` flag
   - ✅ Locally tested and verified

## Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd reddit-telegram-forwarder
   ```

2. **Set up Python environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your credentials
   ```

4. **Set up admin users:**
   ```bash
   nano admins.txt  # Add your Telegram user ID or @username
   ```

5. **Test the setup:**
   ```bash
   python verify_setup.py
   ```

## Running the Bot

### Auto-Start on Boot (Systemd - Recommended)

The bot_manager.sh setup script automatically creates a systemd service. After setup, the bot will start on boot:

```bash
# Check service status
systemctl status reddit-telegram-bot.service

# View service logs
sudo journalctl -u reddit-telegram-bot.service -f
```

### Manual Start
```bash
./bot_manager.sh start
```

### Check Status
```bash
./bot_manager.sh status
```

### Stop Bot
```bash
./bot_manager.sh stop
```

### View Logs
```bash
./bot_manager.sh logs
```

### Update Bot (pulls from git and restarts)
```bash
./bot_manager.sh update
```

## What to Expect After Update

After running `./bot_manager.sh update` on your Raspberry Pi:

- ✅ Videos download with audio merged in
- ✅ Videos display on Telegram with visible thumbnails
- ✅ Correct aspect ratio on Telegram mobile app
- ✅ All video playback working properly

## Modifying Systemd Service Configuration

If you need to modify the service configuration:

```bash
sudo nano /etc/systemd/system/reddit-telegram-bot.service
sudo systemctl daemon-reload
sudo systemctl restart reddit-telegram-bot.service
```

## Troubleshooting

### Check Logs
```bash
tail -f logs/bot.log
```

### Check System Service Logs
```bash
sudo journalctl -u reddit-telegram-bot.service -f
```

### Clear Database (if needed)
```bash
python clear_database.py
```

### Memory Issues
If the Pi runs out of memory during video processing, you can:
1. Increase swap space
2. Reduce `MAX_POSTS_PER_CHECK` in .env
3. Set up log rotation

## Performance Tips

1. **Log Rotation** (prevent disk fill):
   ```bash
   sudo nano /etc/logrotate.d/reddit-telegram-bot
   ```
   Add:
   ```
   /home/pi/reddit-telegram-forwarder/logs/*.log {
       daily
       missingok
       rotate 7
       compress
       delaycompress
       notifempty
       copytruncate
   }
   ```

2. **Temp File Cleanup**: The bot automatically cleans temp files after 24 hours

3. **Database Maintenance**: Periodically clear old posts if needed

## Security

- Keep `.env` file secure (never commit to git)
- Regularly update the bot and dependencies
- Monitor logs for suspicious activity
- Limit admin access appropriately
