"""Disposable browser provider fixture. Not an AI model or application runtime."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from sqlalchemy.engine import make_url


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size > 32768:
            self.send_error(413)
            return
        request = json.loads(self.rfile.read(size))
        question = request["messages"][-1]["content"]
        response = {
            "message": {
                "content": json.dumps(
                    {
                        "product_query": None if question == "سلام" else question,
                        "currency": "IRR",
                    }
                )
            }
        }
        if "deliverable" in request.get("format", {}).get("properties", {}):
            context = json.loads(question)
            sources = context["sources"]
            response = {
                "message": {
                    "content": json.dumps(
                        {
                            "title": "پیش‌نویس داخلی آزمایشی (fixture)",
                            **{
                                part: {
                                    "body": {
                                        "overview": "هدف داخلی آزمایشی.",
                                        "deliverable": "تمرین و پیش‌نویس آزمایشی.",
                                        "checks": "بررسی انسانی آزمایشی.",
                                    }[part],
                                    "sources": [s["alias"] for s in sources],
                                }
                                for part in ("overview", "deliverable", "checks")
                            },
                            "evidence_quotes": [
                                {"source": s["alias"], "quote": s["content"][:80]} for s in sources
                            ],
                            "questions": ["معیار موفقیت چیست؟"],
                        }
                    )
                }
            }
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    if not make_url(os.environ["DATABASE_URL"]).database.endswith("_test"):
        raise SystemExit("Provider fixture requires a disposable _test database")
    HTTPServer(("127.0.0.1", 11435), Handler).serve_forever()
