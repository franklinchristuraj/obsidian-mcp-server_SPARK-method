#!/usr/bin/env python3
"""
Comprehensive Obsidian REST API Diagnostic Script
"""
import subprocess
import socket
import sys

def check_port_listening(port):
    """Check if a port is listening"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

def run_command(cmd):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except:
        return "", "Command failed", 1

def main():
    print("🔍 Obsidian REST API Diagnostic Report")
    print("=" * 50)
    
    # Check if port 36961 is listening
    print("\n📡 Port Status Check:")
    if check_port_listening(36961):
        print("✅ Port 36961 is accepting connections")
    else:
        print("❌ Port 36961 is NOT listening")
    
    # Check for any processes on common Obsidian ports
    print("\n🔍 Scanning for services on common ports:")
    common_ports = [36961, 27123, 8080, 3000, 8000, 8081]
    for port in common_ports:
        if check_port_listening(port):
            print(f"✅ Service found on port {port}")
        else:
            print(f"❌ No service on port {port}")
    
    # Check for Obsidian processes
    print("\n🔍 Looking for Obsidian processes:")
    stdout, stderr, code = run_command("ps aux | grep -i obsidian | grep -v grep")
    if stdout:
        print("✅ Found Obsidian processes:")
        for line in stdout.split('\n'):
            if line.strip():
                print(f"   {line}")
    else:
        print("❌ No Obsidian processes found")
    
    # Check listening ports
    print("\n🔍 All listening ports:")
    stdout, stderr, code = run_command("ss -tuln | grep LISTEN | head -10")
    if stdout:
        print("Current listening ports:")
        for line in stdout.split('\n'):
            if line.strip():
                print(f"   {line}")
    
    # Final recommendation
    print("\n" + "=" * 50)
    print("📋 DIAGNOSIS SUMMARY:")
    
    if check_port_listening(36961):
        print("✅ Obsidian REST API appears to be running")
        print("🔧 Next steps:")
        print("   1. Test with: curl http://127.0.0.1:36961/vault/")
        print("   2. Set OBSIDIAN_API_KEY environment variable if needed")
        print("   3. Run: python test_obsidian_api.py")
    else:
        print("❌ Obsidian REST API is NOT running")
        print("🔧 Required steps:")
        print("   1. Install Obsidian desktop application")
        print("   2. Install 'REST API' community plugin")
        print("   3. Enable the plugin in Settings > Community Plugins")
        print("   4. Configure plugin settings (port, API key)")
        print("   5. Restart Obsidian")
        print("\n📖 See setup_obsidian_api.md for detailed instructions")

if __name__ == "__main__":
    main()
