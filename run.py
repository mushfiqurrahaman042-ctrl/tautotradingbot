#!/usr/bin/env python3
"""
Trading Bot Runner
This script starts the trading bot web server that listens for webhook signals.
"""

import uvicorn
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    print("🚀 Starting Arts Trading Bot...")
    print("✅ Loading configuration...")
    
    # Get host and port from environment or use defaults
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8003"))
    
    print(f"🌐 Server starting on {host}:{port}")
    print("💡 Press Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        # Run the FastAPI application with uvicorn
        uvicorn.run(
            "main:app",  # module:app
            host=host,
            port=port,
            reload=os.getenv("RELOAD", "false").lower() == "true",  # Enable auto-reload in development
            log_level=os.getenv("LOG_LEVEL", "info"),
            workers=int(os.getenv("WORKERS", "1"))  # Number of worker processes
        )
    except KeyboardInterrupt:
        print("\n🛑 Trading bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting trading bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()