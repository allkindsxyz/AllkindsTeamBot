#!/usr/bin/env python
"""
Simple test for health check endpoints.
"""
import requests
import sys
import os

def test_health_endpoint(url):
    """Test a health check endpoint."""
    print(f"Testing health endpoint at {url}...")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    # Get URL from command line or use default
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Try to build URL from environment
        railway_url = os.environ.get("RAILWAY_PUBLIC_URL", "")
        if railway_url:
            url = f"{railway_url}/health"
        else:
            url = "http://localhost:8080/health"
    
    print(f"Testing URL: {url}")
    success = test_health_endpoint(url)
    print(f"Test {'passed' if success else 'failed'}")
    sys.exit(0 if success else 1) 