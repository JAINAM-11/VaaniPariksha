"""
VaaniPariksha - Application Entry Point
Run: python run.py
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app
from backend.config.settings import Config

app = create_app("development")

if __name__ == "__main__":
    print("=" * 60)
    print("  🎙  VaaniPariksha — Voice-Based Examination Platform")
    print("=" * 60)
    print(f"  ► URL: http://localhost:{Config.PORT}")
    print(f"  ► Mode: {Config.STORAGE_MODE.upper()}")
    print(f"  ► Debug: {Config.DEBUG}")
    print("=" * 60)

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )
