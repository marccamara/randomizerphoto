import ctypes
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import toga
from toga.style import Pack

from rubicon.objc import (
    ObjCClass,
    ObjCInstance,
    NSObject,
    objc_method,
)

from .processing import process_folder_advanced


# ============================================================
# PATHS / CONSTANTS
# ============================================================

HERE = Path(__file__).parent
APP_DOCS = Path.home() / "Documents"
HIST = APP_DOCS / "used_file_names.json"

EXTS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
)


# ============================================================
# GLOBAL STATE
# ============================================================

STATE = {
    "base": None,
    "dbg": None,
    "picking": False,
    "done": 0,
    "total": 0,
    "running": False,
    "finished": False,
    "error": None,
}


# ============================================================
# OBJECTIVE-C REFERENCES
# ============================================================
#
# Très important :
# on garde le delegate et l'URL native ici.
#
# Sinon Objective-C peut libérer le delegate trop tôt,
# et le callback peut ne jamais revenir correctement.
#

REFS = {
    "delegate": None,
    "picker": None,
    "security_url": None,
}


# ============================================================
# DEBUG
# ============================================================

def set_debug(message):
    """
    Petit système de debug centralisé.
    """
    try:
        STATE["dbg"] = str(message)
    except Exception:
        pass


# ============================================================
# URL / SECURITY SCOPE
# ============================================================

def _get_url_path(url):
    """
    Récupère proprement le chemin d'une NSURL Rubicon.
    """
    try:
        path = url.path
        if callable(path):
            path = path()
        if path:
            return str(path)
    except Exception:
        pass

    try:
        return str(url)
    except Exception:
        return None


def _start_security_scope(url):
    """
    Active l'accès au dossier sélectionné.

    Apple fournit une security-scoped URL lorsqu'un dossier
    externe est sélectionné.
    """
    try:
        result = url.startAccessingSecurityScopedResource()
        set_debug("Accès sécurisé activé : " + str(bool(result)))
        return bool(result)
    except Exception:
        set_debug("startAccessingSecurityScopedResource() : " + traceback.format_exc()[-300:])
        return False


def _stop_security_scope():
    """
    Libère l'accès au dossier précédent.
    """
    url = REFS.get("security_url")
    if url is None:
        return

    try:
        url.stopAccessingSecurityScopedResource()
    except Exception:
        pass

    REFS["security_url"] = None


# ============================================================
# DOCUMENT PICKER DELEGATE
# ============================================================

class PickerDelegate(NSObject):

    # --------------------------------------------------------
    # DOSSIER SÉLECTIONNÉ
    # --------------------------------------------------------

    @objc_method
    def documentPicker_didPickDocumentsAtURLs_(self, picker, urls):
        try:
            STATE["picking"] = False
            STATE["error"] = None

            if not urls:
                set_debug("Aucun dossier retourné par iOS.")
                return

            # Premier dossier puisque allowsMultipleSelection = False
            url = urls[0]
            set_debug("Callback reçu.\nURL : " + str(url))

            # Libérer éventuellement l'ancien accès
            _stop_security_scope()

            # Garder la NSURL native en mémoire
            REFS["security_url"] = url

            # Demander l'accès sécurisé
            access_ok = _start_security_scope(url)

            if not access_ok:
                STATE["error"] = "iOS n'a pas accordé l'accès au dossier."
                STATE["base"] = None
                return

            # Récupérer le chemin réel
            path = _get_url_path(url)
            if not path:
                STATE["error"] = "Impossible de récupérer le chemin du dossier."
                STATE["base"] = None
                return

            base = Path(path)

            # Vérification supplémentaire
            if not base.exists():
                STATE["error"] = "Le dossier sélectionné n'existe pas."
                STATE["base"] = None
                return

            if not base.is_dir():
                STATE["error"] = "L'élément sélectionné n'est pas un dossier."
                STATE["base"] = None
                return

            # Tout est OK
            STATE["base"] = str(base)
            STATE["dbg"] = "DOSSIER OK : " + str(base)
            print("[RandomizerPhoto] Dossier sélectionné :", base)

        except Exception:
            STATE["base"] = None
            STATE["error"] = "Erreur lors de la sélection du dossier."
            STATE["dbg"] = traceback.format_exc()[-1000:]
            print(traceback.format_exc())

        finally:
            STATE["picking"] = False
            # On garde volontairement le security scope actif.
            # Il sera libéré après le traitement dans _run().
            # Ceci est important car processing.py doit pouvoir
            # lire et créer des fichiers dans le dossier sélectionné.

    # --------------------------------------------------------
    # ANNULATION
    # --------------------------------------------------------

    @objc_method
    def documentPickerWasCancelled_(self, picker):
        STATE["picking"] = False
        set_debug("Sélection du dossier annulée.")
        print("[RandomizerPhoto] Picker annulé.")


