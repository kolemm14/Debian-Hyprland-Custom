"""Rebuild local Nova patches against its pinned, already installed upstream.

No upstream fetch and no in-place git apply: edited QML receives .new through
the same ownership planner as every other configuration.
"""
import re
import tempfile
from pathlib import Path

from files import UpdateError, recipe, run, snapshot


def patch_inventory(tree, locations, components, previous=None):
    output = {}
    for group in recipe(tree).get('patch_sets', []):
        if group['component'] not in components:
            continue
        installed = locations.path(group['destination'])
        if not (installed / '.git').exists():
            raise UpdateError('Nova installé sans référence Git amont : restauration manuelle de sa référence nécessaire.')
        revision = run(['git', 'rev-parse', 'HEAD'], cwd=installed).stdout.strip()
        patches = [tree / name for name in group['patches'] if (tree / name).is_file()]
        prefix = group["destination"].rstrip("/") + "/"
        paths = {key[len(prefix):] for key, entry in (previous or {}).items()
                 if entry.get("external") and key.startswith(prefix)}
        for patch in patches:
            for name in re.findall(r'^(?:--- a/|\+\+\+ b/)([^\t\n]+)', patch.read_text(), re.M):
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise UpdateError('Chemin de patch hors périmètre')
                paths.add(name)
        with tempfile.TemporaryDirectory(prefix='deblestia-patch-') as directory:
            staging = Path(directory)
            for name in paths:
                result = run(['git', 'show', revision + ':' + name], cwd=installed, check=False)
                if result.returncode == 0:
                    path = staging / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(result.stdout)
            for patch in patches:
                run(['git', 'apply', '--whitespace=nowarn', str(patch.resolve())], cwd=staging)
            for name in paths:
                path = staging / name
                if not path.exists():
                    continue
                key = group['destination'].rstrip('/') + '/' + name
                output[key] = {'component': group['component'], 'source': 'patch:' + name,
                               'policy': 'config', 'external': True, 'reference': snapshot(path)}
    return output
