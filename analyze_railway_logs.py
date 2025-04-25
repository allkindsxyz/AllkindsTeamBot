#!/usr/bin/env python
"""
Railway Log Analyzer

Usage:
    1. Download the railway logs from your project
    2. Run this script: python analyze_railway_logs.py path/to/logs.txt
"""

import sys
import re
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import argparse


def parse_logs(logfile):
    """Parse Railway logs into structured data."""
    # Regex to match log lines
    log_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+Z) (\w+) (.*)')
    
    # Parse the logs
    parsed_logs = []
    error_lines = []
    
    with open(logfile, 'r') as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if match:
                timestamp, level, message = match.groups()
                try:
                    ts = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
                except ValueError:
                    ts = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
                
                parsed_logs.append({
                    'timestamp': ts,
                    'level': level,
                    'message': message
                })
                
                # Collect error lines for deeper analysis
                if level.upper() in ['ERROR', 'CRITICAL', 'FATAL']:
                    error_lines.append((ts, message))
            else:
                # Handle continuation lines
                if parsed_logs:
                    parsed_logs[-1]['message'] += '\n' + line.strip()
    
    return parsed_logs, error_lines


def analyze_webhook_requests(logs):
    """Analyze webhook requests from logs."""
    webhook_pattern = re.compile(r'WEBHOOK REQUEST: method=(\w+), ip=([\d\.]+)')
    webhook_calls = []
    
    for log in logs:
        match = webhook_pattern.search(log['message'])
        if match:
            method, ip = match.groups()
            webhook_calls.append({
                'timestamp': log['timestamp'],
                'method': method,
                'ip': ip,
                'message': log['message']
            })
    
    return webhook_calls


def analyze_errors(logs, error_lines):
    """Analyze errors from logs."""
    error_types = Counter()
    error_messages = []
    error_timelines = defaultdict(list)
    
    for log in logs:
        if log['level'].upper() in ['ERROR', 'CRITICAL', 'FATAL']:
            # Extract the error type
            message = log['message']
            error_type = "Unknown Error"
            
            # Try to find specific error patterns
            if "ConnectionError" in message:
                error_type = "ConnectionError"
            elif "TimeoutError" in message:
                error_type = "TimeoutError"
            elif "OperationalError" in message:
                error_type = "Database OperationalError"
            elif "IntegrityError" in message:
                error_type = "Database IntegrityError"
            elif "TelegramAPIError" in message:
                error_type = "Telegram API Error"
            elif "webhook" in message.lower():
                error_type = "Webhook Error"
            elif "aiogram" in message.lower():
                error_type = "Aiogram Error"
            
            error_types[error_type] += 1
            error_messages.append({
                'timestamp': log['timestamp'],
                'type': error_type,
                'message': message
            })
            error_timelines[error_type].append(log['timestamp'])
    
    # Add error timelines from error_lines for deeper analysis
    for ts, message in error_lines:
        # Additional processing if needed
        pass
        
    return error_types, error_messages, error_timelines


def analyze_railway_diagnostics(logs):
    """Find and analyze Railway diagnostics reports in logs."""
    diagnostic_pattern = re.compile(r'==== RAILWAY DIAGNOSTICS REPORT ====')
    diagnostics = []
    
    for i, log in enumerate(logs):
        if diagnostic_pattern.search(log['message']):
            # Collect the full report (might span multiple log entries)
            report = log['message']
            j = i + 1
            while j < len(logs) and logs[j]['timestamp'] - log['timestamp'] < timedelta(seconds=1):
                report += '\n' + logs[j]['message']
                j += 1
            
            diagnostics.append({
                'timestamp': log['timestamp'],
                'report': report
            })
    
    return diagnostics


def find_performance_issues(logs):
    """Identify potential performance issues from logs."""
    # Look for slow operations
    slow_operations = []
    duration_pattern = re.compile(r'completed in (\d+\.\d+)s')
    
    for log in logs:
        match = duration_pattern.search(log['message'])
        if match:
            duration = float(match.group(1))
            if duration > 1.0:  # operations taking more than 1 second
                slow_operations.append({
                    'timestamp': log['timestamp'],
                    'duration': duration,
                    'message': log['message']
                })
    
    return slow_operations


