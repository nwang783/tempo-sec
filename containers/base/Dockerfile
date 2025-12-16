FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base system tools
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    vim \
    netcat-openbsd \
    dnsutils \
    iputils-ping \
    net-tools \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security tools
RUN apt-get update && apt-get install -y \
    nmap \
    nikto \
    sqlmap \
    gobuster \
    dirb \
    hydra \
    whatweb \
    && rm -rf /var/lib/apt/lists/*

# Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Node.js (for some tools)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Playwright for browser automation
RUN pip3 install playwright && playwright install chromium --with-deps

# Additional Python security tools
RUN pip3 install \
    httpx \
    beautifulsoup4 \
    lxml \
    pyyaml \
    requests

# Nuclei (popular vulnerability scanner)
RUN curl -sSfL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_$(uname -s)_$(uname -m).zip -o nuclei.zip \
    && unzip nuclei.zip -d /usr/local/bin \
    && rm nuclei.zip \
    && nuclei -update-templates || true

# Working directory
WORKDIR /workspace

# Non-root user for safety
RUN useradd -m -s /bin/bash agent
RUN chown -R agent:agent /workspace

# Output directory
RUN mkdir -p /output && chown -R agent:agent /output

USER agent

# Default command
CMD ["tail", "-f", "/dev/null"]
