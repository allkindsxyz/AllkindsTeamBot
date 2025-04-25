#!/usr/bin/env python
"""
Database Connection Test Script

This script tests database connectivity using multiple methods to diagnose connection issues.
Usage:
    python db_connection_test.py
"""

import os
import asyncio
import sys
import urllib.parse
import time
from loguru import logger

# Set up logging
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("db_connection_test.log", rotation="1 MB", level="DEBUG")

async def test_asyncpg_connection():
    """Test direct connection using asyncpg."""
    try:
        import asyncpg
        logger.info("Testing direct asyncpg connection...")
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable not found")
            return False
            
        logger.info(f"Using DATABASE_URL: {db_url[:20]}...")
        
        # Parse connection parameters from URL
        result = urllib.parse.urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path.lstrip('/')
        hostname = result.hostname
        port = result.port or 5432
        
        logger.info(f"Parsed connection parameters:")
        logger.info(f"  Hostname: {hostname}")
        logger.info(f"  Port: {port}")
        logger.info(f"  Database: {database}")
        logger.info(f"  Username: {username}")
        
        # Try to connect with asyncpg directly
        try:
            conn = await asyncpg.connect(
                host=hostname,
                port=port,
                user=username,
                password=password,
                database=database,
                timeout=10
            )
            logger.info("asyncpg connection successful!")
            
            # Execute a simple query
            version = await conn.fetchval('SELECT version()')
            logger.info(f"PostgreSQL version: {version}")
            
            await conn.close()
            return True
        except Exception as e:
            logger.error(f"asyncpg connection failed: {e}")
            
            # Try with explicit IPv4 connection
            try:
                logger.info("Trying to connect using explicit 127.0.0.1...")
                conn = await asyncpg.connect(
                    host="127.0.0.1",
                    port=port,
                    user=username,
                    password=password,
                    database=database,
                    timeout=10
                )
                logger.info("asyncpg connection with localhost successful!")
                
                # Execute a simple query
                version = await conn.fetchval('SELECT version()')
                logger.info(f"PostgreSQL version: {version}")
                
                await conn.close()
                return True
            except Exception as e2:
                logger.error(f"asyncpg localhost connection failed: {e2}")
            return False
    except ImportError:
        logger.error("asyncpg module not installed")
        return False

def test_psycopg2_connection():
    """Test connection using psycopg2."""
    try:
        import psycopg2
        logger.info("Testing psycopg2 connection...")
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable not found")
            return False
            
        # Try to connect with the full URL
        try:
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute('SELECT version()')
            version = cursor.fetchone()[0]
            logger.info(f"psycopg2 connection successful - PostgreSQL version: {version}")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"psycopg2 connection failed: {e}")
            
            # Parse connection parameters from URL
            result = urllib.parse.urlparse(db_url)
            username = result.username
            password = result.password
            database = result.path.lstrip('/')
            hostname = result.hostname
            port = result.port or 5432
            
            # Try connecting with individual parameters
            try:
                conn = psycopg2.connect(
                    host=hostname,
                    port=port,
                    user=username,
                    password=password,
                    dbname=database
                )
                cursor = conn.cursor()
                cursor.execute('SELECT version()')
                version = cursor.fetchone()[0]
                logger.info(f"psycopg2 parameter connection successful - PostgreSQL version: {version}")
                conn.close()
                return True
            except Exception as e2:
                logger.error(f"psycopg2 parameter connection failed: {e2}")
                
                # Try with localhost explicitly
                try:
                    conn = psycopg2.connect(
                        host="127.0.0.1",
                        port=port,
                        user=username,
                        password=password,
                        dbname=database
                    )
                    cursor = conn.cursor()
                    cursor.execute('SELECT version()')
                    version = cursor.fetchone()[0]
                    logger.info(f"psycopg2 localhost connection successful - PostgreSQL version: {version}")
                    conn.close()
                    return True
                except Exception as e3:
                    logger.error(f"psycopg2 localhost connection failed: {e3}")
            return False
    except ImportError:
        logger.error("psycopg2 module not installed")
        return False

