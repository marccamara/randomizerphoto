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
# CONFIGURATION
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
# ÉTAT GLOBAL
# ============================================================

STATE = {
    "base": None,
    "dbg": "Application prête.",
    "picking": False,
    "done": 0,
    "total": 0,
    "running": False,
    "finished": False,
    "error": None,
}


# ============================================================
# RÉFÉRENCES OBJECTIVE-C
# ============================================================

REFS = {
    "picker": None,
    "delegate": None,
    "security_url": None,
}


# ============================================================
# DEBUG
# ============================================================

def debug(message):
    """
    Met à jour le message de diagnostic
    et l'affiche également dans les logs.
    """

    message = str(message)

    STATE["dbg"] = message

    print(
        "[RandomizerPhoto]",
        message,
    )


# ============================================================
# SECURITY SCOPE
# ============================================================

def stop_security_scope():
    """
    Libère l'accès au dossier sélectionné.
    """

    url = REFS.get("security_url")

    if url is None:
        return

    try:
        url.stopAccessingSecurityScopedResource()

        print(
            "[RandomizerPhoto] "
            "Security scope libéré."
        )

    except Exception as e:

        print(
            "[RandomizerPhoto] "
            "Erreur libération security scope:",
            e,
        )

    REFS["security_url"] = None


# ============================================================
# PROTOCOLE UIDOCUMENTPICKERDELEGATE
# ============================================================

UIDocumentPickerDelegate = ObjCProtocol(
    "UIDocumentPickerDelegate"
)


# ============================================================
# DELEGATE
# ============================================================

