"""Server startup script."""

from ms_enclave.sandbox import create_server
from ms_enclave.utils import get_logger

logger = get_logger()


def main():
    """Run the sandbox server."""
    server = create_server(cleanup_interval=300)  # 5 minutes

    logger.info('Starting Sandbox Server...')
    logger.info('API docs: http://localhost:8000/docs')
    logger.info('Health check: http://localhost:8000/health')

    server.run(host='0.0.0.0', port=8000, log_level='info')


if __name__ == '__main__':
    main()
