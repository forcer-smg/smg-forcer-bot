# -*- coding: utf-8 -*-
"""
SMG-Forcer Admin Dashboard
Web interface for monitoring users, subscriptions, and payments
"""

from flask import Flask, render_template_string, jsonify, request
from database import Database
from oxapay import OxaPay
import os
import json
import logging
from dotenv import load_dotenv
from HacxGPT import Config
from telegram_bot_module import telegram_bot, settings_sync

load_dotenv(dotenv_path=Config.ENV_FILE)

app = Flask(__name__)
db = Database()
logger = logging.getLogger(__name__)

# Dashboard password (change this!)
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SMG-Forcer Admin Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        .content { padding: 30px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .stat-card h3 { font-size: 0.9em; opacity: 0.9; margin-bottom: 10px; }
        .stat-card .value { font-size: 2.5em; font-weight: bold; }
        .section {
            margin-bottom: 40px;
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #667eea;
            color: white;
            font-weight: 600;
        }
        tr:hover { background: #f5f5f5; }
        .badge {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .badge-success { background: #28a745; color: white; }
        .badge-warning { background: #ffc107; color: black; }
        .badge-danger { background: #dc3545; color: white; }
        .badge-info { background: #17a2b8; color: white; }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover { background: #5568d3; }
        .search-box {
            width: 100%;
            padding: 10px;
            margin-bottom: 20px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 1em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 SMG-Forcer Admin Dashboard</h1>
            <p>Monitor users, subscriptions, and payments</p>
        </div>
        <div class="content">
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>Total Users</h3>
                    <div class="value" id="total-users">-</div>
                </div>
                <div class="stat-card">
                    <h3>Active Subscriptions</h3>
                    <div class="value" id="active-subs">-</div>
                </div>
                <div class="stat-card">
                    <h3>Total Revenue</h3>
                    <div class="value" id="revenue">$-</div>
                </div>
                <div class="stat-card">
                    <h3>New Users Today</h3>
                    <div class="value" id="today-users">-</div>
                </div>
            </div>

            <div class="section">
                <h2>📊 Recent Users</h2>
                <input type="text" class="search-box" id="user-search" placeholder="Search users..." onkeyup="filterTable('user-table', this.value)">
                <div style="overflow-x: auto;">
                    <table id="user-table">
                        <thead>
                            <tr>
                                <th>User ID</th>
                                <th>Username</th>
                                <th>Name</th>
                                <th>Status</th>
                                <th>Referrals</th>
                                <th>Joined</th>
                            </tr>
                        </thead>
                        <tbody id="users-tbody"></tbody>
                    </table>
                </div>
            </div>

            <div class="section">
                <h2>💳 Recent Payments</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Payment ID</th>
                                <th>User</th>
                                <th>Plan</th>
                                <th>Amount</th>
                                <th>Status</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody id="payments-tbody"></tbody>
                    </table>
                </div>
            </div>

            <div class="section">
                <h2>⭐ Active Subscriptions</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>User ID</th>
                                <th>Plan</th>
                                <th>Used/Total</th>
                                <th>Status</th>
                                <th>Expires</th>
                            </tr>
                        </thead>
                        <tbody id="subs-tbody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        function filterTable(tableId, searchText) {
            const table = document.getElementById(tableId);
            const rows = table.getElementsByTagName('tr');
            
            for (let i = 1; i < rows.length; i++) {
                const row = rows[i];
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchText.toLowerCase()) ? '' : 'none';
            }
        }

        function loadDashboard() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('total-users').textContent = data.total_users;
                    document.getElementById('active-subs').textContent = data.active_subscriptions;
                    document.getElementById('revenue').textContent = '$' + data.total_revenue.toFixed(2);
                    document.getElementById('today-users').textContent = data.today_new_users;
                });

            fetch('/api/users')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('users-tbody');
                    tbody.innerHTML = data.map(user => `
                        <tr>
                            <td>${user.user_id}</td>
                            <td>@${user.username || 'N/A'}</td>
                            <td>${user.first_name || 'N/A'}</td>
                            <td><span class="badge ${user.current_status === 'active' ? 'badge-success' : 'badge-info'}">${user.current_status || 'free'}</span></td>
                            <td>${user.total_referrals || 0}</td>
                            <td>${new Date(user.created_at).toLocaleDateString()}</td>
                        </tr>
                    `).join('');
                });

            fetch('/api/payments')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('payments-tbody');
                    tbody.innerHTML = data.map(payment => `
                        <tr>
                            <td>${payment.payment_id}</td>
                            <td>@${payment.username || payment.user_id}</td>
                            <td>${payment.plan_type}</td>
                            <td>$${payment.amount}</td>
                            <td><span class="badge ${payment.status === 'completed' ? 'badge-success' : 'badge-warning'}">${payment.status}</span></td>
                            <td>${new Date(payment.created_at).toLocaleString()}</td>
                        </tr>
                    `).join('');
                });

            fetch('/api/subscriptions')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('subs-tbody');
                    tbody.innerHTML = data.map(sub => `
                        <tr>
                            <td>${sub.user_id}</td>
                            <td>${sub.plan_type}</td>
                            <td>${sub.requests_used}/${sub.requests_limit}</td>
                            <td><span class="badge ${sub.status === 'active' ? 'badge-success' : 'badge-danger'}">${sub.status}</span></td>
                            <td>${new Date(sub.end_date).toLocaleDateString()}</td>
                        </tr>
                    `).join('');
                });
        }

        // Load on page load
        loadDashboard();
        // Auto-refresh every 30 seconds
        setInterval(loadDashboard, 30000);
    </script>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Main dashboard page"""
    password = request.args.get('password', '')
    if password != DASHBOARD_PASSWORD:
        return """
        <html>
        <head><title>SMG-Forcer Dashboard - Login</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>SMG-Forcer Admin Dashboard</h1>
            <p>Enter password to access:</p>
            <form method="get">
                <input type="password" name="password" placeholder="Password" style="padding: 10px; font-size: 16px;">
                <button type="submit" style="padding: 10px 20px; font-size: 16px;">Login</button>
            </form>
        </body>
        </html>
        """
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/stats')
def api_stats():
    """Get dashboard statistics"""
    stats = db.get_dashboard_stats()
    return jsonify(stats)


@app.route('/api/users')
def api_users():
    """Get all users"""
    users = db.get_all_users(limit=50)
    return jsonify(users)


@app.route('/api/payments')
def api_payments():
    """Get all payments"""
    payments = db.get_all_payments(limit=50)
    return jsonify(payments)


@app.route('/api/subscriptions')
def api_subscriptions():
    """Get all subscriptions"""
    subs = db.get_all_subscriptions(limit=50)
    return jsonify(subs)


@app.route('/webhook/oxapay', methods=['POST'])
def oxapay_webhook():
    """Handle OxaPay payment webhook - Enhanced with better logging and error handling"""
    try:
        data = request.json or {}
        
        # Log webhook data for debugging
        logger.info(f"📥 OxaPay webhook received: {json.dumps(data, indent=2)}")
        
        # Try different possible field names (OxaPay may send different formats)
        invoice_id = (
            data.get('invoiceId') or 
            data.get('invoice_id') or 
            data.get('invoiceID') or
            data.get('id') or
            data.get('invoice')
        )
        
        track_id = (
            data.get('trackId') or 
            data.get('track_id') or
            data.get('trackID') or
            data.get('orderId') or
            data.get('order_id') or
            data.get('track_id')
        )
        
        status = (
            data.get('status') or 
            data.get('Status') or
            data.get('payment_status') or
            data.get('paymentStatus')
        )
        
        logger.info(f"📋 Extracted: invoice_id={invoice_id}, track_id={track_id}, status={status}")
        
        if not invoice_id and not track_id:
            logger.error("❌ No invoice_id or track_id found in webhook data")
            return jsonify({
                'success': False,
                'error': 'Missing invoice_id or track_id',
                'received_data': data
            }), 400
        
        if status != 'paid':
            logger.warning(f"⚠️ Payment status is not 'paid': {status}")
            return jsonify({
                'success': False,
                'error': f'Payment status is {status}, not paid',
                'status': status
            }), 400
        
        # Verify payment with OxaPay API before confirming (optional but recommended)
        try:
            from oxapay import OxaPay
            oxapay = OxaPay()
            if invoice_id:
                verification = oxapay.verify_payment(invoice_id)
                if verification and verification.get('paid'):
                    logger.info(f"✅ Payment verified with OxaPay API: {invoice_id}")
                else:
                    logger.warning(f"⚠️ OxaPay API verification failed or not paid: {verification}")
                    # Continue anyway - webhook should be trusted
        except Exception as e:
            logger.warning(f"⚠️ Could not verify with OxaPay API: {e}, continuing anyway...")
        
        # Complete payment in database
        payment_id_to_use = invoice_id or track_id
        result = db.complete_payment(payment_id_to_use)
        
        if result:
            logger.info(f"✅ Payment completed successfully: {payment_id_to_use}")
            
            # If referrer got bonus, it will be notified on next bot interaction
            # The referrer_id is returned if bonus was given
            if isinstance(result, int):
                # result is referrer_id - bonus was given
                logger.info(f"🎁 Referral bonus given to user {result}")
                # Notification will happen when referrer uses bot next
                pass
            
            return jsonify({
                'success': True,
                'invoice_id': invoice_id,
                'track_id': track_id,
                'payment_id': payment_id_to_use
            }), 200
        else:
            logger.error(f"❌ Payment completion failed: {payment_id_to_use}")
            return jsonify({
                'success': False,
                'error': 'Payment not found or already completed',
                'invoice_id': invoice_id,
                'track_id': track_id
            }), 404
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500


# ============================================================
# Dashboard Telegram Notifications (NEW)
# ============================================================

@app.route('/api/telegram/dashboard/notify', methods=['POST'])
def telegram_dashboard_notify():
    """Send dashboard event notification via Telegram"""
    data = request.json or {}
    event_type = data.get('event_type', 'info')
    title = data.get('title', 'Dashboard Event')
    details = data.get('details', '')
    event_data = data.get('data', {})
    
    if not telegram_bot.enabled:
        return jsonify({'error': 'Telegram bot not configured'}), 400
    
    success = telegram_bot.notify_dashboard_event(event_type, title, details, event_data)
    return jsonify({'success': success})


@app.route('/api/telegram/dashboard/terminal', methods=['POST'])
def telegram_dashboard_terminal():
    """Send terminal command notification via Telegram"""
    data = request.json or {}
    command = data.get('command', '')
    output = data.get('output', '')
    success = data.get('success', True)
    
    if not telegram_bot.enabled:
        return jsonify({'error': 'Telegram bot not configured'}), 400
    
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    
    success_sent = telegram_bot.notify_terminal_command(command, output, success)
    return jsonify({'success': success_sent})


@app.route('/api/telegram/dashboard/toolkit', methods=['POST'])
def telegram_dashboard_toolkit():
    """Send toolkit execution notification via Telegram"""
    data = request.json or {}
    tool_name = data.get('tool_name', '')
    result = data.get('result', '')
    success = data.get('success', True)
    
    if not telegram_bot.enabled:
        return jsonify({'error': 'Telegram bot not configured'}), 400
    
    if not tool_name:
        return jsonify({'error': 'Tool name is required'}), 400
    
    success_sent = telegram_bot.notify_toolkit_execution(tool_name, result, success)
    return jsonify({'success': success_sent})


@app.route('/api/telegram/dashboard/status', methods=['GET'])
def telegram_dashboard_status():
    """Get dashboard integration status"""
    return jsonify({
        'telegram_enabled': telegram_bot.enabled,
        'settings_sync_enabled': settings_sync.enabled,
        'features': {
            'terminal_notifications': telegram_bot.enabled,
            'toolkit_notifications': telegram_bot.enabled,
            'extension_notifications': telegram_bot.enabled,
            'git_notifications': telegram_bot.enabled,
            'dashboard_fix_notifications': telegram_bot.enabled,
            'settings_sync': settings_sync.enabled
        }
    })


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Railway provides PORT environment variable
    port = int(os.getenv('PORT', os.getenv('DASHBOARD_PORT', 5000)))
    
    # Get Railway public domain if available
    railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    railway_static = os.getenv('RAILWAY_STATIC_URL')
    
    if railway_static:
        dashboard_url = railway_static
    elif railway_domain:
        dashboard_url = f"https://{railway_domain}"
    else:
        dashboard_url = f"http://localhost:{port}"
    
    print(f"Dashboard running on port {port}")
    print(f"Dashboard URL: {dashboard_url}")
    if not railway_domain and not railway_static:
        print(f"Local access: http://localhost:{port}?password={DASHBOARD_PASSWORD}")

# Add health check endpoint for Railway monitoring
@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    try:
        import click
        import flask
        return jsonify({
            'status': 'healthy',
            'click_version': click.__version__,
            'flask_version': flask.__version__,
            'dashboard': 'running'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

# Command Runner Endpoint (for Railway shell access)
@app.route('/api/run-command', methods=['POST'])
def run_command():
    """Execute shell commands via API (secure)"""
    import subprocess
    import os
    
    # Get password from request
    password = request.headers.get('X-Command-Password') or request.args.get('password')
    command_runner_password = os.getenv('COMMAND_RUNNER_PASSWORD', DASHBOARD_PASSWORD)
    
    if password != command_runner_password:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'error': 'No command provided'}), 400
        
        # Security: Only allow safe commands
        allowed_prefixes = ['python3', 'bash', 'pip3', 'pip', 'go', 'which', 'ls', 'pwd', 'cat']
        allowed_scripts = ['.sh', '.py', 'verify_tools', 'install_custom_tool', 'quick_install']
        
        is_allowed = (
            any(command.startswith(prefix) for prefix in allowed_prefixes) or
            any(script in command for script in allowed_scripts) or
            command in ['nmap --version', 'nuclei -version', 'sqlmap --version']
        )
        
        if not is_allowed:
            return jsonify({'error': 'Command not allowed for security'}), 403
        
        # Get adaptive timeout based on command type
        try:
            from timeout_config import get_timeout_for_command
            timeout = get_timeout_for_command(command)
            logger.info(f"Using adaptive timeout: {timeout}s ({timeout/60:.1f} min)")
        except ImportError:
            timeout = 300  # Default fallback
            logger.warning("timeout_config not available, using default 300s timeout")
        
        # Execute command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd='/app'
        )
        
        return jsonify({
            'success': result.returncode == 0,
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-tools', methods=['GET'])
def api_check_tools():
    """Check installed tools via API"""
    import subprocess
    
    password = request.args.get('password')
    if password != DASHBOARD_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        result = subprocess.run(
            ['python3', 'verify_tools.py'],
            capture_output=True,
            text=True,
            timeout=60,
            cwd='/app'
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/shell')
def shell_interface():
    """Shell interface HTML page"""
    try:
        with open('shell_interface.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return """
        <html><body>
        <h1>Shell Interface</h1>
        <p>Shell interface file not found. Use API endpoints directly:</p>
        <ul>
        <li>POST /api/run-command?password=YOUR_PASSWORD</li>
        <li>GET /api/check-tools?password=YOUR_PASSWORD</li>
        </ul>
        </body></html>
        """
    
    app.run(host='0.0.0.0', port=port, debug=False)

