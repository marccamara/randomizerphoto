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
    ObjCProtocol,
    NSObject,
    objc_method,
)

from .processing import process_folder_advanced


# ============================================================
# PATHS
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
    "dbg": "Application démarrée.",
    "picking": False,
    "done": 0,
    "total": 0,
    "running": False,
    "finished": False,
    "error": None,
}


# ============================================================
# NATIVE REFERENCES
# ============================================================
#
# IMPORTANT :
# On garde ici des références fortes vers le picker et son
# delegate.
#
# Cela évite qu'Objective-C/Python libère le delegate avant
# que iOS ait eu le temps d'appeler le callback.
# ============================================================

REFS = {
    "picker": None,
    "delegate": None,
    "security_url": None,
}


# ============================================================
# DEBUG
# ============================================================

def set_debug(message):
    """
    Met à jour le message de diagnostic.
    """

    try:
        STATE["dbg"] = str(message)
    except Exception:
        pass


# ============================================================
# SECURITY SCOPED RESOURCE
# ============================================================

def stop_security_scope():
    """
    Libère l'accès au dossier précédemment sélectionné.
    """

    url = REFS.get("security_url")

    if url is None:
        return

    try:
        url.stopAccessingSecurityScopedResource()
        print(
            "[RandomizerPhoto] Security scope libéré."
        )
    except Exception as e:
        print(
            "[RandomizerPhoto] Impossible de libérer "
            "le security scope :",
            e,
        )

    REFS["security_url"] = None


# ============================================================
# DOCUMENT PICKER DELEGATE
# ============================================================

try:
    UIDocumentPickerDelegate = ObjCProtocol(
        "UIDocumentPickerDelegate"
    )
except Exception:
    UIDocumentPickerDelegate = None


if UIDocumentPickerDelegate is not None:

    class PickerDelegate(
        NSObject,
        protocols=[UIDocumentPickerDelegate],
    ):
        pass

else:

    class PickerDelegate(
        NSObject,
    ):
        pass


# ============================================================
# CALLBACK : DOSSIER SÉLECTIONNÉ
# ============================================================

@objc_method
def _document_picker_did_pick(
    self,
    picker,
    urls,
):
    """
    Callback Objective-C :

        documentPicker:didPickDocumentsAtURLs:

    C'est LE callback que nous voulons tester.
    """

    try:

        print("")
        print("========================================")
        print("📁 CALLBACK DOCUMENT PICKER REÇU")
        print("========================================")

        STATE["picking"] = False
        STATE["error"] = None

        set_debug(
            "CALLBACK REÇU par Python."
        )

        # ----------------------------------------------------
        # Vérifier les URLs
        # ----------------------------------------------------

        if not urls:

            print(
                "❌ iOS a retourné 0 URL."
            )

            set_debug(
                "CALLBACK REÇU MAIS 0 URL."
            )

            STATE["base"] = None

            return

        print(
            "Nombre d'URL :",
            len(urls),
        )

        # Comme allowsMultipleSelection = False,
        # nous utilisons la première.
        url = urls[0]

        print(
            "URL native :",
            url,
        )

        set_debug(
            "URL reçue : " + str(url)
        )

        # ----------------------------------------------------
        # Libérer ancien security scope
        # ----------------------------------------------------

        stop_security_scope()

        # ----------------------------------------------------
        # Conserver l'URL native
        # ----------------------------------------------------

        REFS["security_url"] = url

        # ----------------------------------------------------
        # Security scoped access
        # ----------------------------------------------------

        try:

            access = (
                url.startAccessingSecurityScopedResource()
            )

            print(
                "Security scope :",
                access,
            )

            if access:

                set_debug(
                    "URL reçue + accès sécurisé OK."
                )

            else:

                set_debug(
                    "URL reçue mais accès sécurisé = False."
                )

        except Exception as e:

            print(
                "❌ Erreur security scope :",
                e,
            )

            set_debug(
                "ERREUR security scope : "
                + str(e)
            )

        # ----------------------------------------------------
        # Récupérer le chemin
        # ----------------------------------------------------

        try:

            path = url.path

            if callable(path):
                path = path()

            path = str(path)

        except Exception:

            path = None

        print(
            "PATH :",
            path,
        )

        if not path:

            STATE["base"] = None

            STATE["error"] = (
                "Impossible de récupérer "
                "le chemin du dossier."
            )

            set_debug(
                "❌ URL reçue mais path introuvable."
            )

            return

        # ----------------------------------------------------
        # Pathlib
        # ----------------------------------------------------

        base = Path(path)

        # ----------------------------------------------------
        # Vérification existence
        # ----------------------------------------------------

        if not base.exists():

            STATE["base"] = None

            STATE["error"] = (
                "Le dossier sélectionné "
                "n'existe pas."
            )

            set_debug(
                "❌ Dossier inexistant : "
                + str(base)
            )

            return

        # ----------------------------------------------------
        # Vérification dossier
        # ----------------------------------------------------

        if not base.is_dir():

            STATE["base"] = None

            STATE["error"] = (
                "L'élément sélectionné "
                "n'est pas un dossier."
            )

            set_debug(
                "❌ L'élément n'est pas un dossier."
            )

            return

        # ----------------------------------------------------
        # SUCCÈS
        # ----------------------------------------------------

        STATE["base"] = str(base)

        STATE["error"] = None

        try:

            count = sum(
                1
                for f in base.iterdir()
                if f.suffix.lower() in EXTS
            )

        except Exception:

            count = 0

        STATE["dbg"] = (
            "✅ DOSSIER SÉLECTIONNÉ : "
            + str(base)
            + " | Images : "
            + str(count)
        )

        print("")
        print("========================================")
        print("✅ DOSSIER SÉLECTIONNÉ")
        print("========================================")
        print("PATH :", base)
        print("IMAGES :", count)
        print("========================================")
        print("")

    except Exception:

        STATE["base"] = None

        STATE["picking"] = False

        STATE["error"] = (
            "Erreur dans le callback du picker."
        )

        STATE["dbg"] = (
            "❌ EXCEPTION CALLBACK\n\n"
            + traceback.format_exc()[-1500:]
        )

        print("")
        print(
            traceback.format_exc()
        )
        print("")

    finally:

        STATE["picking"] = False


