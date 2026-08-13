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
    required = ['fastapi', 'uvicorn', 'pydantic', 'yaml']
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

def check_vault_path():
    """Check if vault path exists and has the expected scope folders"""
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")

    if not vault_path:
        print("⚠️  OBSIDIAN_VAULT_PATH not set")
        return None

    if not os.path.exists(vault_path):
        print(f"❌ Vault path not found: {vault_path}")
        return False

    print(f"✅ Vault path exists: {vault_path}")
    missing_scopes = [
        s for s in ("personal", "passion", "work", "parallax")
        if not os.path.isdir(os.path.join(vault_path, s))
    ]
    if missing_scopes:
        print(f"⚠️  Missing scope folders: {missing_scopes}")
    else:
        print("✅ personal/, passion/, work/, parallax/ scope folders present")
    return True

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
        return 1

if __name__ == "__main__":
    sys.exit(main())

