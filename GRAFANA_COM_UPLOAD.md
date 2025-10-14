# Grafana.com Upload Instructions

This document contains all the information needed to upload the SSH Honeypot Dashboard to Grafana.com.

## Dashboard File

**Use this file for Grafana.com upload:**
- `honeypot-for-grafana-com.json`

This version includes:
- `__inputs` section for datasource mapping
- `__requires` section for dependencies
- `${DS_PROMETHEUS}` datasource templating
- `version: 1` and `id: null` for proper import handling

## Dashboard Information

### Basic Details

**Dashboard Name:**
```
SSH Honeypot - Attack Map with Hall of Fame
```

**Dashboard Description (Short):**
```
Comprehensive SSH honeypot monitoring dashboard with persistent Hall of Fame system for tracking longest trap sessions using Endlessh.
```

**Dashboard Description (Full):**
```
A comprehensive Grafana dashboard for monitoring SSH honeypot attacks using Endlessh, featuring a persistent "Hall of Fame" system that tracks the Top 100 longest trap sessions of all time.

Features:
- 🏆 Hall of Fame System - Persistent Top 100 all-time longest trap sessions
- 🗺️ Attack Map - Geographic visualization of attack origins
- 📊 Real-time Metrics - Active connections, attack rate, trap duration statistics
- 🎯 Smart Deduplication - Only the longest session per IP address
- 💾 Persistent Storage - Hall of Fame survives container restarts
- 🌍 GeoIP Integration - Automatic location lookup for attacker IPs
- ⚡ Performance Optimized - 6-hour log window with persistent historical data

This dashboard monitors an Endlessh SSH honeypot - a tarpit that traps SSH clients by slowly sending an endless SSH banner. The longer an attacker stays connected, the higher their "score"!

Dashboard Panels:
1. Attack Map - World map showing attack origins sized by connection count
2. Statistics - Total attacks, unique IPs, attacks per minute, active connections
3. Max/Avg Trap Duration - How long attackers stay trapped
4. Trap Sessions - Live & Hall of Fame - Detailed table showing currently trapped connections and Top 100 longest sessions

The dashboard requires a custom Prometheus exporter (included in GitHub repository) that parses Endlessh logs, provides GeoIP enrichment, and maintains the persistent Hall of Fame system.
```

### Categories/Tags

**Primary Category:**
- Security

**Additional Tags:**
```
honeypot, security, ssh, endlessh, monitoring, attack-detection, geoip, threat-intelligence
```

### Requirements

**Grafana Version:**
- Minimum: 9.0.0

**Data Sources:**
- Prometheus (required)

**Plugins:**
- Core panels: Geomap, Stat, Pie chart, Table, Time series
- No additional plugins required

### Installation Notes

```
Prerequisites:
- Endlessh SSH honeypot running as systemd service
- Prometheus configured to scrape the custom exporter
- Custom Prometheus exporter (endlessh-exporter-geoip.py) - available in GitHub repository

Setup Instructions:
1. Install and configure Endlessh SSH honeypot
2. Deploy the custom Prometheus exporter from the GitHub repository
3. Configure Prometheus to scrape the exporter at port 9314
4. Import this dashboard and map your Prometheus datasource
5. Detailed setup instructions available in the GitHub repository

GitHub Repository: https://github.com/Peuqui/Grafana-Dashboards/tree/main
Exporter Code: https://github.com/Peuqui/Grafana-Dashboards/blob/main/endlessh-exporter-geoip.py
Full Documentation: https://github.com/Peuqui/Grafana-Dashboards/blob/main/README.md
```

### Links

**GitHub Repository:**
```
https://github.com/Peuqui/Grafana-Dashboards
```

**Documentation:**
```
https://github.com/Peuqui/Grafana-Dashboards/blob/main/README.md
```

**Exporter Source:**
```
https://github.com/Peuqui/Grafana-Dashboards/blob/main/endlessh-exporter-geoip.py
```

### Screenshots

Upload these two screenshots:
1. `screenshots/dashboard-overview-map.png` - Shows the attack map and statistics
2. `screenshots/dashboard-overview-hall-of-fame.png` - Shows the Hall of Fame table

**Screenshot Descriptions:**

Screenshot 1:
```
Attack map showing geographic distribution of SSH honeypot attacks with real-time statistics including total attacks, unique IPs, and active trapped connections.
```

Screenshot 2:
```
Hall of Fame table displaying currently trapped sessions and top all-time longest trap sessions with IP addresses, locations, status, and trap durations.
```

## Upload Steps

1. **Login to Grafana.com**
   - Go to https://grafana.com/
   - Sign in to your account

2. **Navigate to Dashboard Upload**
   - Go to your profile/dashboard section
   - Click "Upload Dashboard" or "Share Dashboard"

3. **Upload Dashboard File**
   - Select `honeypot-for-grafana-com.json`
   - Fill in the dashboard information from above

4. **Add Screenshots**
   - Upload both screenshots
   - Add the descriptions

5. **Set Categories and Tags**
   - Primary category: Security
   - Tags: honeypot, security, ssh, endlessh, monitoring, attack-detection, geoip, threat-intelligence

6. **Add Installation Notes**
   - Copy the installation notes from above
   - Include links to GitHub repository

7. **Review and Publish**
   - Review all information
   - Publish the dashboard

## Expected Metrics

Users should see these metrics when the exporter is properly configured:

```promql
endlessh_connection_info
endlessh_total_connections
endlessh_active_connections
endlessh_max_trap_duration_seconds
endlessh_avg_trap_duration_seconds
endlessh_unique_ips
endlessh_connections_per_ip
endlessh_connections_per_country
```

## Support Information

If users have issues:
1. Check the GitHub repository README for detailed setup instructions
2. Verify the custom exporter is running and exposing metrics on port 9314
3. Ensure Prometheus is scraping the exporter
4. Check exporter logs for GeoIP or parsing errors
5. Open an issue on GitHub for additional support

## License

MIT License - Feel free to use and modify!

---

**Note**: This dashboard requires a custom Prometheus exporter which is not included in the JSON file. Users must deploy the exporter separately following the instructions in the GitHub repository.