# ============================================================
# CALLBACK : ANNULATION
# ============================================================

@objc_method
def _document_picker_cancelled(
    self,
    picker,
):
    """
    Callback Objective-C :

        documentPickerWasCancelled:
    """

    STATE["picking"] = False

    STATE["error"] = None

    STATE["dbg"] = (
        "Sélection du dossier annulée."
    )

    print(
        "[RandomizerPhoto] Picker annulé."
    )


# ============================================================
# ATTACHER LES MÉTHODES AU DELEGATE
# ============================================================

PickerDelegate.documentPicker_didPickDocumentsAtURLs_ = (
    _document_picker_did_pick
)

PickerDelegate.documentPickerWasCancelled_ = (
    _document_picker_cancelled
)


# ============================================================
# CREATE FOLDER PICKER
# ============================================================

def create_folder_picker():
    """
    Crée le UIDocumentPicker configuré pour les dossiers.

    Pour notre test nous utilisons volontairement l'API
    moderne iOS.

    Le type public.folder signifie :
        "je veux sélectionner un dossier"
    """

    print("")
    print("========================================")
    print("📂 CRÉATION DU FOLDER PICKER")
    print("========================================")

    Picker = ObjCClass(
        "UIDocumentPickerViewController"
    )

    UTType = ObjCClass(
        "UTType"
    )

    # --------------------------------------------------------
    # UTType.folder
    # --------------------------------------------------------

    try:

        folder_type = (
            UTType.typeWithIdentifier_(
                "public.folder"
            )
        )

    except Exception:

        # Fallback Rubicon
        folder_type = (
            UTType.typeWithIdentifier(
                "public.folder"
            )
        )

    if folder_type is None:

        raise RuntimeError(
            "UTType public.folder introuvable."
        )

    print(
        "UTType.folder OK"
    )

    # --------------------------------------------------------
    # API moderne
    # --------------------------------------------------------
    #
    # Objective-C :
    #
    # initForOpeningContentTypes:asCopy:
    #
    # Python/Rubicon :
    #
    # initForOpeningContentTypes_asCopy_
    #
    # --------------------------------------------------------

    try:

        picker = (
            Picker.alloc()
            .initForOpeningContentTypes_asCopy_(
                [folder_type],
                False,
            )
        )

    except Exception as e:

        print(
            "API moderne asCopy échouée :",
            e,
        )

        # ----------------------------------------------------
        # Fallback moderne sans asCopy
        # ----------------------------------------------------

        picker = (
            Picker.alloc()
            .initForOpeningContentTypes_(
                [folder_type]
            )
        )

    if picker is None:

        raise RuntimeError(
            "UIDocumentPickerViewController "
            "n'a pas pu être créé."
        )

    print(
        "✅ UIDocumentPicker créé."
    )

    return picker


# ============================================================
# PRESENT PICKER
# ============================================================

