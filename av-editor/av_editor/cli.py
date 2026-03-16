from __future__ import annotations

import argparse
import sys

from .errors import AVEditorError, ConfigError, FFmpegError
from .render import render

VERSION = "0.4.0"  # matches repository CHANGELOG entry


def normalize_argv(argv: list[str]) -> list[str]:
    """Allow legacy invocation: av-editor <config> [render flags]."""
    if not argv:
        return argv

    # Keep top-level options behavior unchanged.
    if argv[0] in ('-h', '--help', '--version'):
        return argv

    known_subcommands = {'render'}
    first_non_option = next((arg for arg in argv if not arg.startswith('-')), None)
    if first_non_option is None:
        return argv

    if first_non_option in known_subcommands:
        return argv

    # Legacy form without subcommand; treat as "render".
    return ['render', *argv]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='av-editor',
        description='Multi-source timeline editor with clapboard sync',
    )
    parser.add_argument('--version', action='version', version=f'av-editor {VERSION}')

    subparsers = parser.add_subparsers(dest='command')

    render_parser = subparsers.add_parser('render', help='Render synchronized output from a config file')
    render_parser.add_argument('config', help='JSON config file')
    render_parser.add_argument('-v', '--verbose', action='store_true', help='Show ffmpeg commands and sync details')
    render_parser.add_argument('--dry-run', action='store_true', help='Show what would happen without executing')
    render_parser.add_argument('--force', action='store_true', help='Overwrite output file if it exists')

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized_argv = normalize_argv(raw_argv)

    parser = build_parser()
    args = parser.parse_args(normalized_argv)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == 'render':
            render(args.config, verbose=bool(args.verbose), dry_run=bool(args.dry_run), force=bool(args.force))
            return 0

        parser.print_help()
        return 1

    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except FFmpegError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except AVEditorError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
