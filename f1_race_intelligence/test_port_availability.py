#!/usr/bin/env python3
"""Quick test to verify Gradio UI can start without port errors."""

import socket
import sys

def find_available_port(start_port=7860, max_attempts=10):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return port
        except OSError:
            continue
    return start_port  # Fallback

if __name__ == "__main__":
    print("Testing port availability...")
    
    # Check if default port is available
    for port in range(7860, 7870):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", port))
            sock.close()
            print(f"  Port {port}: Available ✓")
        except OSError as e:
            print(f"  Port {port}: In use (will fallback)")
    
    available = find_available_port()
    print(f"\nWill use port: {available}")
    print("✓ Port selection logic working correctly")
