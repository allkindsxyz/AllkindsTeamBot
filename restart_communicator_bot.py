#!/usr/bin/env python3
"""
Script to restart the communicator bot in Railway
This should help resolve the conflict error:
"TelegramConflictError: terminated by other getUpdates request"
"""

import sys
import subprocess
import time

def run_command(command, check=True, show_output=True):
    """Run a shell command and return the output."""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if show_output:
        print(result.stdout)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def check_railway_cli():
    """Check if Railway CLI is installed and properly configured."""
    try:
        railway_version = run_command("railway version", check=False, show_output=False)
        if "command not found" in railway_version.lower():
            print("❌ Railway CLI not installed.")
            print("Please install it with: npm i -g @railway/cli")
            return False
        
        print(f"✅ Railway CLI installed: {railway_version}")
        
        # Check login status
        railway_user = run_command("railway whoami", check=False, show_output=False)
        if "not logged in" in railway_user.lower():
            print("❌ Not logged in to Railway.")
            print("Please login with: railway login")
            return False
        
        print(f"✅ Logged in to Railway as: {railway_user}")
        return True
    
    except Exception as e:
        print(f"❌ Error checking Railway CLI: {e}")
        return False

def list_railway_services():
    """List all services in the current Railway project."""
    print("\nListing Railway services...")
    
    try:
        services = run_command("railway service list", check=False)
        if not services or "no services found" in services.lower():
            print("❌ No services found in the current project.")
            print("Please link to your project with: railway link")
            return None
        
        print("✅ Found Railway services")
        return services
    except Exception as e:
        print(f"❌ Error listing services: {e}")
        return None

def restart_service(service_name):
    """Restart the specified service in Railway."""
    print(f"\nRestarting '{service_name}' service...")
    
    try:
        # Attempt to restart the service
        restart_output = run_command(f"railway service restart {service_name}", check=False)
        
        if "error" in restart_output.lower() or "not found" in restart_output.lower():
            print(f"❌ Failed to restart service: {restart_output}")
            return False
        
        print(f"✅ Service '{service_name}' restart initiated")
        print("\nWaiting for service to restart...")
        time.sleep(5)  # Give it some time to start restarting
        
        # Monitor restart status
        for i in range(12):  # Check for up to 60 seconds
            status = run_command(f"railway service status {service_name}", check=False, show_output=False)
            
            if "up" in status.lower() or "running" in status.lower():
                print(f"✅ Service '{service_name}' is now running")
                return True
            
            print(f"Service status: {status.strip() or 'Restarting...'}")
            time.sleep(5)  # Wait before checking again
        
        print("⚠️ Timeout waiting for service to restart. Please check manually.")
        return True  # Return True anyway as we initiated the restart
    
    except Exception as e:
        print(f"❌ Error restarting service: {e}")
        return False

def find_communicator_service(services_output):
    """Find the communicator bot service from the services list output."""
    if not services_output:
        return None
    
    lines = services_output.strip().split('\n')
    services = []
    
    for line in lines:
        if not line.strip():
            continue
        
        # Simple parsing of service names
        parts = line.split()
        if len(parts) >= 1:
            services.append(parts[0])
    
    # Look for likely communicator bot service names
    communicator_candidates = [
        s for s in services if any(x in s.lower() for x in [
            "communicator", "chat", "message", "allkindschat", "chatservice", "messenger"
        ])
    ]
    
    if communicator_candidates:
        return communicator_candidates[0]
    elif services:
        # If we can't identify by name, ask user
        print("\nCould not automatically identify the communicator bot service.")
        print("Available services:")
        for i, service in enumerate(services):
            print(f"{i+1}. {service}")
        
        try:
            selection = input("\nEnter the number of the communicator bot service: ")
            index = int(selection) - 1
            if 0 <= index < len(services):
                return services[index]
            else:
                print("❌ Invalid selection")
                return None
        except (ValueError, IndexError):
            print("❌ Invalid selection")
            return None
    
    return None

def main():
    """Restart the communicator bot in Railway."""
    print("=== Communicator Bot Restart Tool ===")
    
    # Check Railway CLI
    if not check_railway_cli():
        print("\n❌ Railway CLI check failed. Please fix the issues and try again.")
        sys.exit(1)
    
    # Link if needed
    run_command("railway link", check=False)
    
    # List services
    services_output = list_railway_services()
    if not services_output:
        print("\n❌ Could not list Railway services. Please check your project configuration.")
        sys.exit(1)
    
    # Find communicator service
    communicator_service = find_communicator_service(services_output)
    if not communicator_service:
        print("\n❌ Could not identify the communicator bot service.")
        print("Please restart it manually in the Railway dashboard.")
        sys.exit(1)
    
    # Confirm restart
    confirm = input(f"\nReady to restart '{communicator_service}'. Proceed? (y/n): ")
    if confirm.lower() != 'y':
        print("Restart aborted.")
        sys.exit(0)
    
    # Restart service
    if restart_service(communicator_service):
        print("\n✅ Communicator bot restart process completed!")
        print("\nNext steps:")
        print("1. Check bot status with: /start")
        print("2. Monitor logs with: railway logs")
        print("3. If issues persist, check for webhook conflicts in the Telegram Bot API")
    else:
        print("\n❌ Failed to restart the communicator bot.")
        print("Please try restarting it manually in the Railway dashboard.")

if __name__ == "__main__":
    main() 