def analyze_database_operations(logs):
    """Analyze database operations from logs."""
    db_ops = []
    db_pattern = re.compile(r'DB OPERATION #(\d+) - (\w+)')
    
    for log in logs:
        match = db_pattern.search(log['message'])
        if match:
            op_num, op_name = match.groups()
            db_ops.append({
                'timestamp': log['timestamp'],
                'operation': op_name,
                'message': log['message']
            })
    
    return db_ops


def generate_report(logs, webhook_calls, error_types, error_messages, diagnostics, slow_operations, db_ops):
    """Generate a comprehensive analysis report."""
    # Count log levels
    log_levels = Counter([log['level'].upper() for log in logs])
    
    # Time range
    if logs:
        start_time = min(log['timestamp'] for log in logs)
        end_time = max(log['timestamp'] for log in logs)
        duration = end_time - start_time
    else:
        start_time = end_time = datetime.now()
        duration = timedelta(0)
    
    # Generate the report
    report = [
        "======= RAILWAY LOG ANALYSIS REPORT =======",
        f"Log Period: {start_time} to {end_time} ({duration})",
        f"Total Log Entries: {len(logs)}",
        "\n=== LOG LEVELS ===",
    ]
    
    for level, count in log_levels.items():
        report.append(f"{level}: {count}")
    
    # Error summary
    report.append("\n=== ERROR SUMMARY ===")
    for error_type, count in error_types.most_common():
        report.append(f"{error_type}: {count}")
    
    # Top 5 recent errors
    report.append("\n=== RECENT ERRORS (Last 5) ===")
    recent_errors = sorted(error_messages, key=lambda e: e['timestamp'], reverse=True)[:5]
    for i, error in enumerate(recent_errors, 1):
        report.append(f"{i}. [{error['timestamp']}] {error['type']}: {error['message'][:100]}...")
    
    # Webhook calls
    report.append(f"\n=== WEBHOOK CALLS ===")
    report.append(f"Total Webhook Calls: {len(webhook_calls)}")
    if webhook_calls:
        last_webhook = max(webhook_calls, key=lambda w: w['timestamp'])
        report.append(f"Last Webhook Call: {last_webhook['timestamp']} - {last_webhook['method']} from {last_webhook['ip']}")
    
    # Slow operations
    report.append(f"\n=== SLOW OPERATIONS (>1s) ===")
    report.append(f"Total Slow Operations: {len(slow_operations)}")
    for i, op in enumerate(sorted(slow_operations, key=lambda o: o['duration'], reverse=True)[:5], 1):
        report.append(f"{i}. [{op['timestamp']}] {op['duration']}s: {op['message'][:100]}...")
    
    # Database operations
    db_op_counts = Counter([op['operation'] for op in db_ops])
    report.append(f"\n=== DATABASE OPERATIONS ===")
    report.append(f"Total Database Operations: {len(db_ops)}")
    for op, count in db_op_counts.most_common():
        report.append(f"{op}: {count}")
    
    return "\n".join(report)


def main():
    """Main function to run the analysis."""
    parser = argparse.ArgumentParser(description='Analyze Railway logs for debugging.')
    parser.add_argument('logfile', help='Path to the log file')
    parser.add_argument('--output', '-o', help='Output file for the report')
    
    args = parser.parse_args()
    
    print(f"Analyzing log file: {args.logfile}")
    
    # Parse and analyze the logs
    logs, error_lines = parse_logs(args.logfile)
    print(f"Parsed {len(logs)} log entries")
    
    # Analyze various aspects
    webhook_calls = analyze_webhook_requests(logs)
    error_types, error_messages, error_timelines = analyze_errors(logs, error_lines)
    diagnostics = analyze_railway_diagnostics(logs)
    slow_operations = find_performance_issues(logs)
    db_ops = analyze_database_operations(logs)
    
    # Generate report
    report = generate_report(logs, webhook_calls, error_types, error_messages, 
                            diagnostics, slow_operations, db_ops)
    
    # Output the report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main() 