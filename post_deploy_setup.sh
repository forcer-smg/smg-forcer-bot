#!/bin/bash
# Post-Deployment Setup Script
# Runs automatically after Railway deployment
# Can also be run manually via shell

set -e

echo "🚀 Post-Deployment Setup Starting..."
echo "===================================="
echo ""

# Check if we're on Railway
if [ -z "$RAILWAY_ENVIRONMENT" ] && [ -z "$RAILWAY_PUBLIC_DOMAIN" ]; then
    echo "⚠️  Not running on Railway, skipping some setup"
else
    echo "✅ Railway environment detected"
fi

# Verify all tools are installed
echo ""
echo "📦 Verifying tool installation..."
python3 verify_tools.py || echo "⚠️  Tool verification script not available"

# Check Click/Flask versions
echo ""
echo "🔧 Verifying Click/Flask versions..."
python3 -c "
import click
import flask
print(f'Click: {click.__version__}')
print(f'Flask: {flask.__version__}')
if not click.__version__.startswith('8.'):
    print('⚠️  Click version incorrect!')
if not flask.__version__.startswith('2.2.'):
    print('⚠️  Flask version incorrect!')
"

# Install any missing Python dependencies
echo ""
echo "📦 Checking Python dependencies..."
pip3 install --upgrade pip || true
pip3 install --no-cache-dir --force-reinstall click==8.0.1 flask==2.2.5 || true

# Ensure Go tools are in PATH
echo ""
echo "🔧 Ensuring Go tools are in PATH..."
export PATH="${PATH}:${HOME}/go/bin"
echo "PATH updated: $PATH"

# Create necessary directories
echo ""
echo "📁 Creating necessary directories..."
mkdir -p /app/execution_logs || true
mkdir -p /app/vector_memory || true
mkdir -p /app/workspaces || true

echo ""
echo "✅ Post-deployment setup complete!"
echo ""
echo "📋 Quick Commands:"
echo "  python3 verify_tools.py  - Check installed tools"
echo "  bash quick_install_tools.sh  - Install additional tools"
echo "  bash install_custom_tool.sh tool-name \"install-cmd\"  - Install custom tool"
