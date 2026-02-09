FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# We need python tools, nodejs, and native libraries for canvas rendering (Cairo, Pango, etc.)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    dos2unix \
    git \
    build-essential \
    python3-dev \
    # Node.js and npm for the renderer
    nodejs \
    npm \
    # Native dependencies for node-canvas (used by fabric.js in node)
    libcairo2-dev \
    libpango1.0-dev \
    libjpeg-dev \
    libgif-dev \
    librsvg2-dev \
    && rm -rf /var/lib/apt/lists/*
    
# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install Node.js dependencies
# This ensures that packages like fabric and canvas are compiled for Linux
RUN npm install

# Create defaults directory and backup assets for volume initialization
RUN mkdir -p /defaults && \
    if [ -d "overlays" ]; then cp -r overlays /defaults/; fi && \
    if [ -d "textures" ]; then cp -r textures /defaults/; fi && \
    if [ -d "fonts" ]; then cp -r fonts /defaults/; fi && \
    if [ -d "custom_icons" ]; then cp -r custom_icons /defaults/; fi

# Setup entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN dos2unix /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# Expose the port
EXPOSE 5000

# Run the application
CMD ["python", "gui_editor.py"]