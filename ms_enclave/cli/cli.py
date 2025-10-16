# Copyright (c) Alibaba, Inc. and its affiliates.

import argparse

from ms_enclave import __version__
from ms_enclave.cli.start_server import ServerCMD


def run_cmd():
    parser = argparse.ArgumentParser('MS-Enclave Command Line tool', usage='ms-enclave <command> [<args>]')
    parser.add_argument('-v', '--version', action='version', version=f'ms-enclave {__version__}')
    subparsers = parser.add_subparsers(help='MS-Enclave command line helper.')

    ServerCMD.define_args(subparsers)

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        exit(1)

    cmd = args.func(args)
    cmd.execute()


if __name__ == '__main__':
    run_cmd()
