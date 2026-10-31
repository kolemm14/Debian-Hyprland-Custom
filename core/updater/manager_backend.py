"""Local Manager operations using the updater's ownership and transaction APIs."""
import configparser
import io
import os
from pathlib import Path
import shutil
import tempfile

from files import UpdateError, atomic_write, plan_files, read_json, snapshot
from transaction import Services, apply
import install_state


def report(repo, locations):
    state = install_state.migrate(repo, locations, persist=False)
    text = install_state.encode(state)
    manifest = read_json(locations.manifest, {})
    parser = configparser.ConfigParser(interpolation=None)
    for component in manifest.get('components', []):
        owned = {k: v for k, v in manifest.get('files', {}).items() if v['component'] == component}
        problems = []
        good = 0
        for key, entry in owned.items():
            actual = snapshot(locations.path(key))
            if actual is None:
                problems.append('Missing file: ' + str(locations.path(key)))
            elif entry.get('policy') != 'config' and actual != entry['installed']:
                problems.append('Manifest mismatch: ' + str(locations.path(key)))
            else:
                good += 1
        parser['component:' + component] = {'known': 'true', 'files_ok': str(not problems).lower(),
            'healthy_files': str(good), 'problems': '\\n'.join(problems).replace(';', ',')}
    out = io.StringIO()
    parser.write(out, space_around_delimiters=False)
    return text + '\n' + out.getvalue()


def stage_runtime(tree, locations, commit):
    """Publish an immutable release; the transaction switches the runtime symlink."""
    parent = locations.data / 'releases'
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / commit
    if not target.exists():
        temporary = Path(tempfile.mkdtemp(prefix='.stage-', dir=parent))
        try:
            shutil.copytree(tree, temporary, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('.git', 'target', '__pycache__', '*.o'))
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    elif target.is_symlink() or not target.is_dir():
        raise UpdateError('Release runtime invalide')
    return {'kind': 'link', 'value': str(target)}


def runtime_operation(locations, target):
    before = snapshot(locations.runtime)
    if before == target:
        return []
    return [{'key': 'data:debian-hyprland-custom/runtime', 'before': before,
             'after': target, 'action': 'M' if before else 'A'}]


def repair(locations, component):
    manifest = read_json(locations.manifest, None)
    if not manifest or component not in manifest.get('components', []):
        raise UpdateError('Repair indisponible : aucun manifest installé pour ce composant')
    owned = {k: v for k, v in manifest['files'].items() if v['component'] == component}
    if not owned:
        raise UpdateError('Repair indisponible : aucun fichier attribué au composant')
    # Existing immutable references are sufficient: repair works offline and never
    # takes source bytes from a dirty development checkout.
    subset = {**manifest, 'files': owned, 'proposals': {}}
    desired = {k: dict(v) for k, v in owned.items()}
    operations, conflicts, repaired = plan_files(locations, subset, desired, manifest['commit'])
    updated = {**manifest, 'files': {**manifest['files'], **repaired['files']},
               'proposals': {**manifest.get('proposals', {}), **repaired['proposals']}}
    names = {Path(op['key']).name for op in operations
             if 'systemd/user/' in op['key'] and op['key'].endswith(('.service', '.timer'))}
    if operations:
        apply(locations, operations, updated, Services(names), bool(names),
              manifest['commit'], manifest['commit'], False)
    failures = []
    for op in operations:
        if snapshot(locations.path(op['key'])) != op['after']:
            failures.append(op['key'])
    if failures:
        raise UpdateError('Repair recheck échoué : ' + ', '.join(failures))
    print('Repair terminé : ' + component)
    print('Fichiers restaurés/proposés : ' + str(len(operations)))
    if conflicts:
        print('PARTIAL : personnalisations conservées ; propositions .new : ' + ', '.join(conflicts))
    else:
        print('Recheck : fichiers gérés conformes')
