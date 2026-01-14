# Use Python 3.11 slim as base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and security tools
RUN apt-get update && apt-get install -y \
    # Build tools
    build-essential \
    curl \
    wget \
    git \
    # Security tools (only those available in Debian repos)
    nmap \
    masscan \
    dirb \
    # Network tools
    netcat-openbsd \
    # For Go tools
    golang-go \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install nikto manually (not in Debian repos)
RUN git clone https://github.com/sullo/nikto.git /tmp/nikto && \
    cp -r /tmp/nikto/program/* /usr/local/bin/ && \
    chmod +x /usr/local/bin/nikto.pl && \
    ln -s /usr/local/bin/nikto.pl /usr/local/bin/nikto && \
    rm -rf /tmp/nikto

# Install Go-based tools (with error handling)
RUN mkdir -p /root/go/bin && \
    (go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest || echo "nuclei install failed") && \
    (go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest || echo "subfinder install failed") && \
    (go install -v github.com/owasp-amass/amass/v4/...@master || echo "amass install failed") && \
    (go install github.com/ffuf/ffuf/v2@latest || echo "ffuf install failed") && \
    (go install github.com/OJ/gobuster/v3@latest || echo "gobuster install failed") || true

# Add Go bin to PATH
ENV PATH="${PATH}:/root/go/bin"

# Install Python dependencies
# Use Flask 2.2.5 which doesn't require ParameterSource (compatible with Click 8.0+)
# Install Click and Flask FIRST, then other requirements, then verify
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip uninstall -y click flask || true && \
    pip install --no-cache-dir click==8.0.1 flask==2.2.5 && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --force-reinstall click==8.0.1 flask==2.2.5 && \
    pip check && \
    python -c "import click; import flask; print(f'Click: {click.__version__}, Flask: {flask.__version__}')"

# Install additional Python security tools
# Note: zapcli pins click==4.0 which conflicts with Flask, so we skip it
# Install others without dependencies first, then install our Click version
RUN pip install --no-cache-dir \
    sqlmap \
    theHarvester \
    arjun \
    wpscan || echo "Some Python tools failed to install"
# Reinstall Click 8.0.1 after other tools to ensure it's the active version
RUN pip install --no-cache-dir --force-reinstall click==8.0.1

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "start_services.py"]
