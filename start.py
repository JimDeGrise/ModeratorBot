#!/usr/bin/env python3
"""Startup script for ModeratorBot."""
import sys
import os

def check_requirements():
    """Check if all requirements are met."""
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required")
        return False
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found")
        print("📋 Please copy .env.example to .env and configure it:")
        print("   cp .env.example .env")
        return False
    
    # Check if BOT_TOKEN is set
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv('BOT_TOKEN'):
        print("❌ Error: BOT_TOKEN not set in .env file")
        print("📋 Please add your bot token to .env file:")
        print("   BOT_TOKEN=your_telegram_bot_token_here")
        return False
    
    # Check if data directory exists
    if not os.path.exists('data'):
        print("📁 Creating data directory...")
        os.makedirs('data', exist_ok=True)
    
    return True

def main():
    """Main startup function."""
    print("🤖 Starting ModeratorBot...")
    print("=" * 40)
    
    if not check_requirements():
        sys.exit(1)
    
    print("✅ All requirements met")
    print("🚀 Launching bot...")
    
    # Import and run the bot
    try:
        import asyncio
        from bot import main as bot_main
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()