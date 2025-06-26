# Raspberry Pi Deployment Guide

## Prerequisites

1. **Python 3.8+** installed on Raspberry Pi
2. **FFmpeg** for video processing:
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```

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

## Auto-Start on Boot (Systemd)

1. **Create systemd service:**
   ```bash
   sudo nano /etc/systemd/system/reddit-telegram-bot.service
   ```

2. **Add service configuration:**
   ```ini
   [Unit]
   Description=Reddit Telegram Forwarder Bot
   After=network.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/reddit-telegram-forwarder
   Environment=PATH=/home/pi/reddit-telegram-forwarder/.venv/bin
   ExecStart=/home/pi/reddit-telegram-forwarder/.venv/bin/python main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable reddit-telegram-bot.service
   sudo systemctl start reddit-telegram-bot.service
   ```

4. **Check service status:**
   ```bash
   sudo systemctl status reddit-telegram-bot.service
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
