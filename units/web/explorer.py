"""Explorer routes."""
from . import routes
from pathlib import Path
from quart import redirect, render_template, request, send_file, url_for
import aiofiles
import os
import urllib.parse
import zipfile
import logging
logger = logging.getLogger(__name__)
from . import DATA_DIR
from . import HOME_DIR

def safe_path(base, name):
    base_path = Path(base).resolve()
    target = (base_path / name).resolve()
    # Schutz: nicht außerhalb des Basisordners
    if base_path not in target.parents and base_path != target:
        raise ValueError("Ungültiger Pfad!")
    return target

@routes.route("/explorer")
async def explorer():
    path = os.fspath(request.args.get("path") or HOME_DIR)
    selected_file = request.args.get("selected")
    edit_file = request.args.get("file")
    if not os.path.exists(path):
        path = os.fspath(HOME_DIR)
    try:
        raw_items = os.listdir(path)
    except PermissionError:
        return "Zugriff verweigert", 403
    items = []
    for name in raw_items:
        full_p = os.path.join(path, name)
        items.append({
            "name": name,
            "is_dir": os.path.isdir(full_p),
            "full_path": full_p
        })
    content = ""
    if edit_file:
        try:
            async with aiofiles.open(os.path.join(path, edit_file), "r") as f:
                content = await f.read()
        except Exception as e:
            content = f"Fehler: {e}"
    parent_path = os.path.dirname(path)
    return await render_template(
        "explorer.html",
        current_path=path,
        parent_path=parent_path,
        items=items,
        selected_file=selected_file,  
        edit_file=edit_file,          
        content=content,
        DATA_DIR=DATA_DIR,
        HOME_DIR=HOME_DIR
    )

@routes.post("/explorer/create_zip")
async def create_zip():
    form = await request.form
    path = form.get("path")
    # ZIP-Dateiname
    zip_name = os.path.basename(path) or "root"
    zip_name += ".zip"
    zip_path = os.path.join(path, zip_name)
    # ZIP im Ordner erstellen
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _dirs, files in os.walk(path):
            for file in files:
                # ZIP-Datei selbst nicht erneut einpacken
                if file == zip_name:
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, path)
                zipf.write(full_path, rel_path)
    # Zurück zum Explorer
    return redirect(f"/explorer?path={path}")

@routes.route("/explorer/save", methods=["POST"])
async def explorer_save():
    try:
        form = await request.form
        path = form.get("path")
        filename = form.get("filename")
        content = form.get("content")
        if not path or not filename:
            return "Fehlende Daten", 400
        full_path = os.path.join(path, filename)
        with open(full_path, "w", newline="") as f:
            f.write(content)
        return redirect(url_for("routes.explorer", path=path, file=filename))
    except Exception as e:
        logger.exception("❌ SAVE ERROR")
        return f"Fehler: {e}", 500

@routes.route("/explorer/new_file", methods=["POST"])
async def new_file():
    form = await request.form
    path = form.get("path")
    filename = form.get("filename")
    if not path or not filename:
        return "Fehlende Daten", 400
    full_path = os.path.join(path, filename)
    try:
        # Datei erstellen (leer)
        with open(full_path, "w") as f:
            f.write("")
    except Exception as e:
        return f"Fehler: {e}", 500
    return redirect(url_for("routes.explorer", path=path, selected=filename))

@routes.route("/explorer/new_folder", methods=["POST"])
async def new_folder():
    form = await request.form
    path = form.get("path")
    foldername = form.get("foldername")
    if not path or not foldername:
        return "Fehlende Daten", 400
    full_path = os.path.join(path, foldername)
    try:
        os.makedirs(full_path, exist_ok=True)
    except Exception:
        logger.exception("Fehler beim Erstellen des Ordners:")
        return "Fehler beim Erstellen des Ordners", 500
    return redirect(url_for("routes.explorer", path=path))

@routes.route("/explorer/delete", methods=["POST"])
async def delete_item():
    form = await request.form
    path = form.get("path")
    name = form.get("name")
    if not path or not name:
        return "Fehlende Daten", 400
    clean_path = os.path.normpath(path)
    full_path = Path(os.path.join(clean_path, name)).resolve()
    if not full_path.exists():
        return f"Datei oder Ordner existiert nicht unter: {full_path}", 404     
    try:
        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            import shutil
            shutil.rmtree(full_path)
        else:
            return "Unbekannter Typ", 400
    except Exception as error:
        return f"Fehler beim Löschen: {error}", 500      
    return redirect(url_for("routes.explorer", path=str(clean_path)))

@routes.route("/explorer/rename", methods=["POST"])
async def rename():
    form = await request.form
    path = form.get("path")
    old_name = form.get("old_name")
    new_name = form.get("new_name")
    if not path or not old_name or not new_name:
        return "Ungültige Daten", 400    
    try:
        # HIER DER WINDOWS-FIX: Pfad bereinigen
        clean_path = os.path.normpath(path)    
        from pathlib import Path
        old_path = Path(os.path.join(clean_path, old_name)).resolve()
        new_path = Path(os.path.join(clean_path, new_name)).resolve()
        if not old_path.exists():
            return f"Datei existiert nicht unter: {old_path}", 404
        old_path.rename(new_path)
    except Exception as e:
        return f"Fehler: {e}", 500
    return redirect(url_for("routes.explorer", path=clean_path, selected=new_name))

@routes.route("/explorer/upload", methods=["POST"])
async def explorer_upload():
    try:
        # Zielpfad aus dem Formular
        path = (await request.form).get("path")
        if not path:
            return "Kein Zielpfad angegeben", 400
        # Hochgeladene Datei
        files = await request.files
        file = files.get("file")
        if not file:
            return "Keine Datei ausgewählt", 400
        if not file.filename:
            return "Kein Dateiname vorhanden", 400
        # Zielordner
        ziel = os.path.join(path, file.filename)
        # Datei speichern
        await file.save(ziel)
        return redirect(
            url_for(
                "routes.explorer",
                path=path,
                selected=file.filename
            )
        )
    except Exception as e:
        return f"Fehler beim Upload: {e}", 500

@routes.route("/explorer/download")
async def explorer_download():
    path = request.args.get("path")
    name = request.args.get("name")
    if not path or not name:
        return "Fehlende Daten", 400 
    name = urllib.parse.unquote(name)
    path = urllib.parse.unquote(path)
    clean_path = os.path.normpath(path)
    file_path = os.path.normpath(os.path.join(clean_path, name))
    if not os.path.isfile(file_path):
        return f"Datei nicht gefunden unter: {file_path}", 404
    try:
        # HIER DER FIX: attachment_filename anstelle von download_name nutzen
        return await send_file(
            file_path,
            as_attachment=True,
            attachment_filename=name  # 👈 Für ältere Quart/Flask-Versionen
        )
    except Exception as e:
        return f"Fehler beim Download: {e}", 500