async def test_sqlalchemy_connection():
    """Test connection using SQLAlchemy."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        logger.info("Testing SQLAlchemy connection...")
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable not found")
            return False
            
        # Convert postgres:// to postgresql+asyncpg://
        if db_url.startswith('postgres://'):
            sqlalchemy_url = db_url.replace('postgres://', 'postgresql+asyncpg://', 1)
        elif db_url.startswith('postgresql://'):
            sqlalchemy_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        else:
            sqlalchemy_url = db_url
            
        logger.info(f"Using SQLAlchemy URL: {sqlalchemy_url[:20]}...")
        
        # Create engine with various connection parameters
        engine = create_async_engine(
            sqlalchemy_url,
            echo=True,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            pool_size=5,
            max_overflow=10,
            connect_args={
                "timeout": 10,
                "command_timeout": 10,
                "server_settings": {
                    "application_name": "allkinds_test"
                }
            }
        )
        
        # Try to connect
        try:
            async with engine.connect() as conn:
                result = await conn.execute("SELECT version()")
                version = result.scalar()
                logger.info(f"SQLAlchemy connection successful - PostgreSQL version: {version}")
                return True
        except Exception as e:
            logger.error(f"SQLAlchemy connection failed: {e}")
            
            # Try with modified URL using 127.0.0.1 explicitly
            try:
                # Parse and rebuild URL with 127.0.0.1
                parsed = urllib.parse.urlparse(sqlalchemy_url)
                hostname = parsed.hostname
                new_netloc = parsed.netloc.replace(hostname, '127.0.0.1')
                url_parts = list(parsed)
                url_parts[1] = new_netloc
                local_url = urllib.parse.urlunparse(url_parts)
                
                logger.info(f"Trying with explicit 127.0.0.1: {local_url[:20]}...")
                
                local_engine = create_async_engine(
                    local_url,
                    echo=True,
                    pool_pre_ping=True,
                    pool_recycle=300,
                    pool_timeout=30,
                    pool_size=5,
                    max_overflow=10,
                    connect_args={
                        "timeout": 10,
                        "command_timeout": 10
                    }
                )
                
                async with local_engine.connect() as conn:
                    result = await conn.execute("SELECT version()")
                    version = result.scalar()
                    logger.info(f"SQLAlchemy localhost connection successful - PostgreSQL version: {version}")
                    return True
            except Exception as e2:
                logger.error(f"SQLAlchemy localhost connection failed: {e2}")
            return False
    except ImportError:
        logger.error("SQLAlchemy module not installed")
        return False

def check_network_connectivity():
    """Check basic network connectivity."""
    import socket
    
    logger.info("Checking network connectivity...")
    
    # Try to resolve common hostnames
    for hostname in ["www.google.com", "api.telegram.org", "github.com"]:
        try:
            ip = socket.gethostbyname(hostname)
            logger.info(f"Resolved {hostname} to {ip}")
        except Exception as e:
            logger.error(f"Failed to resolve {hostname}: {e}")
    
    # Check if Railway internal services are reachable
    if os.environ.get('DATABASE_URL'):
        try:
            db_url = os.environ.get('DATABASE_URL')
            parsed = urllib.parse.urlparse(db_url)
            hostname = parsed.hostname
            port = parsed.port or 5432
            
            logger.info(f"Checking if database host {hostname}:{port} is reachable...")
            
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            # Try to connect
            result = sock.connect_ex((hostname, port))
            if result == 0:
                logger.info(f"Port {port} on {hostname} is open")
            else:
                logger.error(f"Port {port} on {hostname} is not reachable (error: {result})")
            
            sock.close()
        except Exception as e:
            logger.error(f"Socket connection test failed: {e}")

def check_environment():
    """Check environment variables and system information."""
    import platform
    
    logger.info("Checking environment variables and system information:")
    logger.info(f"Python version: {platform.python_version()}")
    logger.info(f"Platform: {platform.platform()}")
    
    # Check for Railway environment variables
    railway_vars = [var for var in os.environ.keys() if var.startswith('RAILWAY_')]
    logger.info(f"Found {len(railway_vars)} Railway environment variables: {railway_vars}")
    
    # Check critical environment variables
    critical_vars = ['DATABASE_URL', 'PORT', 'TELEGRAM_BOT_TOKEN', 'WEBHOOK_DOMAIN']
    for var in critical_vars:
        if var in os.environ:
            value = os.environ.get(var)
            masked_value = value[:10] + '...' if value else value
            logger.info(f"{var} is set: {masked_value}")
        else:
            logger.warning(f"{var} is NOT set")

def fix_base_py():
    """Fix potential issues in the base.py file."""
    logger.info("Checking for potential fixes in base.py...")
    
    try:
        from src.db.base import process_database_url, ORIGINAL_DB_URL
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable not found, cannot test fixes")
            return
        
        # Try processing the URL
        processed_url = process_database_url(db_url)
        logger.info(f"Process function gave: {processed_url[:20]}...")
        
        # Check for host override in connect_args
        from src.db.base import connect_args
        logger.info(f"Current connect_args in base.py: {connect_args}")
        
        # Check if there might be an issue with IP addressing
        if "host" in connect_args and connect_args["host"] == "127.0.0.1":
            logger.warning("base.py is forcing host=127.0.0.1 in connect_args")
            logger.info("This might be causing issues if Railway is using internal hostnames")
            
    except ImportError as e:
        logger.error(f"Could not import modules from src.db.base: {e}")
    except Exception as e:
        logger.error(f"Error checking base.py: {e}")

async def main():
    """Run all tests."""
    logger.info("=== DATABASE CONNECTION TEST SCRIPT ===")
    
    # Check environment first
    check_environment()
    
    # Check network connectivity
    check_network_connectivity()
    
    # Check if there are potential fixes in base.py
    fix_base_py()
    
    # Test connections
    psycopg2_result = test_psycopg2_connection()
    asyncpg_result = await test_asyncpg_connection()
    sqlalchemy_result = await test_sqlalchemy_connection()
    
    # Summary
    logger.info("\n=== CONNECTION TEST SUMMARY ===")
    logger.info(f"psycopg2 connection: {'SUCCESS' if psycopg2_result else 'FAILED'}")
    logger.info(f"asyncpg connection: {'SUCCESS' if asyncpg_result else 'FAILED'}")
    logger.info(f"SQLAlchemy connection: {'SUCCESS' if sqlalchemy_result else 'FAILED'}")
    
    if not any([psycopg2_result, asyncpg_result, sqlalchemy_result]):
        logger.error("All connection methods failed. This suggests a serious connectivity issue.")
        
        # Provide recommendations
        logger.info("\n=== RECOMMENDATIONS ===")
        logger.info("1. Check if the DATABASE_URL environment variable is correct")
        logger.info("2. Verify the database instance is running on Railway")
        logger.info("3. Check for network restrictions between services")
        logger.info("4. Try removing 'host': '127.0.0.1' from connect_args in src/db/base.py")
        logger.info("5. Consider restarting the database service on Railway")
    elif not sqlalchemy_result:
        logger.warning("SQLAlchemy connection failed, but direct connections work.")
        logger.info("\n=== RECOMMENDATIONS ===")
        logger.info("1. Update the connect_args in src/db/base.py")
        logger.info("2. Check for driver compatibility issues with asyncpg")
        logger.info("3. Consider updating the process_database_url function")

if __name__ == "__main__":
    asyncio.run(main()) 