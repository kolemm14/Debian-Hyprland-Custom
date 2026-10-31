"""Read Steam's installed Workshop manifest; never read account credentials."""
import json
import re
from pathlib import Path

from mpvpaper_download import steam_library_roots, steam_workshop_id
from .runtimes.project_detector import detect_project


def parse_manifest(text):
    tokens = iter(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|([{}])', text))

    def block(depth=0):
        if depth > 32:
            raise ValueError("Steam manifest nesting exceeds limit")
        result = {}
        for key, symbol in tokens:
            if symbol == '}':
                return result
            if symbol:
                raise ValueError("Invalid Steam manifest")
            value, symbol = next(tokens)
            if symbol == '}':
                raise ValueError("Invalid Steam manifest value")
            result[key] = block(depth + 1) if symbol == '{' else value
        if depth:
            raise ValueError("Incomplete Steam manifest")
        return result

    try:
        return block()
    except StopIteration as error:
        raise ValueError("Incomplete Steam manifest") from error


def installed_project(uri, roots=None):
    """Return a validated installed project, or None while Steam hasn't finished."""
    item_id = steam_workshop_id(uri)
    if not item_id:
        raise ValueError("Ouvrez la fiche d’un fond Steam Workshop avant d’importer.")
    for root in steam_library_roots() if roots is None else roots:
        workshop = Path(root) / 'steamapps/workshop'
        manifest = workshop / 'appworkshop_431960.acf'
        try:
            with manifest.open('r', encoding='utf-8') as stream:
                text = stream.read(4 * 1024 * 1024 + 1)
            if len(text) > 4 * 1024 * 1024:
                continue
            app = parse_manifest(text).get('AppWorkshop', {})
            if app.get('appid') != '431960':
                continue
            installed = app.get('WorkshopItemsInstalled', {}).get(item_id, {})
            details = app.get('WorkshopItemDetails', {}).get(item_id, {})
            version = installed.get('manifest')
            if not version or version == '0':
                continue
            if details.get('latest_manifest', version) != version:
                continue
            if (workshop / 'downloads/431960' / item_id).exists():
                continue
            folder = workshop / 'content/431960' / item_id
            if not (folder / 'project.json').is_file():
                continue
            project = detect_project(folder)
            # Explicit preview entries must not be treated as original media.
            data = json.loads((folder / 'project.json').read_text())
            if project.media and data.get('preview') and project.media == (folder / data['preview']).resolve():
                raise ValueError("Le projet désigne son aperçu comme média original : import refusé.")
            return project
        except (OSError, ValueError, AttributeError):
            continue
    return None
