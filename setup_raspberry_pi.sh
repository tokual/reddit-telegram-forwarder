#!/bin/bash
# Raspberry Pi Optimization Setup Script

echo "🍓 Setting up Raspberry Pi optimizations for Reddit Telegram Bot"
echo "================================================================"

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ Please run this script from the reddit-telegram-forwarder directory"
    exit 1
fi

# Update .env file with Raspberry Pi settings
echo "📝 Updating .env file with Raspberry Pi optimizations..."

if [ -f ".env" ]; then
    # Backup existing .env
    cp .env .env.backup
    echo "✅ Backed up existing .env to .env.backup"
    
    # Add or update Raspberry Pi settings
    grep -q "RASPBERRY_PI_MODE" .env || echo "RASPBERRY_PI_MODE=true" >> .env
    grep -q "VIDEO_TIMEOUT_SECONDS" .env || echo "VIDEO_TIMEOUT_SECONDS=120" >> .env
    grep -q "AUDIO_TIMEOUT_SECONDS" .env || echo "AUDIO_TIMEOUT_SECONDS=60" >> .env
    grep -q "FFMPEG_THREADS" .env || echo "FFMPEG_THREADS=2" >> .env
    
    # Update existing values to be Raspberry Pi friendly
    sed -i 's/MAX_POSTS_PER_CHECK=.*/MAX_POSTS_PER_CHECK=3/' .env
    sed -i 's/LOG_LEVEL=.*/LOG_LEVEL=DEBUG/' .env
    sed -i 's/RASPBERRY_PI_MODE=.*/RASPBERRY_PI_MODE=true/' .env
    
    echo "✅ Updated .env file"
else
    echo "⚠️  No .env file found. Please copy .env.example to .env first"
    exit 1
fi

# Check system requirements
echo ""
echo "🔍 Checking system requirements..."

# Check FFmpeg
if command -v ffmpeg &> /dev/null; then
    echo "✅ FFmpeg is installed"
    ffmpeg -version | head -1
else
    echo "❌ FFmpeg is not installed. Please run: sudo apt install ffmpeg"
    exit 1
fi

# Check memory
echo ""
echo "💾 Memory information:"
grep -E "(MemTotal|MemAvailable|SwapTotal)" /proc/meminfo

# Check available disk space
echo ""
echo "💿 Disk space:"
df -h . | tail -1

# Check Python virtual environment
echo ""
echo "🐍 Python environment check..."
if [ -d ".venv" ]; then
    echo "✅ Virtual environment exists"
    source .venv/bin/activate
    python --version
    echo "📦 Checking required packages..."
    pip list | grep -E "(ffmpeg-python|praw|python-telegram-bot|requests)" || echo "⚠️  Some packages may be missing"
else
    echo "❌ Virtual environment not found. Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Create diagnostic script shortcut
echo ""
echo "🔧 Setting up diagnostic tools..."
chmod +x debug_audio_issue.py
echo "✅ Made debug script executable"

echo ""
echo "🎉 Raspberry Pi optimization setup complete!"
echo ""
echo "Next steps:"
echo "1. Run the audio diagnostic: python3 debug_audio_issue.py"
echo "2. If diagnostics pass, restart your bot: ./bot_manager.sh restart"
echo "3. Monitor logs with: tail -f logs/bot.log"
echo "4. If issues persist, check the logs for specific error messages"
echo ""
echo "Raspberry Pi optimizations applied:"
echo "- ✅ Raspberry Pi mode enabled"
echo "- ✅ Increased timeouts (video: 120s, audio: 60s)"
echo "- ✅ Limited FFmpeg threads to 2"
echo "- ✅ Reduced concurrent posts to 3"
echo "- ✅ Debug logging enabled"
