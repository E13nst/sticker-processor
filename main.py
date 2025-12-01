#!/usr/bin/env python3
"""
Entry point for Amvera deployment.
This file imports the FastAPI app from the app module.
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
