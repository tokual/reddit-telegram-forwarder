# Reddit Telegram Forwarder Bot

A Telegram bot that scrapes Reddit posts and forwards them to Telegram channels after admin approval.

## Features

- 🔍 Scrapes images/videos from specified subreddits
- ✅ Admin approval workflow before forwarding
- 🚫 Duplicate prevention
- ⏰ Configurable check frequency
- � Whitelist-based admin access

## Quick Setup

### 1. Install & Configure

```bash
git clone <your-repo-url>
cd reddit-telegram-forwarder
./bot_manager.sh setup
```

### 2. Configure Credentials

Edit `.env` with your API credentials:

```bash
# Get from https://t.me/BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Get from https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
```

### 3. Add Admins

Edit `admins.txt` with your Telegram user ID:

```
123456789
```

### 4. Start Bot

```bash
./bot_manager.sh start
```

## Usage

1. **Create Rule**: Send `/add_rule` to the bot
2. **Configure**: Set subreddit, sort type, frequency, target channel
3. **Approve Posts**: Bot sends posts for your approval
4. **Auto-Forward**: Approved posts go to your channel

**Important**: Add the bot as admin to your target channel!

## Management

```bash
./bot_manager.sh start     # Start bot
./bot_manager.sh stop      # Stop bot
./bot_manager.sh restart   # Restart bot
./bot_manager.sh status    # Check status
./bot_manager.sh logs      # View logs
./bot_manager.sh update    # Update from git
```

## Getting API Keys

### Telegram Bot
1. Message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow instructions
3. Copy the bot token to `.env`

### Reddit API
1. Go to [Reddit Apps](https://www.reddit.com/prefs/apps)
2. Click "Create App" → "script"
3. Copy client ID and secret to `.env`

## Commands

- `/add_rule` - Create forwarding rule
- `/list_rules` - Manage existing rules
- `/status` - Bot statistics
- `/help` - Help information

## Troubleshooting

**Bot not responding**: Check `./bot_manager.sh logs`
**No posts found**: Verify Reddit credentials and subreddit name
**Channel errors**: Ensure bot is admin in target channel
**Permission denied**: Check file permissions on bot_manager.sh

## Requirements

- Python 3.8+
- Internet connection
- Telegram Bot Token
- Reddit API credentials