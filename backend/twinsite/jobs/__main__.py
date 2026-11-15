"""`python -m twinsite.jobs` — run the single mission worker.

  python -m twinsite.jobs                 # poll forever
  python -m twinsite.jobs --once          # process at most one run
  python -m twinsite.jobs cancel RUN_ID   # request cancellation
"""
import argparse
import logging
import signal

from twinsite.storage import Store, load_settings

from .worker import Worker


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m twinsite.jobs')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('command', nargs='?', choices=['run', 'cancel'], default='run')
    parser.add_argument('run_id', nargs='?')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s worker %(levelname)s %(message)s')
    settings = load_settings(args.data_dir)
    if args.command == 'cancel':
        if not args.run_id:
            parser.error('cancel requires RUN_ID')
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        status = Store(settings.db_path).request_cancel(args.run_id)
        print(status or 'unknown run')
        return 0 if status else 1
    worker = Worker(settings)
    if args.once:
        worker.run_once()
        return 0
    signal.signal(signal.SIGTERM, lambda *_: worker.stop_event.set())
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
