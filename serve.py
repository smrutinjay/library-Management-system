from waitress import serve
from app import app
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('waitress')

if __name__ == '__main__':
    port = 8080
    logger.info(f"Starting production server on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port)
