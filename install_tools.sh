#!/bin/bash
# Runtime tool installation script for Railway
# This script installs security tools if they're not available

set -e

echo "🔧 Checking and installing security tools..."

# Update package list
apt-get update || true

# Install apt-based tools
TOOLS_TO_INSTALL=(
    "nmap"
    "nikto"
    "masscan"
    "dirb"
)

for tool in "${TOOLS_TO_INSTALL[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        echo "Installing $tool..."
        apt-get install -y "$tool" || echo "Failed to install $tool"
    else
        echo "✅ $tool already installed"
    fi
done

# Install Go if not available
if ! command -v go &> /dev/null; then
    echo "Installing Go..."
    apt-get install -y golang-go || echo "Failed to install Go"
fi

# Install Go-based tools
if command -v go &> /dev/null; then
    export PATH="${PATH}:${HOME}/go/bin"
    
    GO_TOOLS=(
        "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
        "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
        "github.com/owasp-amass/amass/v4/...@master"
        "github.com/ffuf/ffuf/v2@latest"
        "github.com/OJ/gobuster/v3@latest"
    )
    
    for tool in "${GO_TOOLS[@]}"; do
        tool_name=$(echo "$tool" | awk -F'/' '{print $NF}' | awk -F'@' '{print $1}')
        if ! command -v "$tool_name" &> /dev/null; then
            echo "Installing $tool_name..."
            go install -v "$tool" || echo "Failed to install $tool_name"
        else
            echo "✅ $tool_name already installed"
        fi
    done
else
    echo "⚠️ Go not available, skipping Go-based tools"
fi

# Install Python-based tools
# Note: zapcli is excluded as it pins click==4.0 which conflicts with Flask
PYTHON_TOOLS=(
    "sqlmap"
    "theHarvester"
    "arjun"
    "wpscan"
)

for tool in "${PYTHON_TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null && ! python3 -m "$tool" --help &> /dev/null; then
        echo "Installing $tool via pip..."
        pip3 install "$tool" || echo "Failed to install $tool"
    else
        echo "✅ $tool available"
    fi
done

# Reinstall Click 8.0.1 to ensure compatibility with Flask 2.2.5
echo "🔧 Ensuring Click 8.0.1 is installed (required for Flask 2.2.5)..."
pip3 install --no-cache-dir --force-reinstall click==8.0.1 || echo "Warning: Could not reinstall Click 8.0.1"

echo "✅ Tool installation check complete"
