# Railway CLI Usage Guide

## ✅ Project Linked Successfully

Your project is now linked to Railway:
- **Project**: stunning-liberation
- **Environment**: production
- **Service**: smg-forcer-bot

## Common Railway CLI Commands

### View Project Status
```bash
railway status
```

### View Environment Variables
```bash
railway variables
```

### Set Environment Variable
```bash
railway variables set VARIABLE_NAME=value
```

### Run Commands in Railway Environment
```bash
# Run Python script
railway run python restore_supabase_database.py

# Run shell command
railway run bash

# Run specific command
railway run python -c "import os; print(os.getenv('DATABASE_URL'))"
```

### Deploy to Railway
```bash
# Deploy current code
railway up

# Deploy and watch logs
railway up --watch
```

### View Logs
```bash
# View recent logs
railway logs

# Follow logs in real-time
railway logs --follow
```

### Open Railway Shell
```bash
railway shell
```

### Restore Supabase Database
```bash
# Run the restore script
railway run python restore_supabase_database.py
```

## Next Steps

1. **Restore Supabase Database**:
   ```bash
   railway run python restore_supabase_database.py
   ```
   Type `yes` when prompted to restore the database schema.

2. **Verify Environment Variables**:
   ```bash
   railway variables
   ```
   Make sure `DATABASE_URL` and `EDEN_AI_API_KEY` are set.

3. **Check Deployment Status**:
   ```bash
   railway status
   railway logs
   ```

4. **Deploy Latest Code** (if needed):
   ```bash
   railway up
   ```

## Troubleshooting

### If Railway CLI is not installed:
```bash
# Windows (PowerShell)
iwr https://railway.com/install.sh | iex

# Or download from: https://railway.com/cli
```

### If project link fails:
```bash
railway login
railway link -p 3424e74d-fcad-4d55-9a72-d1c149b3cd8c
```

### View Railway Dashboard:
Visit: https://railway.app/dashboard
