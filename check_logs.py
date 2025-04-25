#!/usr/bin/env python
"""
Railway Logs Analyzer

This script connects to Railway using the Railway CLI to download and analyze logs.
Requirements:
- Railway CLI must be installed and configured
- You must be logged in to Railway

Usage:
    python check_logs.py                   # Download and analyze latest logs
    python check_logs.py --lines 500       # Specify number of log lines to fetch
"""

import subprocess
import sys
import argparse
import tempfile
import re
import os
from datetime import datetime

def run_railway_command(args):
    """Run a Railway CLI command and return the output."""
    cmd = ["railway"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running Railway command: {result.stderr}")
            return None
        return result.stdout
    except Exception as e:
        print(f"Error running Railway command: {e}")
        return None

def download_logs(lines=200):
    """Download logs from Railway."""
    print(f"Downloading the latest {lines} lines of logs from Railway...")
    
    # Create a temporary file to store the logs
    with tempfile.NamedTemporaryFile(delete=False, mode='w+', suffix='.txt') as temp:
        temp_filename = temp.name
        
        # Run the Railway logs command
        logs = run_railway_command(["logs", "--lines", str(lines)])
        
        if not logs:
            print("Failed to download logs.")
            return None
            
        # Write logs to file
        temp.write(logs)
    
    print(f"Logs downloaded to temporary file: {temp_filename}")
    return temp_filename

def analyze_logs(log_file, output_file=None):
    """Analyze the Railway logs and extract relevant information."""
    print("Analyzing logs...")
    
    # Patterns to look for
    webhook_pattern = re.compile(r'(WEBHOOK|webhook)')
    error_pattern = re.compile(r'(ERROR|Error|error|Exception|exception|Failed|failed)')
    bot_start_pattern = re.compile(r'(Starting bot|Bot started|bot started)')
    health_check_pattern = re.compile(r'(Health check|health check|HEALTH)')
    db_pattern = re.compile(r'(database|Database|DB|PostgreSQL)')
    
    # Statistics
    stats = {
        'webhook_lines': [],
        'error_lines': [],
        'bot_start_lines': [],
        'health_check_lines': [],
        'db_lines': [],
        'total_lines': 0
    }
    
    # Read and analyze the logs
    with open(log_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            stats['total_lines'] += 1
            
            if webhook_pattern.search(line):
                stats['webhook_lines'].append((line_num, line.strip()))
                
            if error_pattern.search(line):
                stats['error_lines'].append((line_num, line.strip()))
                
            if bot_start_pattern.search(line):
                stats['bot_start_lines'].append((line_num, line.strip()))
                
            if health_check_pattern.search(line):
                stats['health_check_lines'].append((line_num, line.strip()))
                
            if db_pattern.search(line):
                stats['db_lines'].append((line_num, line.strip()))
    
    # Generate the report
    report = [
        f"=== RAILWAY LOGS ANALYSIS ===",
        f"Total lines: {stats['total_lines']}",
        f"Webhook-related lines: {len(stats['webhook_lines'])}",
        f"Error lines: {len(stats['error_lines'])}",
        f"Bot start lines: {len(stats['bot_start_lines'])}",
        f"Health check lines: {len(stats['health_check_lines'])}",
        f"Database-related lines: {len(stats['db_lines'])}",
        "",
        "=== WEBHOOK INFO ===",
    ]
    
    for line_num, line in stats['webhook_lines'][-10:]:  # Last 10 webhook lines
        report.append(f"{line_num}: {line}")
    
    report.append("")
    report.append("=== ERROR INFO ===")
    
    for line_num, line in stats['error_lines'][-20:]:  # Last 20 error lines
        report.append(f"{line_num}: {line}")
    
    report.append("")
    report.append("=== BOT START INFO ===")
    
    for line_num, line in stats['bot_start_lines'][-5:]:  # Last 5 bot start lines
        report.append(f"{line_num}: {line}")
    
    report.append("")
    report.append("=== HEALTH CHECK INFO ===")
    
    for line_num, line in stats['health_check_lines'][-10:]:  # Last 10 health check lines
        report.append(f"{line_num}: {line}")
    
    report.append("")
    report.append("=== DATABASE INFO ===")
    
    for line_num, line in stats['db_lines'][-10:]:  # Last 10 database lines
        report.append(f"{line_num}: {line}")
    
    # Write the report
    report_text = "\n".join(report)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report_text)
        print(f"Report written to {output_file}")
    else:
        print(report_text)
    
    return stats

def main():
    parser = argparse.ArgumentParser(description='Railway Logs Analyzer')
    
    parser.add_argument('--lines', type=int, default=200, help='Number of log lines to fetch (default: 200)')
    parser.add_argument('--output', '-o', help='Output file for the report')
    
    args = parser.parse_args()
    
    # Download logs
    log_file = download_logs(args.lines)
    
    if not log_file:
        sys.exit(1)
    
    # Analyze logs
    analyze_logs(log_file, args.output)
    
    # Clean up temporary file
    if os.path.exists(log_file):
        os.unlink(log_file)

if __name__ == "__main__":
    main() 