class PickerDelegate(
    NSObject,
    protocols=[UIDocumentPickerDelegate],
):

    # ========================================================
    # iOS 11+
    #
    # Objective-C :
    #
    # documentPicker:didPickDocumentsAtURLs:
    #
    # Rubicon :
    #
    # documentPicker_didPickDocumentsAtURLs_
    # ========================================================

    @objc_method
    def documentPicker_didPickDocumentsAtURLs_(
        self,
        picker,
        urls,
    ):

        print("")
        print("==========================================")
        print("📁 CALLBACK iOS MODERNE REÇU")
        print("==========================================")

        try:

            STATE["picking"] = False
            STATE["error"] = None

            debug(
                "✅ CALLBACK REÇU : "
                "documentPicker:didPickDocumentsAtURLs:"
            )

            # ------------------------------------------------
            # Vérification
            # ------------------------------------------------

            if not urls:

                STATE["base"] = None

                debug(
                    "⚠️ Callback reçu mais "
                    "iOS a retourné 0 URL."
                )

                return

            print(
                "Nombre d'URL :",
                len(urls),
            )

            # Une seule sélection autorisée
            url = urls[0]

            print(
                "NSURL reçue :",
                url,
            )

            debug(
                "URL reçue : " + str(url)
            )

            # ------------------------------------------------
            # Ancien security scope
            # ------------------------------------------------

            stop_security_scope()

            # ------------------------------------------------
            # Garder l'NSURL en vie
            # ------------------------------------------------

            REFS["security_url"] = url

            # ------------------------------------------------
            # Security-scoped access
            # ------------------------------------------------

            try:

                access = (
                    url.startAccessingSecurityScopedResource()
                )

                print(
                    "startAccessingSecurityScopedResource:",
                    access,
                )

            except Exception as e:

                print(
                    "Erreur security scope:",
                    e,
                )

            # ------------------------------------------------
            # Récupérer le PATH
            # ------------------------------------------------

            try:

                path = url.path

                if callable(path):
                    path = path()

                path = str(path)

            except Exception as e:

                STATE["base"] = None

                debug(
                    "❌ Impossible de récupérer "
                    "url.path : " + str(e)
                )

                return

            print(
                "PATH :",
                path,
            )

            # ------------------------------------------------
            # Vérifier Path
            # ------------------------------------------------

            base = Path(path)

            if not base.exists():

                STATE["base"] = None

                debug(
                    "❌ Le dossier n'existe pas : "
                    + str(base)
                )

                return

            if not base.is_dir():

                STATE["base"] = None

                debug(
                    "❌ L'élément sélectionné "
                    "n'est pas un dossier."
                )

                return

            # ------------------------------------------------
            # COMPTER LES IMAGES
            # ------------------------------------------------

            try:

                count = sum(
                    1
                    for f in base.iterdir()
                    if f.suffix.lower() in EXTS
                )

            except Exception:

                count = 0

            # ------------------------------------------------
            # SUCCÈS
            # ------------------------------------------------

            STATE["base"] = str(base)

            STATE["error"] = None

            debug(
                "✅ DOSSIER SÉLECTIONNÉ : "
                + str(base)
                + " | "
                + str(count)
                + " images"
            )

            print("")
            print("==========================================")
            print("✅ SUCCÈS")
            print("DOSSIER :", base)
            print("IMAGES  :", count)
            print("==========================================")
            print("")

        except Exception:

            STATE["base"] = None

            STATE["picking"] = False

            STATE["error"] = (
                "Erreur dans le callback."
            )

            STATE["dbg"] = (
                "❌ ERREUR CALLBACK\n\n"
                + traceback.format_exc()[-2000:]
            )

            print(
                traceback.format_exc()
            )


    # ========================================================
    # ANCIEN CALLBACK
    #
    # iOS plus ancien :
    #
    # documentPicker:didPickDocumentAtURL:
    # ========================================================

    @objc_method
    def documentPicker_didPickDocumentAtURL_(
        self,
        picker,
        url,
    ):

        print("")
        print("==========================================")
        print("📁 ANCIEN CALLBACK REÇU")
        print("==========================================")

        try:

            STATE["picking"] = False

            if url is None:

                STATE["base"] = None

                debug(
                    "⚠️ Ancien callback sans URL."
                )

                return

            # Transformer en traitement identique
            # au callback moderne.

            self._process_selected_url(
                url
            )

        except Exception:

            STATE["base"] = None

            STATE["error"] = (
                "Erreur ancien callback."
            )

            STATE["dbg"] = (
                "❌ ERREUR ANCIEN CALLBACK\n\n"
                + traceback.format_exc()[-2000:]
            )

            print(
                traceback.format_exc()
            )


    # ========================================================
    # TRAITEMENT COMMUN D'UNE URL
    # ========================================================

    def _process_selected_url(
        self,
        url,
    ):

        try:

            print(
                "URL reçue :",
                url,
            )

            stop_security_scope()

            REFS["security_url"] = url

            # ----------------------------------------------
            # Security scope
            # ----------------------------------------------

            try:

                access = (
                    url.startAccessingSecurityScopedResource()
                )

                print(
                    "Security scope:",
                    access,
                )

            except Exception as e:

                print(
                    "Security scope erreur:",
                    e,
                )

            # ----------------------------------------------
            # Path
            # ----------------------------------------------

            path = url.path

            if callable(path):
                path = path()

            path = str(path)

            base = Path(path)

            # ----------------------------------------------
            # Vérifications
            # ----------------------------------------------

            if not base.exists():

                STATE["base"] = None

                debug(
                    "❌ Dossier inexistant : "
                    + str(base)
                )

                return

            if not base.is_dir():

                STATE["base"] = None

                debug(
                    "❌ Ce n'est pas un dossier."
                )

                return

            # ----------------------------------------------
            # Images
            # ----------------------------------------------

            try:

                count = sum(
                    1
                    for f in base.iterdir()
                    if f.suffix.lower() in EXTS
                )

            except Exception:

                count = 0

            # ----------------------------------------------
            # OK
            # ----------------------------------------------

            STATE["base"] = str(base)

            STATE["error"] = None

            debug(
                "✅ DOSSIER OK : "
                + str(base)
                + " | Images : "
                + str(count)
            )

        except Exception:

            STATE["base"] = None

            STATE["error"] = (
                "Erreur traitement URL."
            )

            STATE["dbg"] = (
                "❌ ERREUR URL\n\n"
                + traceback.format_exc()[-2000:]
            )

            print(
                traceback.format_exc()
            )


    # ========================================================
    # ANNULATION
    # ========================================================

    @objc_method
    def documentPickerWasCancelled_(
        self,
        picker,
    ):

        STATE["picking"] = False

        STATE["error"] = None

        debug(
            "Sélection du dossier annulée."
        )

        print(
            "[RandomizerPhoto] "
            "Picker annulé."
        )


# ============================================================
# CRÉATION DU PICKER
# ============================================================

def create_folder_picker():

    print("")
    print("==========================================")
    print("📂 CRÉATION DU PICKER")
    print("==========================================")

    Picker = ObjCClass(
        "UIDocumentPickerViewController"
    )

    UTType = ObjCClass(
        "UTType"
    )

    # --------------------------------------------------------
    # public.folder
    # --------------------------------------------------------

    try:

        folder_type = (
            UTType.typeWithIdentifier_(
                "public.folder"
            )
        )

    except Exception:

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
        "UTType public.folder : OK"
    )

    # --------------------------------------------------------
    # API moderne
    # --------------------------------------------------------

    try:

        picker = (
            Picker.alloc()
            .initForOpeningContentTypes_asCopy_(
                [folder_type],
                False,
            )
        )

        print(
            "API utilisée : "
            "initForOpeningContentTypes:asCopy:"
        )

    except Exception as e:

        print(
            "API asCopy indisponible :",
            e,
        )

        picker = (
            Picker.alloc()
            .initForOpeningContentTypes_(
                [folder_type]
            )
        )

        print(
            "API utilisée : "
            "initForOpeningContentTypes:"
        )

    if picker is None:

        raise RuntimeError(
            "Impossible de créer le picker."
        )

    return picker


