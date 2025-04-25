#!/usr/bin/env python3
import os
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def stop_communicator_bot():
    """Find and stop running communicator bot processes."""
    logging.info("Looking for running communicator bot processes...")
    
    # Find all Python processes that match the communicator bot pattern
    try:
        # Get all processes with 'python' and 'communicator' in the command line
        ps_output = subprocess.check_output(
            ["ps", "aux"], 
            universal_newlines=True
        )
        
        # Filter lines containing both 'python' and 'communicator'
        comm_bot_lines = [
            line for line in ps_output.split('\n') 
            if 'python' in line.lower() and 'communicator' in line.lower()
            and 'stop_communicator' not in line.lower()  # Exclude this script
        ]
        
        if not comm_bot_lines:
            logging.info("No running communicator bot processes found.")
            return 0
        
        logging.info(f"Found {len(comm_bot_lines)} communicator bot processes.")
        
        # Extract PIDs
        pids = []
        for line in comm_bot_lines:
            parts = line.split()
            if len(parts) > 1:
                try:
                    pid = int(parts[1])
                    pids.append(pid)
                except ValueError:
                    continue
        
        # Terminate each process
        for pid in pids:
            logging.info(f"Terminating process with PID: {pid}")
            try:
                os.kill(pid, 15)  # Send SIGTERM
                logging.info(f"Successfully terminated process {pid}")
            except ProcessLookupError:
                logging.warning(f"Process {pid} not found.")
            except PermissionError:
                logging.error(f"Permission denied to terminate process {pid}")
            except Exception as e:
                logging.error(f"Error terminating process {pid}: {e}")
        
        return len(pids)
    
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing ps command: {e}")
        return 0
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return 0

if __name__ == "__main__":
    stopped_count = stop_communicator_bot()
    
    if stopped_count > 0:
        logging.info(f"Successfully stopped {stopped_count} communicator bot processes.")
    else:
        logging.info("No communicator bot processes were stopped.")
    
    sys.exit(0) 