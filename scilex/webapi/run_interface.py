#!/usr/bin/env python
"""
SciLEx Web Interface Launcher

Run this script to start both the FastAPI backend and Streamlit frontend.
The script will open your browser automatically.

Usage:
    python run_interface.py                 # Start both API and web interface
    python run_interface.py --api-only      # Start only the FastAPI backend
    python run_interface.py --web-only      # Start only the Streamlit interface
"""

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent


def main():
    """Main runner function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Launch SciLEx web interface and/or API"
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Run only the FastAPI backend",
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Run only the Streamlit web interface",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="Port for FastAPI backend (default: 8000)",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8501,
        help="Port for Streamlit frontend (default: 8501)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind to (default: localhost)",
    )

    args = parser.parse_args()

    # Change to project root
    os.chdir(PROJECT_ROOT)

    print(
        """
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║     🚀 SciLEx Web Interface                                    ║
    ║                                                                ║
    ║     Academic Paper Collection & Analysis Platform              ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """
    )

    # Determine what to run
    run_api = not args.web_only
    run_web = not args.api_only

    processes = []

    try:
        # Start FastAPI backend
        if run_api:
            print(
                f"\n📡 Starting FastAPI backend on http://{args.host}:{args.api_port}"
            )
            print("   API Documentation: http://localhost:8000/docs")
            print("   (Press Ctrl+C to stop)\n")

            api_cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "scilex.webapi.scilex_api:app",
                "--host",
                args.host,
                "--port",
                str(args.api_port),
            ]

            api_process = subprocess.Popen(api_cmd)
            processes.append(("API", api_process))

            # Wait for API to start
            time.sleep(3)

        # Start Streamlit web interface
        if run_web:
            print(
                f"\n🌐 Starting Streamlit web interface on http://{args.host}:{args.web_port}"
            )
            print("   (Press Ctrl+C to stop)\n")

            web_cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(SCRIPT_DIR / "web_interface.py"),
                "--server.port",
                str(args.web_port),
                "--server.address",
                args.host,
            ]

            web_process = subprocess.Popen(web_cmd)
            processes.append(("Web", web_process))

        # Wait for all processes
        print("\n" + "=" * 60)
        print("✅ All services started successfully!")
        print("\n📚 SciLEx Web Interface URLs:")
        if run_api:
            print(f"   • API Backend: http://{args.host}:{args.api_port}")
            print(f"   • API Docs: http://{args.host}:{args.api_port}/docs")
        if run_web:
            print(f"   • Web Interface: http://{args.host}:{args.web_port}")
        print("\n⏹️  To stop, press Ctrl+C")
        print("=" * 60 + "\n")

        for _, process in processes:
            process.wait()

    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down...\n")
        for name, process in processes:
            print(f"Stopping {name}...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("✅ Services stopped.")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        for _, process in processes:
            process.kill()
        sys.exit(1)


if __name__ == "__main__":
    main()