# ============================================================
# PRÉSENTER LE PICKER
# ============================================================

def present_picker(app):

    try:

        STATE["picking"] = True

        STATE["error"] = None

        debug(
            "Création du sélecteur de dossier..."
        )

        # ----------------------------------------------------
        # Picker
        # ----------------------------------------------------

        picker = create_folder_picker()

        # ----------------------------------------------------
        # Delegate
        # ----------------------------------------------------

        delegate = (
            PickerDelegate.alloc().init()
        )

        if delegate is None:

            raise RuntimeError(
                "Impossible de créer PickerDelegate."
            )

        # ----------------------------------------------------
        # IMPORTANT
        # ----------------------------------------------------
        #
        # Garder les références très fortement.
        # ----------------------------------------------------

        REFS["picker"] = picker

        REFS["delegate"] = delegate

        # ----------------------------------------------------
        # Affecter delegate
        # ----------------------------------------------------

        picker.delegate = delegate

        picker.allowsMultipleSelection = False

        print(
            "Delegate :",
            picker.delegate,
        )

        # ----------------------------------------------------
        # Fenêtre native Toga
        # ----------------------------------------------------

        native = (
            app.main_window
            ._impl
            .native
        )

        window = ObjCInstance(
            native
        )

        # ----------------------------------------------------
        # Root VC
        # ----------------------------------------------------

        root = (
            window.rootViewController
        )

        if root is None:

            raise RuntimeError(
                "rootViewController introuvable."
            )

        print(
            "Root VC :",
            root,
        )

        # ----------------------------------------------------
        # Présenter
        # ----------------------------------------------------

        root.presentViewController(
            picker,
            animated=True,
            completion=None,
        )

        debug(
            "📂 Picker ouvert. "
            "Entre dans ton dossier puis appuie sur Ouvrir."
        )

        print(
            "=========================================="
        )
        print(
            "✅ PICKER AFFICHÉ"
        )
        print(
            "=========================================="
        )

    except Exception:

        STATE["picking"] = False

        STATE["error"] = (
            "Erreur ouverture picker."
        )

        STATE["dbg"] = (
            "❌ ERREUR PICKER\n\n"
            + traceback.format_exc()[-2000:]
        )

        print(
            traceback.format_exc()
        )


# ============================================================
# COMPTER LES IMAGES
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
# PROGRESSION
# ============================================================

def progress(
    done,
    total,
):

    STATE["done"] = done
    STATE["total"] = total


# ============================================================
# TRAITEMENT
# ============================================================

def run_processing(
    n,
    model,
):

    STATE["done"] = 0
    STATE["total"] = 0
    STATE["running"] = True
    STATE["finished"] = False
    STATE["error"] = None

    try:

        if not STATE["base"]:

            raise RuntimeError(
                "Aucun dossier sélectionné."
            )

        base = Path(
            STATE["base"]
        )

        if not base.exists():

            raise RuntimeError(
                "Le dossier n'est plus accessible."
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
        # Traitement
        # ----------------------------------------------------

        debug(
            "Traitement en cours..."
        )

        process_folder_advanced(
            str(base),
            str(out),
            n,
            str(HIST),
            progress,
            model,
        )

        debug(
            "✅ Traitement terminé."
        )

    except Exception as e:

        STATE["error"] = str(e)

        STATE["dbg"] = (
            "❌ ERREUR TRAITEMENT\n\n"
            + traceback.format_exc()[-2000:]
        )

        print(
            traceback.format_exc()
        )

    finally:

        STATE["running"] = False
        STATE["finished"] = True

        # Le traitement est terminé.
        stop_security_scope()

        REFS["picker"] = None
        REFS["delegate"] = None


# ============================================================
# HTTP SERVER
# ============================================================

def make_handler(app):

    class Handler(
        BaseHTTPRequestHandler
    ):

        def log_message(
            self,
            *args,
        ):
            pass


        # ----------------------------------------------------
        # JSON
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

                debug(
                    "Demande de sélection..."
                )

                # UIKit sur le thread principal.
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
        # Serveur HTTP local
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
            "[RandomizerPhoto] "
            "Serveur HTTP :",
            port,
        )

        # ----------------------------------------------------
        # Fenêtre
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
        # Affichage
        # ----------------------------------------------------

        self.main_window.show()

        print(
            "[RandomizerPhoto] "
            "Application prête."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    return RandomizerPhoto(
        "RandomizerPhoto",
        "com.perso.randomizerphoto",
    )
