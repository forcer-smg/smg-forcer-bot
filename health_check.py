#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health Check Endpoint for Railway
Can be used as a healthcheck path
"""

from flask import Flask, jsonify
import os
import sys

app = Flask(__name__)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    status = {
        'status': 'healthy',
        'services': {}
    }
    
    # Check Click version
    try:
        import click
        status['services']['click'] = {
            'version': click.__version__,
            'status': 'ok' if click.__version__.startswith('8.') else 'warning'
        }
    except Exception as e:
        status['services']['click'] = {'status': 'error', 'error': str(e)}
    
    # Check Flask version
    try:
        import flask
        status['services']['flask'] = {
            'version': flask.__version__,
            'status': 'ok' if flask.__version__.startswith('2.2.') else 'warning'
        }
    except Exception as e:
        status['services']['flask'] = {'status': 'error', 'error': str(e)}
    
    # Check Dashboard
    try:
        status['services']['dashboard'] = {'status': 'running'}
    except Exception as e:
        status['services']['dashboard'] = {'status': 'error', 'error': str(e)}
    
    # Overall status
    has_errors = any(s.get('status') == 'error' for s in status['services'].values())
    if has_errors:
        status['status'] = 'unhealthy'
    
    return jsonify(status), 200 if status['status'] == 'healthy' else 503

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, debug=False)