def present_picker(app):
    """
    Présente le UIDocumentPicker depuis le ViewController
    principal de Toga.
    """

    try:

        STATE["picking"] = True
        STATE["error"] = None

        set_debug(
            "Création du sélecteur de dossier..."
        )

        # ----------------------------------------------------
        # Créer picker
        # ----------------------------------------------------

        picker = create_folder_picker()

        # ----------------------------------------------------
        # Créer delegate
        # ----------------------------------------------------

        delegate = (
            PickerDelegate.alloc().init()
        )

        if delegate is None:

            raise RuntimeError(
                "Impossible de créer "
                "PickerDelegate."
            )

        # ----------------------------------------------------
        # CONSERVER LES RÉFÉRENCES
        # ----------------------------------------------------

        REFS["picker"] = picker

        REFS["delegate"] = delegate

        # ----------------------------------------------------
        # Delegate
        # ----------------------------------------------------

        picker.delegate = delegate

        # Un seul dossier
        picker.allowsMultipleSelection = False

        print(
            "Delegate attaché."
        )

        # ----------------------------------------------------
        # Récupérer fenêtre native Toga
        # ----------------------------------------------------

        native_window = (
            app.main_window
            ._impl
            .native
        )

        window = ObjCInstance(
            native_window
        )

        # ----------------------------------------------------
        # Root ViewController
        # ----------------------------------------------------

        root = (
            window.rootViewController
        )

        if root is None:

            raise RuntimeError(
                "rootViewController introuvable."
            )

        print(
            "Root ViewController OK."
        )

        # ----------------------------------------------------
        # Présenter
        # ----------------------------------------------------

        root.presentViewController(
            picker,
            animated=True,
            completion=None,
        )

        print(
            "✅ PICKER AFFICHÉ."
        )

        print(
            "➡️ Entre dans le dossier puis appuie "
            "sur Ouvrir."
        )

        set_debug(
            "Picker ouvert. "
            "Entre dans le dossier puis appuie sur « Ouvrir »."
        )

    except Exception:

        STATE["picking"] = False

        STATE["error"] = (
            "Impossible d'ouvrir "
            "le sélecteur de dossier."
        )

        STATE["dbg"] = (
            "❌ ERREUR PICKER\n\n"
            + traceback.format_exc()[-1500:]
        )

        print("")
        print(
            traceback.format_exc()
        )
        print("")


# ============================================================
# COUNT IMAGES
# ============================================================

def count_images(base):

    if not base:
        return 0

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

def progress(done, total):

    STATE.update(
        done=done,
        total=total,
    )


# ============================================================
# RUN PROCESSING
# ============================================================

def run_processing(
    n,
    model,
):

    STATE.update(
        done=0,
        total=0,
        running=True,
        finished=False,
        error=None,
    )

    try:

        # ----------------------------------------------------
        # Vérification dossier
        # ----------------------------------------------------

        if not STATE["base"]:

            raise RuntimeError(
                "Aucun dossier sélectionné."
            )

        base = Path(
            STATE["base"]
        )

        if not base.exists():

            raise RuntimeError(
                "Le dossier sélectionné "
                "n'est plus accessible."
            )

        if not base.is_dir():

            raise RuntimeError(
                "Le chemin sélectionné "
                "n'est pas un dossier."
            )

        # ----------------------------------------------------
        # Output
        # ----------------------------------------------------

        out = (
            base
            / "photos_traitees"
        )

        out.mkdir(
            exist_ok=True
        )

        # ----------------------------------------------------
        # Processing
        # ----------------------------------------------------

        print("")
        print("========================================")
        print("🚀 TRAITEMENT")
        print("========================================")
        print("SOURCE :", base)
        print("OUTPUT :", out)
        print("MODEL  :", model)
        print("N      :", n)
        print("========================================")

        process_folder_advanced(
            str(base),
            str(out),
            n,
            str(HIST),
            progress,
            model,
        )

    except Exception as e:

        STATE["error"] = str(e)

        STATE["dbg"] = (
            "❌ ERREUR TRAITEMENT\n\n"
            + traceback.format_exc()[-1500:]
        )

        print("")
        print(
            traceback.format_exc()
        )
        print("")

    finally:

        STATE.update(
            running=False,
            finished=True,
        )

        # ----------------------------------------------------
        # Libérer security scope
        # ----------------------------------------------------

        stop_security_scope()

        # ----------------------------------------------------
        # Libérer références picker
        # ----------------------------------------------------

        REFS["picker"] = None
        REFS["delegate"] = None


# ============================================================
# HTTP SERVER
# ============================================================

