import ctypes
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import toga
from toga.style import Pack
from rubicon.objc import ObjCClass, ObjCInstance, NSObject, objc_method

from .processing import process_folder_advanced

HERE = Path(__file__).parent
APP_DOCS = Path.home() / "Documents"          # historique des noms (interne à l'app)
HIST = APP_DOCS / "used_file_names.json"
EXTS = (".jpg", ".jpeg", ".png", ".webp")

STATE = {"base": None, "dbg": None, "picking": False, "done": 0, "total": 0,
         "running": False, "finished": False, "error": None}
REFS = {}  # garde les objets natifs en vie


# ---------- Sélecteur de dossier natif ----------
class PickerDelegate(NSObject):
    @objc_method
    def documentPicker_didPickDocumentsAtURLs_(self, picker, urls):
        try:
            url = urls[0]
            url.startAccessingSecurityScopedResource()
            STATE["base"] = str(url.path)
            STATE["dbg"] = None
        except Exception:
            STATE["dbg"] = traceback.format_exc()[-300:]
        STATE["picking"] = False

    @objc_method
    def documentPickerWasCancelled_(self, picker):
        STATE["picking"] = False


def _present_picker(app):
    try:
        Picker = ObjCClass("UIDocumentPickerViewController")
        try:
            # API moderne (iOS 14+)
            ctypes.CDLL("/System/Library/Frameworks/UniformTypeIdentifiers.framework/UniformTypeIdentifiers")
            folder = ObjCClass("UTType").typeWithIdentifier("public.folder")
            picker = Picker.alloc().initForOpeningContentTypes([folder])
        except Exception:
            # ancienne API
            picker = Picker.alloc().initWithDocumentTypes(["public.folder"], inMode=1)
        delegate = PickerDelegate.alloc().init()
        REFS["delegate"] = delegate
        picker.delegate = delegate
        picker.allowsMultipleSelection = False
        root = ObjCInstance(app.main_window._impl.native).rootViewController
        root.presentViewController(picker, animated=True, completion=None)
    except Exception:
        STATE["dbg"] = traceback.format_exc()[-300:]


# ---------- Traitement ----------
def _count_images(base):
    try:
        return sum(1 for f in Path(base).iterdir() if f.suffix.lower() in EXTS)
    except Exception:
        return 0


def _progress(done, total):
    STATE.update(done=done, total=total)


def _run(n, model):
    STATE.update(done=0, total=0, running=True, finished=False, error=None)
    try:
        base = Path(STATE["base"])
        out = base / "photos_traitees"
        out.mkdir(exist_ok=True)
        process_folder_advanced(str(base), str(out), n, str(HIST), _progress, model)
    except Exception as e:
        STATE["error"] = str(e)
    finally:
        STATE.update(running=False, finished=True)


# ---------- Mini serveur local pour l'interface ----------
def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code=200, body=b"{}", ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = urlparse(self.path).path
            if p == "/":
                self._send(200, (HERE / "index.html").read_bytes(),
                           "text/html; charset=utf-8")
            elif p == "/state":
                s = dict(STATE)
                s["count"] = _count_images(STATE["base"]) if STATE["base"] else 0
                s["name"] = Path(STATE["base"]).name if STATE["base"] else None
                self._send(200, json.dumps(s).encode())
            else:
                self._send(404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/pick":
                STATE["picking"] = True
                app.loop.call_soon_threadsafe(_present_picker, app)  # thread principal
                self._send()
            elif u.path == "/run":
                q = parse_qs(u.query)
                n = int(q.get("n", ["10"])[0])
                model = q.get("model", ["Mix"])[0]
                if STATE["base"] and not STATE["running"]:
                    threading.Thread(target=_run, args=(n, model), daemon=True).start()
                self._send()
            else:
                self._send(404)
    return Handler


class RandomizerPhoto(toga.App):
    def startup(self):
        APP_DOCS.mkdir(parents=True, exist_ok=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = toga.WebView(
            url=f"http://127.0.0.1:{port}/", style=Pack(flex=1)
        )
        self.main_window.show()


def main():
    return RandomizerPhoto("RandomizerPhoto", "com.perso.randomizerphoto")
