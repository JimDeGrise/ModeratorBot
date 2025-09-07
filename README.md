# ModeratorBot

A sophisticated Telegram moderation bot with auto-mute functionality, rate limiting, and escalation logic. The bot automatically mutes users who send too many messages in a short time period and applies progressively longer mutes for repeat offenders.

## Features

### 🔇 Auto-Mute System
- **Rate Limiting**: Automatically mutes users who send 5+ messages within a 10-second sliding window
- **Escalation Logic**: Progressive mute durations for repeat violations (1h → 6h → 24h → 7d by default)
- **Non-blocking Design**: Handles multiple chats concurrently without performance issues
- **Smart Exemptions**: Admins and whitelisted users are automatically exempt from rate limiting

### 👮 Moderation Features
- **Manual Mute/Unmute**: Admin commands for manual moderation
- **User Status Tracking**: View violation history and current status for any user
- **Database Persistence**: All violations and user data stored in SQLite database
- **Admin Notifications**: Configurable notifications when auto-mutes occur

### ⚙️ Configuration
- **Flexible Settings**: Customizable rate limits, escalation durations, and notification options
- **Environment-based Config**: Easy configuration via `.env` file
- **Whitelist Support**: Exempt specific users from all moderation

## Installation & Setup

### Prerequisites
- Python 3.8 or higher
- A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather))

### 1. Clone the Repository
```bash
git clone https://github.com/JimDeGrise/ModeratorBot.git
cd ModeratorBot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configuration
Copy the example environment file and configure it:
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```env
# Required: Your bot token from @BotFather
BOT_TOKEN=your_telegram_bot_token_here

# Admin user IDs (comma-separated)
ADMIN_IDS=123456789,987654321

# Rate limiting settings
ANTIFLOOD_MAX_MESSAGES=5
ANTIFLOOD_WINDOW_SECONDS=10

# Escalation durations in minutes (1h,6h,24h,7d)
ESCALATION_DURATIONS=60,360,1440,10080

# Optional: Whitelisted users (exempt from rate limiting)
WHITELISTED_USERS=111111111,222222222

# Notification settings
NOTIFY_ADMINS=true
NOTIFICATION_CHAT=-1001234567890  # Optional: specific chat for notifications
```

### 4. Run the Bot
```bash
python bot.py
```

### 5. Add Bot to Group
1. Add the bot to your Telegram group
2. Make sure the bot has admin permissions:
   - Delete messages
   - Restrict members
   - Send messages

## Configuration Options

### Rate Limiting
| Setting | Default | Description |
|---------|---------|-------------|
| `ANTIFLOOD_MAX_MESSAGES` | `5` | Maximum messages allowed in time window |
| `ANTIFLOOD_WINDOW_SECONDS` | `10` | Time window in seconds |

### Escalation
| Setting | Default | Description |
|---------|---------|-------------|
| `ESCALATION_DURATIONS` | `60,360,1440,10080` | Mute durations in minutes for violations 1,2,3,4+ |

### Admin & Notifications
| Setting | Default | Description |
|---------|---------|-------------|
| `ADMIN_IDS` | - | Comma-separated admin user IDs |
| `WHITELISTED_USERS` | - | Comma-separated whitelisted user IDs |
| `NOTIFY_ADMINS` | `true` | Enable/disable admin notifications |
| `NOTIFICATION_CHAT` | - | Optional chat ID for notifications (if empty, sends to admin DMs) |

### Database
| Setting | Default | Description |
|---------|---------|-------------|
| `DB_PATH` | `./data/modbot.db` | Path to SQLite database file |

## Commands

### User Commands
- `/start` - Show welcome message and bot status
- `/help` - Display help information and available commands
- `/rules` - Show chat rules

### Admin Commands
- `/mute <reply> [duration]` - Manually mute a user (reply to their message, duration in minutes)
- `/unmute <reply>` - Unmute a user (reply to their message)
- `/status <reply>` - Check user's moderation status and violation history
- `/stats` - View bot statistics and performance metrics

## How It Works

### Rate Limiting Algorithm
The bot uses a **sliding window** rate limiting algorithm:

1. **Message Tracking**: Each message is timestamped and stored per user per chat
2. **Window Sliding**: Old messages outside the time window are automatically removed
3. **Threshold Check**: When message count exceeds the limit, auto-mute is triggered
4. **Concurrent Safety**: Thread-safe design handles multiple chats simultaneously

### Escalation System
When a user violates the rate limit:

1. **Violation Recording**: The violation is logged in the database
2. **History Check**: Bot checks user's violation count in the last 30 days
3. **Duration Calculation**: Mute duration is determined by escalation level
4. **Mute Application**: User is restricted from sending messages
5. **Admin Notification**: Admins are notified of the action

### Example Escalation
- **1st violation**: 1 hour mute
- **2nd violation**: 6 hour mute  
- **3rd violation**: 24 hour mute
- **4th+ violations**: 7 day mute

## Testing

Run the comprehensive test suite:
```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run specific test files
pytest tests/test_rate_limiter.py
pytest tests/test_escalation.py

# Run with coverage
pytest --cov=src tests/
```

### Test Coverage
- ✅ Rate limiter sliding window algorithm
- ✅ Escalation logic and violation tracking
- ✅ Database operations and data persistence
- ✅ Concurrent access and thread safety
- ✅ Configuration validation
- ✅ Admin/whitelist exemptions

## Database Schema

The bot uses SQLite with the following main table:

### user_violations
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `user_id` | INTEGER | Telegram user ID |
| `chat_id` | INTEGER | Telegram chat ID |
| `violation_type` | TEXT | Type of violation ('rate_limit', 'manual') |
| `timestamp` | TEXT | ISO timestamp of violation |
| `mute_duration_minutes` | INTEGER | Duration of applied mute |
| `is_active` | BOOLEAN | Whether violation is currently active |

## Monitoring & Maintenance

### Automatic Cleanup
The bot performs automatic maintenance:
- **Hourly**: Cleanup old rate limiter entries
- **Hourly**: Deactivate expired violations  
- **Daily**: Remove old database records (90+ days)

### Statistics
Use `/stats` command to monitor:
- Total and active violations
- Unique users and chats
- Rate limiter performance
- Configuration summary

## Troubleshooting

### Common Issues

**Bot not responding to commands:**
- Verify the bot token is correct
- Ensure bot has admin permissions in the group
- Check bot is not muted or restricted

**Auto-mute not working:**
- Confirm bot has "Restrict members" permission
- Verify rate limiting settings in `.env`
- Check admin/whitelist exemptions

**Database errors:**
- Ensure `data/` directory exists and is writable
- Check database path in configuration
- Verify SQLite is installed

### Debug Mode
Enable debug logging by setting:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check existing issues for solutions
- Review the troubleshooting section