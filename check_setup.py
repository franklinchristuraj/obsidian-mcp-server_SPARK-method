#!/usr/bin/env python3
"""
Setup Verification Script for Obsidian MCP Server
Checks if everything is configured correctly
"""
import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} (requires 3.8+)")
        return False

def check_dependencies():
    """Check if required packages are installed"""
    required = ['fastapi', 'uvicorn', 'httpx', 'pydantic', 'yaml']
    missing = []
    
    for package in required:
        try:
            if package == 'yaml':
                __import__('yaml')
            else:
                __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} (missing)")
            missing.append(package)
    
    return len(missing) == 0

def check_env_file():
    """Check if .env file exists and has required variables"""
    env_path = Path('.env')
    required_vars = [
        'MCP_API_KEY',
        'OBSIDIAN_API_URL',
        'OBSIDIAN_API_KEY',
        'OBSIDIAN_VAULT_PATH'
    ]
    
    if not env_path.exists():
        print("❌ .env file not found")
        print("💡 Create .env file with required variables")
        return False
    
    print("✅ .env file exists")
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'KEY' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"✅ {var}={display_value}")
        else:
            print(f"❌ {var} (not set)")
            missing.append(var)
    
    return len(missing) == 0

def check_obsidian_connection():
    """Check if Obsidian API is accessible"""
    import httpx
    
    api_url = os.getenv("OBSIDIAN_API_URL")
    api_key = os.getenv("OBSIDIAN_API_KEY")
    
    if not api_url or not api_key:
        print("⚠️  Skipping Obsidian connection check (missing config)")
        return None
    
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        # Disable SSL verification for self-signed certs
        client = httpx.Client(verify=False, timeout=5.0)
        response = client.get(f"{api_url}/", headers=headers)
        
        if response.status_code == 200:
            print(f"✅ Obsidian API accessible at {api_url}")
            return True
        else:
            print(f"⚠️  Obsidian API returned status {response.status_code}")
            return False
    except httpx.ConnectError:
        print(f"❌ Cannot connect to Obsidian API at {api_url}")
        print("💡 Check if Obsidian REST API plugin is running")
        return False
    except Exception as e:
        print(f"⚠️  Error checking Obsidian API: {e}")
        return None

def check_vault_path():
    """Check if vault path exists"""
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    
    if not vault_path:
        print("⚠️  OBSIDIAN_VAULT_PATH not set")
        return None
    
    if os.path.exists(vault_path):
        print(f"✅ Vault path exists: {vault_path}")
        return True
    else:
        print(f"❌ Vault path not found: {vault_path}")
        return False

def main():
    print("🔍 Obsidian MCP Server Setup Verification")
    print("=" * 50)
    print()
    
    checks = []
    
    print("📦 Checking Python and Dependencies:")
    print("-" * 30)
    checks.append(check_python_version())
    checks.append(check_dependencies())
    print()
    
    print("⚙️  Checking Configuration:")
    print("-" * 30)
    checks.append(check_env_file())
    checks.append(check_vault_path())
    print()
    
    print("🔌 Checking Obsidian Connection:")
    print("-" * 30)
    obsidian_check = check_obsidian_connection()
    if obsidian_check is not None:
        checks.append(obsidian_check)
    print()
    
    print("=" * 50)
    print("📋 SUMMARY:")
    passed = sum(1 for c in checks if c)
    total = len(checks)
    
    if passed == total:
        print(f"✅ All checks passed ({passed}/{total})")
        print()
        print("🚀 To start the server:")
        print("   source venv/bin/activate")
        print("   python main.py")
        return 0
    else:
        print(f"⚠️  {passed}/{total} checks passed")
        print()
        print("💡 Next steps:")
        if not all(checks[:2]):
            print("   1. Install dependencies: pip install -r requirements.txt")
        if not checks[2] if len(checks) > 2 else False:
            print("   2. Create .env file with required variables")
        if not checks[3] if len(checks) > 3 else False:
            print("   3. Verify OBSIDIAN_VAULT_PATH points to your vault")
        if obsidian_check is False:
            print("   4. Ensure Obsidian REST API plugin is running")
            print("   5. Check OBSIDIAN_API_URL and OBSIDIAN_API_KEY")
        return 1

if __name__ == "__main__":
    sys.exit(main())

