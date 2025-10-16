# Copyright (c) Alibaba, Inc. and its affiliates.
from argparse import ArgumentParser
from typing import Optional

from ms_enclave.cli.base import CLICommand
from ms_enclave.sandbox import create_server
from ms_enclave.utils import get_logger

logger = get_logger()


def subparser_func(args):
    """ Function which will be called for a specific sub parser.
    """
    return ServerCMD(args)


class ServerCMD(CLICommand):
    name = 'server'

    def __init__(self, args):
        self.args = args

    @staticmethod
    def define_args(parsers: ArgumentParser):
        """Define args for the server command.
        """
        parser = parsers.add_parser(ServerCMD.name, help='Start the MS-Enclave sandbox HTTP server')
        add_argument(parser)
        parser.set_defaults(func=subparser_func)

    def execute(self):
        """Start the sandbox server using provided CLI arguments."""
        cleanup_interval: int = getattr(self.args, 'cleanup_interval', 300)
        host: str = getattr(self.args, 'host', '0.0.0.0')
        port: int = getattr(self.args, 'port', 8000)
        log_level: str = getattr(self.args, 'log_level', 'info')
        api_key: Optional[str] = getattr(self.args, 'api_key', None)

        server = create_server(cleanup_interval=cleanup_interval, api_key=api_key)

        logger.info('Starting Sandbox Server...')
        logger.info('API docs: http://%s:%d/docs', host, port)
        logger.info('Health check: http://%s:%d/health', host, port)

        try:
            server.run(host=host, port=port, log_level=log_level)
        except KeyboardInterrupt:
            logger.info('Server interrupted by user, shutting down...')
        except Exception as e:  # pragma: no cover - runtime dependent
            logger.error('Failed to start server: %s', e)
            raise


def add_argument(parser: ArgumentParser) -> None:
    """Register command line arguments for the server command.

    Args:
        parser: The argparse parser to add arguments to.
    """
    parser.add_argument(
        '--host', type=str, default='0.0.0.0', help='Host interface to bind the server (default: 0.0.0.0)'
    )
    parser.add_argument('--port', type=int, default=8000, help='Port for the HTTP server (default: 8000)')
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['critical', 'error', 'warning', 'info', 'debug'],
        default='info',
        help='Log level for the server (default: info)'
    )
    parser.add_argument(
        '--cleanup-interval',
        type=int,
        default=300,
        metavar='SECONDS',
        help='Background cleanup interval in seconds (default: 300)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='Optional API key to protect endpoints. If omitted, no authentication is enforced.'
    )
