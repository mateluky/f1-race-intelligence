#!/usr/bin/env python3
"""Test the improved port selection logic."""

import socket
import os

def find_available_port(start_port=7860, max_attempts=50):
    """Find an available port starting from start_port, with wider range and better fallback."""
    # First check environment variable for explicit port override
    env_port = os.environ.get('GRADIO_SERVER_PORT')
    if env_port:
        try:
            port = int(env_port)
            print(f"Using port from GRADIO_SERVER_PORT env var: {port}")
            return port
        except (ValueError, TypeError):
            pass
    
    for port in range(start_port, start_port + max_attempts):
        try:
            # Test both localhost and 0.0.0.0 with SO_REUSEADDR to handle TIME_WAIT
            for addr in ["127.0.0.1", "0.0.0.0"]:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((addr, port))
                sock.close()
            
            print(f"Found available port: {port}")
            return port
        except OSError as e:
            continue
    
    # If all specific ports fail, print warning and let OS choose (port 0)
    print("WARNING: Could not find free port in range, using OS-assigned port (0)")
    return 0

if __name__ == "__main__":
    port = find_available_port()
    print(f"\nSelected port: {port}")
    print(f"Use 'set GRADIO_SERVER_PORT={port}' or '$env:GRADIO_SERVER_PORT={port}' to force this port")