# ============================================================
# VIEW CONTROLLER
# ============================================================

def _get_top_view_controller(root):
    """
    Trouve le UIViewController actuellement visible.

    Cela rend la présentation du picker plus robuste si Toga
    utilise plusieurs niveaux de controllers.
    """
    current = root
    try:
        while True:
            # UINavigationController
            presented = getattr(current, "presentedViewController", None)
            if presented:
                current = presented
                continue

            # UITabBarController
            selected = getattr(current, "selectedViewController", None)
            if selected:
                current = selected
                continue

            # UINavigationController visible VC
            visible = getattr(current, "visibleViewController", None)
            if visible:
                current = visible
                continue

            break
    except Exception:
        pass

    return current


# ============================================================
# CRÉATION DU PICKER
# ============================================================

def _create_folder_picker():
    """
    Crée automatiquement le meilleur UIDocumentPicker
    disponible sur la version iOS actuelle.

    Ordre :
        1. API moderne + UTType.folder
        2. API moderne avec public.folder
        3. API legacy avec public.folder

    Cela permet à l'application d'être beaucoup plus tolérante
    entre différentes versions d'iOS.
    """
    Picker = ObjCClass("UIDocumentPickerViewController")

    # --------------------------------------------------------
    # MÉTHODE 1
    # --------------------------------------------------------
    # iOS moderne :
    # UIDocumentPickerViewController(forOpeningContentTypes: [.folder])
    # Apple recommande cette API.
    # --------------------------------------------------------
    try:
        UTType = ObjCClass("UTType")
        try:
            folder_type = UTType.typeWithIdentifier_("public.folder")
        except Exception:
            folder_type = UTType.typeWithIdentifier("public.folder")

        if folder_type:
            try:
                picker = Picker.alloc().initForOpeningContentTypes_([folder_type])
                if picker:
                    set_debug("Picker moderne UTType.folder")
                    return picker
            except Exception as e:
                print("[Picker] API moderne 1 échouée:", e)
    except Exception as e:
        print("[Picker] UTType indisponible:", e)

    # --------------------------------------------------------
    # MÉTHODE 2
    # --------------------------------------------------------
    # Certaines versions/bridges Rubicon peuvent préférer
    # la syntaxe keyword.
    # --------------------------------------------------------
    try:
        UTType = ObjCClass("UTType")
        try:
            folder_type = UTType.typeWithIdentifier_("public.folder")
        except Exception:
            folder_type = UTType.typeWithIdentifier("public.folder")

        if folder_type:
            try:
                picker = Picker.alloc().initForOpeningContentTypes([folder_type])
                if picker:
                    set_debug("Picker moderne UTType.folder (fallback)")
                    return picker
            except Exception as e:
                print("[Picker] API moderne 2 échouée:", e)
    except Exception:
        pass

    # --------------------------------------------------------
    # MÉTHODE 3
    # --------------------------------------------------------
    # Ancienne API : initWithDocumentTypes:inMode:
    # On utilise public.folder.
    # Cette API est dépréciée sur les iOS récents mais permet
    # un fallback pour les anciens environnements.
    # --------------------------------------------------------
    try:
        picker = Picker.alloc().initWithDocumentTypes_inMode_(
            ["public.folder"],
            1,  # UIDocumentPickerModeOpen
        )
        if picker:
            set_debug("Picker legacy public.folder")
            return picker
    except Exception as e:
        print("[Picker] API legacy échouée:", e)

    # --------------------------------------------------------
    # DERNIER ESSAI : syntaxe keyword
    # --------------------------------------------------------
    try:
        picker = Picker.alloc().initWithDocumentTypes(
            ["public.folder"],
            inMode=1,
        )
        if picker:
            set_debug("Picker legacy public.folder (fallback)")
            return picker
    except Exception as e:
        print("[Picker] Dernier fallback échoué:", e)

    raise RuntimeError("Impossible de créer le sélecteur de dossier iOS.")


# ============================================================
# PRESENTATION DU PICKER
# ============================================================

def _present_picker(app):
    try:
        STATE["picking"] = True
        STATE["error"] = None
        STATE["dbg"] = "Ouverture du sélecteur de dossier..."

        # Création automatique
        picker = _create_folder_picker()

        # Delegate
        delegate = PickerDelegate.alloc().init()

        # Très important : conserver une référence Python forte.
        REFS["delegate"] = delegate
        REFS["picker"] = picker
        picker.delegate = delegate
        picker.allowsMultipleSelection = False

        # Trouver le controller Toga
        native_window = app.main_window._impl.native
        window = ObjCInstance(native_window)
        root = window.rootViewController

        if root is None:
            raise RuntimeError("rootViewController introuvable.")

        controller = _get_top_view_controller(root)
        if controller is None:
            raise RuntimeError("ViewController actif introuvable.")

        # Présentation
        controller.presentViewController(
            picker,
            animated=True,
            completion=None,
        )

        set_debug("Sélecteur ouvert. Navigue jusqu'au dossier puis appuie sur « Ouvrir ».")
        print("[RandomizerPhoto] Folder picker ouvert.")

    except Exception:
        STATE["picking"] = False
        STATE["error"] = "Impossible d'ouvrir le sélecteur de dossier."
        STATE["dbg"] = traceback.format_exc()[-1000:]
        print(traceback.format_exc())


