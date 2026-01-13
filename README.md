# 🔥 SMG-Forcer Telegram Bot

A powerful Telegram bot with AI capabilities, subscription management, payment integration, and comprehensive admin controls.

## ✨ Features

### User Features
- 🤖 AI-powered conversations using DeepSeek API
- 📊 Free tier with daily request limits
- 💳 Subscription plans (Test, Premium)
- 🎁 Referral system with bonuses
- 📈 Account status tracking
- 💬 Conversation management

### Admin Features
- 🎛️ Comprehensive admin dashboard
- 👥 User management (view, upgrade, downgrade)
- 🚫 User blocking/unblocking
- ⏱️ Temporary upgrades (10min, 1day, 7days)
- 🔢 Custom request amounts
- 💰 Payment monitoring
- 📊 Statistics and analytics

### Payment Integration
- 💳 OxaPay crypto payment support
- 🔄 Automatic subscription activation
- 📝 Payment history tracking

## 🚀 Quick Start

### Easy Installation (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/smg-forcer-bot.git
cd smg-forcer-bot

# 2. Run the setup script
python setup.py
```

The setup script will:
- ✅ Check Python version
- ✅ Install all dependencies
- ✅ Create configuration file (.hacx)
- ✅ Help you add admin users
- ✅ Verify the setup

### Manual Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy environment template
cp .env.example .hacx

# 3. Edit .hacx and add your credentials
# Required:
#   - TELEGRAM_BOT_TOKEN
#   - SMG-Forcer-API (DeepSeek API key)

# 4. Add admin user
python add_admin.py YOUR_TELEGRAM_USER_ID

# 5. Start the bot
python telegram_bot.py
```

## 📋 Requirements

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- DeepSeek API Key
- OxaPay credentials (optional, for payments)

## ⚙️ Configuration

### Environment Variables (.hacx file)

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
SMG-Forcer-API=sk-your-deepseek-api-key-here

# Optional - Backup API keys
DEEPSEEK_API_KEY_2=sk-backup-key-2
DEEPSEEK_API_KEY_3=sk-backup-key-3

# Optional - Payment integration
OXAPAY_API_KEY=your_oxapay_api_key
OXAPAY_MERCHANT_ID=your_merchant_id

# Optional - Production mode
PRODUCTION_MODE=false
```

### Admin Setup

**Option 1: Using script**
```bash
python add_admin.py YOUR_TELEGRAM_USER_ID
```

**Option 2: Using admins.txt**
```bash
# Add user IDs to admins.txt (one per line)
echo "YOUR_USER_ID" >> admins.txt
python sync_admins.py
```

## 📖 Commands

### User Commands
- `/start` - Start the bot and see welcome message
- `/help` - Show help information
- `/status` - View account status and plan
- `/plans` - View available subscription plans
- `/subscribe` - Subscribe to a plan
- `/referral` - Get your referral code
- `/new` - Start a new conversation
- `/myid` - Get your Telegram user ID

### Admin Commands
- `/admin` - Open admin dashboard
- `/admin_users` - View all users
- `/admin_add USER_ID` - Add admin user
- `/admin_upgrade USER_ID DURATION` - Upgrade user manually

## 🔧 Backup & Restore

### Create Backup
```bash
python backup_restore.py backup
```

This backs up:
- `.hacx` (configuration)
- `admins.txt` (admin list)
- `smg_forcer.db` (database)

### Restore Backup
```bash
python backup_restore.py restore
```

### List Backups
```bash
python backup_restore.py list
```

## 🛡️ Security

- ✅ Admin-only features are protected
- ✅ Users cannot block/downgrade admins
- ✅ Blocked users cannot use the bot
- ✅ Input validation on all user inputs
- ✅ Secure API key storage

## 📊 Database

The bot uses SQLite database (`smg_forcer.db`) that is automatically created on first run.

**Tables:**
- `users` - User information and blocking status
- `subscriptions` - Active and expired subscriptions
- `payments` - Payment history
- `admins` - Admin users
- `daily_usage` - Daily usage tracking
- `referral_transactions` - Referral bonuses

## 🐛 Troubleshooting

### Bot Not Starting
1. Check `.hacx` file exists and has correct token
2. Verify Python dependencies: `pip install -r requirements.txt`
3. Run verification: `python production_setup.py`

### Database Issues
1. Check file permissions
2. Verify database file exists
3. Check for database locks

### Payment Issues
1. Verify OxaPay API credentials
2. Check webhook URL configuration
3. Review payment logs

## 📚 Documentation

- **[README_PRODUCTION.md](README_PRODUCTION.md)** - Production deployment guide
- **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** - Pre-deployment checklist
- **[PRODUCTION_READY.md](PRODUCTION_READY.md)** - Production status

## 🔄 Updates

```bash
# 1. Backup current setup
python backup_restore.py backup

# 2. Pull latest code
git pull

# 3. Update dependencies
pip install -r requirements.txt --upgrade

# 4. Verify setup
python production_setup.py

# 5. Restart bot
python telegram_bot.py
```

## 📝 Project Structure

```
smg-forcer-bot/
├── telegram_bot.py          # Main bot file
├── database.py             # Database management
├── HacxGPT.py              # AI integration
├── oxapay.py               # Payment integration
├── setup.py                # Easy setup script
├── production_setup.py      # Setup verification
├── backup_restore.py        # Backup/restore utility
├── add_admin.py            # Add admin user
├── sync_admins.py           # Sync admin list
├── check_subscription.py    # Check user subscriptions
├── requirements.txt         # Python dependencies
├── .env.example            # Environment template
├── .gitignore              # Git ignore rules
├── README.md               # This file
└── backups/                # Backup storage
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API wrapper
- [DeepSeek](https://www.deepseek.com/) - AI API provider
- [OxaPay](https://oxapay.com/) - Payment gateway

## 📞 Support

For issues and questions:
1. Check the documentation
2. Review troubleshooting section
3. Check logs for errors
4. Open an issue on GitHub
5. Contact support directly on Telegram: [@Lesstalk420](https://t.me/Lesstalk420)

---

**Made with ❤️ for the SMG-Forcer community**
