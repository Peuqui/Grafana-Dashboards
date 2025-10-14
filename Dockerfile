FROM python:3.11-slim

# Install systemd for journalctl access
RUN apt-get update && apt-get install -y systemd && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the exporter script
COPY endlessh-exporter-geoip.py /app/

# Expose metrics port
EXPOSE 9314

# Run the exporter
CMD ["python3", "endlessh-exporter-geoip.py"]
