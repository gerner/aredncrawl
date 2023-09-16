""" Python Management Interface """

import http
import http.server
import urllib.parse
import threading

class PyMXServer(http.server.HTTPServer):
    def __init__(self, get_registry, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_registry = get_registry

class PyMXHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        #TODO: parse query string
        parsed_url = urllib.parse.urlparse(self.path)
        query_args = urllib.parse.parse_qs(parsed_url.query)
        raw_result = self.server.get_registry[parsed_url.path](query_args)
        result = repr(raw_result)

        self.send_response(http.HTTPStatus.OK)
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-Length", len(result))
        self.end_headers()

        self.wfile.write(result.encode("utf8"))

class PyMX:
    def __init__(self, address="", port=8765):
        self.address = address
        self.port = port

        self.get_registry = {}

    def register_get(self, func, path):
        self.get_registry[path] = func

    def run(self):
        server = PyMXServer(self.get_registry, (self.address, self.port), PyMXHandler)
        server.serve_forever()

_pymx = PyMX()
_server_thread = None

def config(address, port):
    _pymx.address = address
    _pymx.port = port

def run():
    _pymx.run()

def start():
    _server_thread = threading.Thread(target=run, daemon=True)
    _server_thread.start()

def register_get(func, path):
    _pymx.register_get(func, path)

def pymx_get(path):
    def decorator(func):
        # TODO: allow sending back a dict or something else
        # TODO: sanity check signature of func
        # register this function as a pymx method
        _pymx.register_get(func, path)
        return func
    return decorator
