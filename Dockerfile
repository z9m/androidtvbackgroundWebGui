FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (SSL certificates for requests)
RUN apt-get update && apt-get install -y ca-certificates curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create defaults directory and backup assets for volume initialization
RUN mkdir -p /defaults && \
    cp -r overlays /defaults/ && \
    cp -r textures /defaults/ && \
    cp -r fonts /defaults/

# Setup entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# Expose the port
EXPOSE 5000

# Run the application
CMD ["python", "gui_editor.py"]