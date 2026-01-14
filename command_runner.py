#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Command Runner - Execute shell commands via API
Secure command execution for Railway shell access
"""

from flask import Flask, request, jsonify
import subprocess
import os
import logging
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security: Only allow specific commands
ALLOWED_COMMANDS = [
    'which', 'ls', 'pwd', 'echo', 'cat', 'head', 'tail',
    'python3', 'pip3', 'pip', 'go', 'apt-get',
    'bash', 'sh',
    'nmap', 'nuclei', 'nikto', 'sqlmap', 'masscan', 'dirb',
    'subfinder', 'amass', 'ffuf', 'gobuster', 'theHarvester', 'arjun',
    'verify_tools.py', 'quick_install_tools.sh', 'install_custom_tool.sh',
    'post_deploy_setup.sh'
]

# Password protection
COMMAND_RUNNER_PASSWORD = os.getenv('COMMAND_RUNNER_PASSWORD', 'admin123')

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        password = request.headers.get('X-Command-Password') or request.args.get('password')
        if password != COMMAND_RUNNER_PASSWORD:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/run-command', methods=['POST'])
@require_auth
def run_command():
    """Execute a shell command"""
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'error': 'No command provided'}), 400
        
        # Security check - only allow safe commands
        command_parts = command.split()
        base_command = command_parts[0] if command_parts else ''
        
        # Allow if it's a script file or starts with allowed command
        is_allowed = (
            any(cmd in command for cmd in ALLOWED_COMMANDS) or
            command.endswith('.sh') or
            command.endswith('.py') or
            command.startswith('python3 ') or
            command.startswith('bash ') or
            command.startswith('pip3 ') or
            command.startswith('go install')
        )
        
        if not is_allowed:
            return jsonify({
                'error': 'Command not allowed',
                'allowed': ALLOWED_COMMANDS[:10]  # Show first 10
            }), 403
        
        logger.info(f"Executing command: {command}")
        
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
            'stderr': result.stderr,
            'command': command,
            'timeout_used': timeout
        })
        
    except subprocess.TimeoutExpired:
        timeout_min = timeout / 60 if 'timeout' in locals() else 5
        return jsonify({
            'error': f'Command timed out after {timeout_min:.1f} minutes',
            'timeout_used': timeout,
            'suggestion': 'For comprehensive scans, try a more targeted approach or increase timeout via SCAN_TIMEOUT environment variable'
        }), 408
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-tools', methods=['GET'])
@require_auth
def check_tools():
    """Check installed tools"""
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

@app.route('/api/install-tool', methods=['POST'])
@require_auth
def install_tool():
    """Install a tool using install_custom_tool.sh"""
    try:
        data = request.get_json()
        tool_name = data.get('tool_name', '').strip()
        install_cmd = data.get('install_cmd', '').strip()
        
        if not tool_name or not install_cmd:
            return jsonify({'error': 'tool_name and install_cmd required'}), 400
        
        # Use install_custom_tool.sh
        command = f'bash install_custom_tool.sh "{tool_name}" "{install_cmd}"'
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd='/app'
        )
        
        return jsonify({
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'exit_code': result.returncode
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, debug=False)
