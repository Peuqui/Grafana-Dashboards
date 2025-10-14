#!/usr/bin/env python3
"""
Endlessh Prometheus Exporter with GeoIP
Parses journalctl logs from endlessh and exports metrics for Prometheus with geographic data
"""

import re
import subprocess
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict
from datetime import datetime, timezone

# Port for Prometheus scraping
EXPORTER_PORT = 9314

# Persistent storage for Hall of Fame
HALL_OF_FAME_FILE = '/data/hall_of_fame.json'

# Store metrics
individual_connections = {}  # conn_id -> {ip, started, duration, status, country, city}
hall_of_fame = {}  # Persistent storage for released connections (Top 100 by duration)
ip_locations = {}  # IP -> {country, lat, lon}
total_connections_counter = 0  # Counter: total connections since start (never reset)
seen_log_entries = set()  # Track which log entries we've already counted
connections_per_ip = defaultdict(int)  # IP -> count (for aggregated stats)
max_trap_duration = 0  # Max trap duration in seconds (from currently displayed connections)
avg_trap_duration = 0  # Average trap duration in seconds
active_connections = 0  # Currently active connections

def load_hall_of_fame():
    """Load Hall of Fame from JSON file if it exists"""
    global hall_of_fame

    if os.path.exists(HALL_OF_FAME_FILE):
        try:
            with open(HALL_OF_FAME_FILE, 'r') as f:
                data = json.load(f)
                # Convert datetime strings back to datetime objects
                for conn_id, conn in data.items():
                    if 'started' in conn and isinstance(conn['started'], str):
                        # Parse ISO format timestamp
                        conn['started'] = datetime.fromisoformat(conn['started'])
                hall_of_fame = data
                print(f"Loaded {len(hall_of_fame)} connections from Hall of Fame")
        except Exception as e:
            print(f"Error loading Hall of Fame: {e}")
            hall_of_fame = {}
    else:
        print("No existing Hall of Fame found, starting fresh")
        hall_of_fame = {}