def make_handler(app):

    class Handler(
        BaseHTTPRequestHandler
    ):

        # ----------------------------------------------------
        # Pas de logs HTTP
        # ----------------------------------------------------

        def log_message(
            self,
            *args,
        ):
            pass


        # ----------------------------------------------------
        # SEND
        # ----------------------------------------------------

        def send_json(
            self,
            code=200,
            data=None,
        ):

            if data is None:
                data = {}

            body = json.dumps(
                data
            ).encode(
                "utf-8"
            )

            self.send_response(
                code
            )

            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )

            self.send_header(
                "Content-Length",
                str(len(body)),
            )

            self.end_headers()

            self.wfile.write(
                body
            )


        # ----------------------------------------------------
        # GET
        # ----------------------------------------------------

        def do_GET(self):

            parsed = urlparse(
                self.path
            )

            path = parsed.path

            # -----------------------------------------------
            # HTML
            # -----------------------------------------------

            if path == "/":

                try:

                    body = (
                        HERE
                        / "index.html"
                    ).read_bytes()

                    self.send_response(
                        200
                    )

                    self.send_header(
                        "Content-Type",
                        "text/html; charset=utf-8",
                    )

                    self.send_header(
                        "Content-Length",
                        str(len(body)),
                    )

                    self.end_headers()

                    self.wfile.write(
                        body
                    )

                except Exception:

                    self.send_json(
                        500,
                        {
                            "error":
                                traceback.format_exc()
                        },
                    )

                return

            # -----------------------------------------------
            # STATE
            # -----------------------------------------------

            if path == "/state":

                state = dict(
                    STATE
                )

                base = STATE.get(
                    "base"
                )

                if base:

                    state["count"] = (
                        count_images(
                            base
                        )
                    )

                    try:

                        state["name"] = (
                            Path(base).name
                        )

                    except Exception:

                        state["name"] = None

                else:

                    state["count"] = 0
                    state["name"] = None

                self.send_json(
                    200,
                    state,
                )

                return

            # -----------------------------------------------
            # 404
            # -----------------------------------------------

            self.send_json(
                404,
                {
                    "error": "Not found"
                },
            )


        # ----------------------------------------------------
        # POST
        # ----------------------------------------------------

        def do_POST(self):

            parsed = urlparse(
                self.path
            )

            path = parsed.path

            # -----------------------------------------------
            # PICK
            # -----------------------------------------------

            if path == "/pick":

                if STATE["picking"]:

                    self.send_json(
                        409,
                        {
                            "error":
                                "Picker déjà ouvert."
                        },
                    )

                    return

                STATE["picking"] = True

                STATE["error"] = None

                set_debug(
                    "Demande de sélection du dossier..."
                )

                # IMPORTANT :
                # UIKit doit être manipulé sur le thread
                # principal.
                app.loop.call_soon_threadsafe(
                    present_picker,
                    app,
                )

                self.send_json(
                    200,
                    {
                        "ok": True
                    },
                )

                return

            # -----------------------------------------------
            # RUN
            # -----------------------------------------------

            if path == "/run":

                query = parse_qs(
                    parsed.query
                )

                try:

                    n = int(
                        query.get(
                            "n",
                            ["10"],
                        )[0]
                    )

                except Exception:

                    n = 10

                model = query.get(
                    "model",
                    ["Mix"],
                )[0]

                if (
                    STATE["base"]
                    and not STATE["running"]
                    and not STATE["picking"]
                ):

                    threading.Thread(
                        target=run_processing,
                        args=(
                            n,
                            model,
                        ),
                        daemon=True,
                    ).start()

                self.send_json(
                    200,
                    {
                        "ok": True
                    },
                )

                return

            # -----------------------------------------------
            # 404
            # -----------------------------------------------

            self.send_json(
                404,
                {
                    "error": "Not found"
                },
            )

    return Handler


# ============================================================
# TOGA APP
# ============================================================

class RandomizerPhoto(
    toga.App
):

    def startup(self):

        # ----------------------------------------------------
        # Documents
        # ----------------------------------------------------

        APP_DOCS.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # Local HTTP server
        # ----------------------------------------------------

        server = ThreadingHTTPServer(
            (
                "127.0.0.1",
                0,
            ),
            make_handler(
                self
            ),
        )

        threading.Thread(
            target=server.serve_forever,
            daemon=True,
        ).start()

        port = (
            server.server_address[1]
        )

        print(
            "[RandomizerPhoto] HTTP server :",
            port,
        )

        # ----------------------------------------------------
        # Toga window
        # ----------------------------------------------------

        self.main_window = (
            toga.MainWindow(
                title=self.formal_name
            )
        )

        # ----------------------------------------------------
        # WebView
        # ----------------------------------------------------

        self.main_window.content = (
            toga.WebView(
                url=(
                    f"http://127.0.0.1:{port}/"
                ),
                style=Pack(
                    flex=1
                ),
            )
        )

        # ----------------------------------------------------
        # Show
        # ----------------------------------------------------

        self.main_window.show()

        print(
            "[RandomizerPhoto] Application prête."
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    return RandomizerPhoto(
        "RandomizerPhoto",
        "com.perso.randomizerphoto",
    )
