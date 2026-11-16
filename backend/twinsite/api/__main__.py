"""`python -m twinsite.api` — serve the TwinSite v1 API.

Host/port from TWINSITE_API_HOST / TWINSITE_API_PORT (default 127.0.0.1:8080).
`--print-openapi` writes the OpenAPI document to stdout and exits.
"""
import argparse
import json
import logging
import signal
import threading

from .openapi import build_openapi
from .server import make_server


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m twinsite.api')
    parser.add_argument('--host')
    parser.add_argument('--port', type=int)
    parser.add_argument('--print-openapi', action='store_true')
    args = parser.parse_args(argv)
    if args.print_openapi:
        print(json.dumps(build_openapi(), indent=2, sort_keys=True, allow_nan=False))
        return 0
    logging.basicConfig(level=logging.INFO, format='%(asctime)s api %(levelname)s %(message)s')
    server = make_server(host=args.host, port=args.port)
    host, port = server.server_address[:2]
    from twinsite.ai.registry import router as _ai_router
    _r = _ai_router()
    logging.getLogger('twinsite.api').info('listening on http://%s:%s (AI-Powered Analysis %s, uploads disabled)', host, port,
                                           'available' if _r.enabled() else 'unavailable: ' + str(_r.disabled_reason()))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
