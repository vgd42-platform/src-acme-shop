"""Demo vendor app: one page showing who built it, which version runs, and which
Azure blob containers it can see through its workload identity (no secrets)."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- Settings: baked into the image by the build, or injected by Kubernetes --------
VENDOR = os.getenv("VENDOR", "unknown")
APP = os.getenv("APP", "app")
VERSION = os.getenv("APP_VERSION", "0.0.0")
COMMIT = os.getenv("APP_COMMIT", "local")[:7]
NAMESPACE = os.getenv("POD_NAMESPACE", "local-dev")
ENVIRONMENT = NAMESPACE.rsplit("-", 1)[-1]
STORAGE_URL = os.getenv("STORAGE_ACCOUNT_URL", "")
PORT = int(os.getenv("PORT", "8080"))

# --- Release content the vendor edits: colour and message ------------------------
with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)


# --- JSON logs on stdout: Container Insights collects them into ContainerLogV2 ------
def log(level, msg, **fields):
    print(json.dumps({"level": level, "msg": msg, "vendor": VENDOR, "version": VERSION, **fields}), flush=True)


# --- Blob containers via workload identity, cached for 30 s ---------------------------
_cache = {"at": 0.0, "value": "not configured"}


def storage_containers():
    if not STORAGE_URL:
        return "not configured"
    if time.time() - _cache["at"] < 30:
        return _cache["value"]
    if not os.getenv("AZURE_FEDERATED_TOKEN_FILE"):  # injected by AKS workload identity
        return "no workload identity"
    try:
        from azure.identity import WorkloadIdentityCredential
        from azure.storage.blob import BlobServiceClient

        client = BlobServiceClient(STORAGE_URL, credential=WorkloadIdentityCredential(),
                                   connection_timeout=5, read_timeout=5, retry_total=1)
        value = ", ".join(c.name for c in client.list_containers()) or "(none)"
    except Exception as exc:  # show the reason on the page instead of failing
        value = f"not reachable yet ({exc.__class__.__name__})"
        log("warning", "storage check failed", error=str(exc)[:200])
    _cache.update(at=time.time(), value=value)
    return value


# --- The page --------------------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{app}</title>
<meta http-equiv="refresh" content="10"></head>
<body style="margin:0;font-family:Segoe UI,Arial,sans-serif;background:{color};color:#fff;
height:100vh;display:flex;align-items:center;justify-content:center">
<div style="background:rgba(0,0,0,.25);padding:40px 56px;border-radius:16px;min-width:480px">
<div style="font-size:18px;opacity:.85">Vendor <b>{vendor}</b> &middot; environment <b>{env}</b></div>
<h1 style="font-size:56px;margin:12px 0">{app} v{version}</h1>
<div style="font-size:20px">{message}</div>
<div style="margin-top:24px;font-size:15px;opacity:.9">commit {commit} &middot; built by the platform pipeline</div>
<div style="font-size:15px;opacity:.9">blob containers: {containers}</div>
</div></body></html>"""


# --- HTTP handler: "/" = page, "/healthz" = probe for Kubernetes ------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, "text/plain", "ok")
            return
        html = PAGE.format(app=APP, vendor=VENDOR, env=ENVIRONMENT, version=VERSION, commit=COMMIT,
                           color=CONFIG.get("color", "#444"), message=CONFIG.get("message", ""),
                           containers=storage_containers())
        self._send(200, "text/html; charset=utf-8", html)
        log("info", "page served", path=self.path)

    def _send(self, code, ctype, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence the default access log; we log JSON instead
        pass


if __name__ == "__main__":
    log("info", "starting", port=PORT, environment=ENVIRONMENT)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()  # threads: probes never wait for a slow page