def save_hall_of_fame():
    """Save Hall of Fame to JSON file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(HALL_OF_FAME_FILE), exist_ok=True)

        # Convert datetime objects to ISO strings for JSON serialization
        data_to_save = {}
        for conn_id, conn in hall_of_fame.items():
            conn_copy = conn.copy()
            if 'started' in conn_copy and isinstance(conn_copy['started'], datetime):
                conn_copy['started'] = conn_copy['started'].isoformat()
            data_to_save[conn_id] = conn_copy

        # Write to file
        with open(HALL_OF_FAME_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=2)

    except Exception as e:
        print(f"Error saving Hall of Fame: {e}")

def get_geoip_data(ip):
    """Get GeoIP data using geoiplookup or online API"""
    if ip in ip_locations:
        return ip_locations[ip]

    # Try using a simple HTTP API (ip-api.com allows 45 requests/minute for free)
    try:
        import urllib.request
        url = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,lat,lon,city"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                result = {
                    'country': data.get('country', 'Unknown'),
                    'country_code': data.get('countryCode', 'XX'),
                    'city': data.get('city', 'Unknown'),
                    'lat': data.get('lat', 0.0),
                    'lon': data.get('lon', 0.0)
                }
                ip_locations[ip] = result
                return result
    except Exception as e:
        pass

    # Fallback
    return {
        'country': 'Unknown',
        'country_code': 'XX',
        'city': 'Unknown',
        'lat': 0.0,
        'lon': 0.0
    }

def parse_endlessh_logs():
    """Parse endlessh logs from journalctl"""
    global individual_connections, hall_of_fame, active_connections, connections_per_ip
    global total_connections_counter, seen_log_entries
    global max_trap_duration, avg_trap_duration

    # Get logs from last 6 hours (to catch long-running traps)
    # Note: Hall of Fame persists released connections, so we don't lose history
    cmd_6h = ['journalctl', '-u', 'endlessh', '--since', '6 hours ago', '--no-pager']
    try:
        output_6h = subprocess.check_output(cmd_6h, text=True)
    except subprocess.CalledProcessError:
        return

    # Get logs from last 5 minutes (for new connections to add to counter)
    cmd_5min = ['journalctl', '-u', 'endlessh', '--since', '5 minutes ago', '--no-pager']
    try:
        output_5min = subprocess.check_output(cmd_5min, text=True)
    except subprocess.CalledProcessError:
        output_5min = ""

    # Reset current connections (will rebuild from logs + hall of fame)
    individual_connections.clear()
    connections_per_ip.clear()
    current_active = 0
    current_time = datetime.now(timezone.utc)

    # Parse patterns - use port as unique connection ID (port is unique, fd gets reused)
    accept_pattern = r'ACCEPT host=::ffff:(\d+\.\d+\.\d+\.\d+) port=(\d+).*?fd=(\d+).*?n=(\d+)/(\d+)'
    close_pattern = r'CLOSE host=::ffff:(\d+\.\d+\.\d+\.\d+) port=(\d+).*?fd=(\d+).*?time=([\d.]+)'
    # Parse ISO timestamp from endlessh: 2025-10-14T16:17:13.280Z
    timestamp_pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+Z'

    # Parse all events chronologically and build timeline
    # First, collect all CLOSE events to know which connections are closed
    closed_ports = set()
    for line in output_6h.split('\n'):
        close_match = re.search(close_pattern, line)
        if close_match:
            port = close_match.group(2)
            closed_ports.add(port)

    # Now parse ACCEPT events
    all_durations = []
    for line in output_6h.split('\n'):
        match = re.search(accept_pattern, line)
        if match:
            ip = match.group(1)
            port = match.group(2)
            fd = match.group(3)
            current_active = int(match.group(4))

            # Use ip:port as unique connection ID (port is unique per connection)
            conn_id = f"{ip}:{port}"

            # Parse timestamp from log (UTC timestamp from endlessh)
            ts_match = re.search(timestamp_pattern, line)
            if ts_match:
                # Parse ISO timestamp as UTC
                timestamp_str = ts_match.group(1)
                started_time = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
            else:
                started_time = datetime.now(timezone.utc)

            # Get GeoIP data (cached after first lookup)
            if ip not in ip_locations:
                get_geoip_data(ip)

            geo = ip_locations.get(ip, {})

            # Determine status: trapped if port not in closed_ports
            if port in closed_ports:
                status = 'released'
            else:
                status = 'trapped'

            # Store individual connection (will overwrite if same port appears multiple times)
            individual_connections[conn_id] = {
                'ip': ip,
                'port': port,
                'fd': fd,
                'country': geo.get('country', 'Unknown').replace('"', ''),
                'city': geo.get('city', 'Unknown').replace('"', ''),
                'country_code': geo.get('country_code', 'XX'),
                'started': started_time,
                'duration': 0,
                'status': status
            }

            connections_per_ip[ip] += 1

    # Second pass: Parse all CLOSE events to get durations
    for line in output_6h.split('\n'):
        close_match = re.search(close_pattern, line)
        if close_match:
            ip = close_match.group(1)
            port = close_match.group(2)
            fd = close_match.group(3)
            duration = float(close_match.group(4))

            # Use ip:port as unique connection ID
            conn_id = f"{ip}:{port}"

            # Update the connection with duration
            if conn_id in individual_connections:
                individual_connections[conn_id]['duration'] = duration
                # Move released connections to hall_of_fame
                hall_of_fame[conn_id] = individual_connections[conn_id].copy()
                all_durations.append(duration)

    # Separate trapped and released connections
    trapped_connections = {k: v for k, v in individual_connections.items() if v['status'] == 'trapped'}

    # For trapped connections, calculate current duration
    for conn_id, conn in trapped_connections.items():
        conn['duration'] = (datetime.now(timezone.utc) - conn['started']).total_seconds()

    # Deduplicate hall_of_fame: Keep only the longest duration per IP
    # Group by IP and keep only the connection with max duration
    ip_to_best_conn = {}
    for conn_id, conn in hall_of_fame.items():
        ip = conn['ip']
        if ip not in ip_to_best_conn or conn['duration'] > ip_to_best_conn[ip][1]['duration']:
            ip_to_best_conn[ip] = (conn_id, conn)

    # Rebuild hall_of_fame with deduplicated connections
    hall_of_fame = {conn_id: conn for conn_id, conn in ip_to_best_conn.values()}

    # Keep only Top 100 released connections in hall_of_fame (by duration)
    # Always trim to exactly 100 (or less if we have fewer)
    if len(hall_of_fame) > 100:
        # Sort by duration (descending) and keep top 100
        sorted_hall = sorted(hall_of_fame.items(), key=lambda x: x[1]['duration'], reverse=True)
        hall_of_fame = dict(sorted_hall[:100])

    # Save Hall of Fame to persistent storage
    save_hall_of_fame()

    # Combine trapped connections + top 100 hall of fame for display
    display_connections = trapped_connections.copy()
    display_connections.update(hall_of_fame)

    # Calculate global max and average trap duration from DISPLAYED connections
    all_durations = [conn['duration'] for conn in display_connections.values()]
    if all_durations:
        max_trap_duration = max(all_durations)
        avg_trap_duration = sum(all_durations) / len(all_durations)
    else:
        max_trap_duration = 0
        avg_trap_duration = 0

    # Calculate per-IP statistics (max and average trap duration)
    ip_durations = defaultdict(list)
    for conn_id, conn in display_connections.items():
        ip_durations[conn['ip']].append(conn['duration'])

    # Active connections: count trapped connections in our data
    # This is more accurate than using endlessh's counter, which can be stale
    active_connections = sum(1 for conn in display_connections.values() if conn['status'] == 'trapped')

    # Store display_connections back to individual_connections for metric generation
    individual_connections = display_connections

    # Parse 5min logs for new connections to add to counter
    for line in output_5min.split('\n'):
        match = re.search(accept_pattern, line)
        if match:
            # Create unique ID for this log entry (timestamp + FD)
            ts_match = re.search(timestamp_pattern, line)
            if ts_match:
                fd = match.group(2)
                log_id = f"{ts_match.group(1)}_{fd}"

                # Only count if we haven't seen this log entry before
                if log_id not in seen_log_entries:
                    seen_log_entries.add(log_id)
                    total_connections_counter += 1

    # Clean up old seen_log_entries (keep only last 10 minutes worth)
    # This prevents the set from growing forever
    if len(seen_log_entries) > 1000:
        # Keep only the most recent 500
        seen_log_entries.clear()
        # Will rebuild from next scrape

def generate_metrics():
    """Generate Prometheus metrics"""
    parse_endlessh_logs()

    metrics = []

    # Total connections counter (always increases, never resets - for rate calculations)
    metrics.append('# HELP endlessh_total_connections_total Total SSH connections since exporter start')
    metrics.append('# TYPE endlessh_total_connections_total counter')
    metrics.append(f'endlessh_total_connections_total {total_connections_counter}')

    # Total connections gauge (last 60min - for display)
    metrics.append('# HELP endlessh_total_connections Total SSH connections in last 60 minutes')
    metrics.append('# TYPE endlessh_total_connections gauge')
    metrics.append(f'endlessh_total_connections {len(individual_connections)}')

    # Active connections
    metrics.append('# HELP endlessh_active_connections Currently active SSH connections')
    metrics.append('# TYPE endlessh_active_connections gauge')
    metrics.append(f'endlessh_active_connections {active_connections}')

    # Global trap duration metrics
    metrics.append('# HELP endlessh_max_trap_duration_seconds Maximum trap duration in seconds')
    metrics.append('# TYPE endlessh_max_trap_duration_seconds gauge')
    metrics.append(f'endlessh_max_trap_duration_seconds {max_trap_duration:.2f}')

    metrics.append('# HELP endlessh_avg_trap_duration_seconds Average trap duration in seconds')
    metrics.append('# TYPE endlessh_avg_trap_duration_seconds gauge')
    metrics.append(f'endlessh_avg_trap_duration_seconds {avg_trap_duration:.2f}')

    # Individual connections - each connection gets its own metric
    # Sort by: status (trapped first), then by duration (longest first)
    def sort_key(item):
        conn = item[1]
        # trapped = 1, released = 0 (so trapped comes first when sorted desc)
        status_priority = 1 if conn['status'] == 'trapped' else 0
        # Return tuple: (status_priority desc, duration desc)
        return (-status_priority, -conn['duration'])

    metrics.append('# HELP endlessh_connection_info Individual connection information')
    metrics.append('# TYPE endlessh_connection_info gauge')

    # Sort connections and add sort_order field
    sorted_connections = sorted(individual_connections.items(), key=sort_key)

    # Track IP addresses to assign group numbers for alternating row colors
    ip_group_map = {}  # ip -> group_number
    current_group = 0
    last_ip = None

    for idx, (conn_id, conn) in enumerate(sorted_connections):
        # Format started time as readable string: "2025-10-14 18:32:29" (local time with date)
        started_str = conn["started"].astimezone().strftime("%Y-%m-%d %H:%M:%S")

        # Assign IP group number for alternating colors
        current_ip = conn['ip']
        if current_ip != last_ip:
            # New IP group
            if current_ip not in ip_group_map:
                ip_group_map[current_ip] = current_group
                current_group += 1
            last_ip = current_ip

        ip_group = ip_group_map[current_ip]

        # Add sort_order and ip_group as labels
        # ip_group allows alternating row colors (even/odd)
        metrics.append(
            f'endlessh_connection_info{{fd="{conn["fd"]}",ip="{conn["ip"]}",'
            f'port="{conn["port"]}",country="{conn["country"]}",city="{conn["city"]}",'
            f'status="{conn["status"]}",started="{started_str}",sort_order="{idx}",ip_group="{ip_group}"}} {conn["duration"]:.2f}'
        )

    # Calculate per-IP statistics for aggregated views
    ip_durations = defaultdict(list)
    for conn_id, conn in individual_connections.items():
        ip_durations[conn['ip']].append(conn['duration'])

    # Connections per IP (aggregated for map view and Top Attackers table)
    for ip, count in connections_per_ip.items():
        geo = ip_locations.get(ip, {})
        country = geo.get('country', 'Unknown').replace('"', '')
        country_code = geo.get('country_code', 'XX')
        city = geo.get('city', 'Unknown').replace('"', '')
        lat = geo.get('lat', 0.0)
        lon = geo.get('lon', 0.0)

        # Calculate max and avg trap duration for this IP
        durations = ip_durations.get(ip, [0])
        max_duration = max(durations) if durations else 0
        avg_duration = sum(durations) / len(durations) if durations else 0

        metrics.append(
            f'endlessh_connections_per_ip{{ip="{ip}",country="{country}",'
            f'country_code="{country_code}",city="{city}",'
            f'latitude="{lat}",longitude="{lon}",'
            f'max_trap_duration="{max_duration:.2f}",avg_trap_duration="{avg_duration:.2f}"}} {count}'
        )

    # Unique IPs
    metrics.append(f'endlessh_unique_ips {len(connections_per_ip)}')

    # Connections per country
    countries = defaultdict(int)
    for ip in connections_per_ip.keys():
        geo = ip_locations.get(ip, {})
        country = geo.get('country', 'Unknown')
        countries[country] += connections_per_ip[ip]

    for country, count in countries.items():
        country_safe = country.replace('"', '')
        metrics.append(f'endlessh_connections_per_country{{country="{country_safe}"}} {count}')

    return '\n'.join(metrics) + '\n'

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            metrics = generate_metrics()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(metrics.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress request logging
        return

def main():
    print(f'Endlessh GeoIP Exporter running on port {EXPORTER_PORT}')
    print(f'Metrics available at http://localhost:{EXPORTER_PORT}/metrics')

    # Load Hall of Fame from persistent storage
    load_hall_of_fame()

    server = HTTPServer(('0.0.0.0', EXPORTER_PORT), MetricsHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        # Save Hall of Fame one last time before shutting down
        save_hall_of_fame()
        server.shutdown()

if __name__ == '__main__':
    main()