# ============================================================
# IMAGE COUNT
# ============================================================

def _count_images(base):
    try:
        return sum(
            1
            for f in Path(base).iterdir()
            if f.suffix.lower() in EXTS
        )
    except Exception:
        return 0


# ============================================================
# PROGRESS
# ============================================================

def _progress(done, total):
    STATE.update(
        done=done,
        total=total,
    )


# ============================================================
# PROCESSING
# ============================================================

def _run(n, model):
    STATE.update(
        done=0,
        total=0,
        running=True,
        finished=False,
        error=None,
    )

    try:
        if not STATE["base"]:
            raise RuntimeError("Aucun dossier sélectionné.")

        base = Path(STATE["base"])

        if not base.exists():
            raise RuntimeError("Le dossier sélectionné n'est plus accessible.")

        if not base.is_dir():
            raise RuntimeError("Le chemin sélectionné n'est pas un dossier.")

        # Dossier de sortie
        out = base / "photos_traitees"
        out.mkdir(exist_ok=True)

        # Traitement
        process_folder_advanced(
            str(base),
            str(out),
            n,
            str(HIST),
            _progress,
            model,
        )

    except Exception as e:
        STATE["error"] = str(e)
        STATE["dbg"] = traceback.format_exc()[-1000:]
        print(traceback.format_exc())

    finally:
        STATE.update(
            running=False,
            finished=True,
        )

        # IMPORTANT
        # Maintenant que processing.py a terminé,
        # on peut libérer l'accès security-scoped.
        _stop_security_scope()

        REFS["picker"] = None
        REFS["delegate"] = None


# ============================================================
# HTTP SERVER
# ============================================================

def make_handler(app):

    class Handler(BaseHTTPRequestHandler):

        # Désactive les logs HTTP
        def log_message(self, *args):
            pass

        # SEND
        def _send(
            self,
            code=200,
            body=b"{}",
            ctype="application/json",
        ):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # GET
        def do_GET(self):
            p = urlparse(self.path).path

            # HTML
            if p == "/":
                self._send(
                    200,
                    (HERE / "index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
                return

            # STATE
            if p == "/state":
                s = dict(STATE)
                base = STATE["base"]

                if base:
                    s["count"] = _count_images(base)
                    try:
                        s["name"] = Path(base).name
                    except Exception:
                        s["name"] = None
                else:
                    s["count"] = 0
                    s["name"] = None

                self._send(
                    200,
                    json.dumps(s).encode(),
                )
                return

            # 404
            self._send(404)

        # POST
        def do_POST(self):
            u = urlparse(self.path)

            # PICK
            if u.path == "/pick":
                if STATE["picking"]:
                    self._send(
                        409,
                        json.dumps({
                            "error": "Picker déjà ouvert."
                        }).encode(),
                    )
                    return

                STATE["picking"] = True

                # Toujours présenter le picker sur le thread principal iOS.
                app.loop.call_soon_threadsafe(
                    _present_picker,
                    app,
                )

                self._send()
                return

            # RUN
            if u.path == "/run":
                q = parse_qs(u.query)

                try:
                    n = int(q.get("n", ["10"])[0])
                except Exception:
                    n = 10

                model = q.get("model", ["Mix"])[0]

                if (
                    STATE["base"]
                    and not STATE["running"]
                    and not STATE["picking"]
                ):
                    threading.Thread(
                        target=_run,
                        args=(
                            n,
                            model,
                        ),
                        daemon=True,
                    ).start()

                self._send()
                return

            # 404
            self._send(404)

    return Handler


# ============================================================
# TOGA APPLICATION
# ============================================================

class RandomizerPhoto(toga.App):

    def startup(self):
        # Documents directory
        APP_DOCS.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Local HTTP server
        server = ThreadingHTTPServer(
            (
                "127.0.0.1",
                0,
            ),
            make_handler(self),
        )

        threading.Thread(
            target=server.serve_forever,
            daemon=True,
        ).start()

        port = server.server_address[1]

        # Toga window
        self.main_window = toga.MainWindow(
            title=self.formal_name
        )

        # WebView
        self.main_window.content = toga.WebView(
            url=f"http://127.0.0.1:{port}/",
            style=Pack(
                flex=1
            ),
        )

        # Show
        self.main_window.show()


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    return RandomizerPhoto(
        "RandomizerPhoto",
        "com.perso.randomizerphoto",
    )
