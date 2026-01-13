# Repository Structure

## ✅ Production Files Included

### Core Application Files (19 Python files)
1. `telegram_bot.py` - Main Telegram bot application
2. `HacxGPT.py` - AI brain with DeepSeek integration
3. `eden_ai_handler.py` - Eden AI integration for current information
4. `start_services.py` - Service starter for Railway (starts bot + dashboard)
5. `database.py` - SQLite database handler
6. `database_hybrid.py` - Hybrid database (SQLite/PostgreSQL auto-detect)
7. `oxapay.py` - Payment integration (OxaPay)
8. `dashboard.py` - Admin dashboard web interface
9. `dashboard_features.py` - Dashboard functionality
10. `telegram_bot_module.py` - Telegram bot module for dashboard
11. `telegram_commands.py` - Telegram command handlers
12. `multi_model_manager.py` - Multi-model AI manager
13. `background_processor.py` - Background task processor
14. `approval_manager.py` - Approval workflow manager
15. `supabase_integration.py` - Supabase database integration
16. `supabase_task_queue.py` - Supabase task queue
17. `supabase_conversation_context.py` - Conversation context manager
18. `monitor_and_fix.py` - Monitoring and auto-fix service
19. `setup.py` - Setup script

### Configuration Files
- `Procfile` - Railway process configuration
- `requirements.txt` - Python dependencies
- `railway.json` - Railway deployment configuration
- `.gitignore` - Git ignore rules

### Deployment Scripts
- `install.sh` - Installation script
- `post_deploy_setup.sh` - Post-deployment setup
- `install_tools.sh` - Tool installation script

### Documentation
- `README.md` - Project documentation
- `DEPLOYMENT_STATUS.md` - Deployment status and checklist
- `EDEN_AI_SETUP.md` - Eden AI setup instructions

## 📁 File Organization

### Tracked Files (27 total)
- **19 Python modules** - Core application code
- **3 Shell scripts** - Deployment and installation
- **3 Configuration files** - Procfile, requirements.txt, railway.json
- **2 Documentation files** - README.md, deployment docs

### Excluded Files (via .gitignore)
- Development scripts (*.bat, *.ps1, deploy scripts)
- Documentation files (except README.md and essential docs)
- Test files (test_*.py, *_test.py)
- Debug files (debug_*.py)
- Checkpoints and backups
- Temporary files
- Log files
- IDE files (.cursor/, .vscode/, .idea/)

## 🔍 Dependency Chain

### Main Entry Point
```
start_services.py
├── telegram_bot.py
│   ├── HacxGPT.py
│   │   └── eden_ai_handler.py
│   ├── database_hybrid.py / database.py
│   ├── oxapay.py
│   ├── multi_model_manager.py
│   ├── background_processor.py
│   ├── approval_manager.py
│   └── telegram_bot_module.py
│       └── telegram_commands.py
└── dashboard.py
    ├── database.py
    ├── oxapay.py
    ├── telegram_bot_module.py
    └── dashboard_features.py
```

### Supabase Integration
- `supabase_integration.py` - Main Supabase client
- `supabase_task_queue.py` - Task queue implementation
- `supabase_conversation_context.py` - Context management

### Monitoring
- `monitor_and_fix.py` - Auto-monitoring and fixes

## ✅ Verification Checklist

- [x] All core Python modules included
- [x] All dependencies for telegram_bot.py included
- [x] All dependencies for dashboard.py included
- [x] All dependencies for start_services.py included
- [x] Deployment scripts included (install.sh, post_deploy_setup.sh, install_tools.sh)
- [x] Configuration files included (Procfile, requirements.txt, railway.json)
- [x] Essential documentation included (README.md)
- [x] .gitignore properly configured
- [x] No critical files excluded

## 🚀 Railway Deployment Ready

All files necessary for Railway deployment are included:
- ✅ Procfile configured
- ✅ requirements.txt complete
- ✅ start_services.py starts both bot and dashboard
- ✅ All Python dependencies included
- ✅ Deployment scripts included
- ✅ Configuration files included

## 📝 Notes

- The repository is organized to include only production-ready code
- Development scripts and test files are excluded via .gitignore
- All critical dependencies are tracked in git
- The structure supports both SQLite (local) and PostgreSQL (Railway) databases
- Eden AI integration is complete and ready for use
