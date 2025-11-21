import uvicorn
import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import create_app

if __name__ == "__main__":
    # Suppress warnings
    os.environ['PYTHONWARNINGS'] = 'ignore'
    
    app = create_app()
    print("Starting headless server on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
