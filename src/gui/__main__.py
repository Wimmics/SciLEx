"""
SciLEx GUI entry point.
Run with: python -m src.gui
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("SCILEX_GUI_PORT", "8000"))
    host = os.getenv("SCILEX_GUI_HOST", "127.0.0.1")

    print(f"Starting SciLEx GUI on http://{host}:{port}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "src.gui.backend.main:app",
        host=host,
        port=port,
        reload=True
    )
