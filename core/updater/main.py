#!/usr/bin/env python3
"""Incremental updater. Python standard library; no installer is re-run."""
from __future__ import annotations

import argparse
import base64
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile

from files import (Locations, UpdateError, baseline, detect_components, fingerprint,
                   inventory, json_write, plan_files, read_json, recipe, run, snapshot)
from transaction import Lock, Services, apply, log, recover, rollback
from patches import patch_inventory
import install_state
from manager_backend import report, repair, stage_runtime, runtime_operation

OFFICIAL = 'https://github.com/kolemm14/Debian-Hyprland-Custom.git'
LEGACY = 'kebemouhamet08-gif'  # Recognition only; never used as a fetch destination.
REPOSITORY = 'Debian-Hyprland-Custom'


def migrated(url):
    for prefix in ('https://github.com/', 'git@github.com:', 'ssh://git@github.com/'):
        if url in (f'{prefix}{LEGACY}/{REPOSITORY}', f'{prefix}{LEGACY}/{REPOSITORY}.git'):
            return f'{prefix}kolemm14/{REPOSITORY}.git'
    return url


def remote(repo, mutate=False):
    urls = run(['git', 'config', '--get-all', 'remote.origin.url'], cwd=repo, check=False).stdout.splitlines()
    if len(urls) != 1:
        raise UpdateError('Un origin unique est nécessaire ; remotes personnalisés conservés.')
    original = urls[0]
    updated = migrated(original)
    if updated != original and mutate:
        run(['git', 'remote', 'set-url', 'origin', updated], cwd=repo)
        print('Origin officiel migré (protocole conservé).')
    return updated


def export_tree(git_dir, commit, destination):
    result = subprocess.run(['git', '--git-dir', str(git_dir), 'archive', commit],
                            capture_output=True, timeout=120, check=True)
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        archive.extractall(destination, filter='data')


def changes(git_dir, old, new):
    raw = run(['git', '--git-dir', str(git_dir), 'diff', '--name-status', '-z', '-M', old, new]).stdout.split('\0')
    output, renames = [], {}
    index = 0
    while index < len(raw) and raw[index]:
        status, source = raw[index:index + 2]
        index += 2
        if status.startswith(('R', 'C')):
            target = raw[index]
            index += 1
            output.append((status, source, target))
            if status.startswith('R'):
                renames[source] = target
        else:
            output.append((status, source))
    return output, renames


def prepare(repo, url, branch, head, installed, root):
    git_dir = root / 'objects.git'
    run(['git', 'init', '--bare', str(git_dir)])
    run(['git', '--git-dir', str(git_dir), 'fetch', '--no-tags', url, 'refs/heads/' + branch])
    latest = run(['git', '--git-dir', str(git_dir), 'rev-parse', 'FETCH_HEAD']).stdout.strip()
    if run(['git', '--git-dir', str(git_dir), 'cat-file', '-e', installed + '^{commit}'], check=False).returncode:
        # Historical local commits are consulted only for the installed reference,
        # never as a condition on the current development HEAD.
        fetched = run(['git', '--git-dir', str(git_dir), 'fetch', '--no-tags', url, installed], check=False)
        if fetched.returncode:
            run(['git', '--git-dir', str(git_dir), 'fetch', '--no-tags', str(repo), installed])
    old_tree, new_tree = root / 'old', root / 'new'
    export_tree(git_dir, installed, old_tree)
    export_tree(git_dir, latest, new_tree)
    # Older commits predate ownership recipes. The audited local mapping is
    # used only when the commit contains no mapping of its own.
    for tree in (old_tree, new_tree):
        mapping = tree / 'manifests/update-files.json'
        if not mapping.exists():
            mapping.parent.mkdir(exist_ok=True)
            shutil.copy2(repo / 'manifests/update-files.json', mapping)
    diff, renames = changes(git_dir, installed, latest)
    return git_dir, latest, old_tree, new_tree, diff, renames


def build_programs(tree, desired, old, locations, dry=False, force=False):
    builds = []
    for key, entry in desired.items():
        if 'build' not in entry:
            continue
        previous = old['files'].get(key)
        current = snapshot(locations.path(key))
        if previous and previous.get('inputs') == entry['inputs'] :
            entry['reference'] = previous['reference']
            continue
        builds.append(entry['component'] + ': cargo build --release --locked')
        if dry:
            # Precise destination, but compiled bytes cannot be known before building.
            entry['reference'] = current
            continue
        if not shutil.which('cargo'):
            raise UpdateError('Compilation requise : installez cargo et les dépendances documentées du composant.')
        build_root = tree / entry['build']
        run(['cargo', 'build', '--release', '--locked', '--manifest-path', str(build_root / 'Cargo.toml')], timeout=1800)
        entry['reference'] = snapshot(build_root / 'target/release' / entry['binary'])
    return builds


def missing_packages(tree, components):
    wanted = set()
    for component, packages in recipe(tree).get('packages', {}).items():
        if component in components:
            wanted.update(packages)
    for package in wanted:
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?', package):
            raise UpdateError('Nom de paquet Debian invalide dans le manifest')
    return sorted(package for package in wanted if run(
        ['dpkg-query', '-W', '-f=${db:Status-Abbrev}', package], check=False).stdout.strip() != 'ii')


def service_plan(operations, desired, old, new_recipe, renames):
    names, removed, replacements = set(), set(), {}
    affected = set()
    unit_changed = False
    for operation in operations:
        key = operation['key']
        if operation['action'] == 'CONFLICT':
            continue
        entry = desired.get(key) or old['files'].get(key)
        if entry:
            affected.add(entry['component'])
        if 'systemd/user/' in key and key.endswith(('.service', '.timer')):
            unit_changed = True
            name = Path(key).name
            names.add(name)
            if operation['after'] is None:
                removed.add(name)
                old_source = old['files'][key]['source']
                new_source = renames.get(old_source)
                for target, item in desired.items():
                    if new_source and item['source'] == new_source and 'systemd/user/' in target:
                        replacements[name] = Path(target).name
    for component in affected:
        names.update(new_recipe.get('services', {}).get(component, []))
    if old.get('pending_reload'):
        unit_changed = True
        names.update(old.get('pending_services', []))
    return names, removed, replacements, unit_changed


def record(repo, locations, component):
    commit = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
    current = read_json(locations.manifest, {'schema': 1, 'commit': commit, 'components': [], 'files': {}, 'proposals': {}})
    # A freshly reinstalled component may now contain local uncommitted files.
    # Its exact per-file reference is retained; other components are untouched.
    source = locations.runtime.resolve() if locations.runtime.is_dir() else repo
    own = baseline(source, locations, {component}, commit)
    patched = patch_inventory(source, locations, {component})
    for key, entry in patched.items():
        actual = snapshot(locations.path(key))
        if actual == entry['reference']:
            own['files'][key] = {**entry, 'installed': actual, 'commit': commit}
    for key, entry in inventory(source, locations, {component}).items():
        if 'build' in entry:
            actual = snapshot(locations.path(key))
            if actual is not None:
                own['files'][key] = {**entry, 'reference': actual, 'installed': actual, 'commit': commit}
    for key, item in own['files'].items():
        current['files'][key] = item
    current['components'] = sorted(set(current['components']) | {component})
    current['disabled_components'] = [c for c in current.get('disabled_components', []) if c != component]
    current.setdefault('branch', 'main')
    json_write(locations.manifest, current)
    json_write(locations.data / 'version', {'commit': current['commit'], 'branch': current['branch']})
    install_state.migrate(repo, locations)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Debian-Hyprland-Custom Updater')
    group = parser.add_mutually_exclusive_group()
    for name in ('check', 'dry-run', 'force', 'migrate-only', 'rollback'):
        group.add_argument('--' + name, action='store_true')
    group.add_argument('--record-component', metavar='ID', help=argparse.SUPPRESS)
    group.add_argument('--forget-component', metavar='ID', help=argparse.SUPPRESS)
    group.add_argument('--state', action='store_true', help='migrer/lire InstallState (INI)')
    group.add_argument('--inspect', action='store_true', help='santé locale structurée (INI)')
    group.add_argument('--repair', metavar='COMPONENT', help='réparer les fichiers possédés, sans réseau')
    parser.add_argument('--cache-result', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--yes', action='store_true', help='autoriser les nouveaux paquets Debian affichés')
    parser.add_argument('action', nargs='?', choices=['update'])
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    locations = Locations(repo)
    if args.migrate_only:
        # Compatibility: no origin and multi-URL origins are harmless in migration-only mode.
        urls = run(['git', 'config', '--get-all', 'remote.origin.url'], cwd=repo, check=False).stdout.splitlines()
        if len(urls) == 1:
            remote(repo, True)
        return 0
    if os.geteuid() == 0 and os.environ.get('SUDO_USER'):
        raise UpdateError('Lancez ./update.sh sans sudo ; seuls les paquets nécessitent une élévation.')
    readonly = args.check or args.dry_run or args.inspect
    context = nullcontext() if readonly else Lock(locations)
    with context:
        if readonly and (locations.state / 'pending.json').exists():
            raise UpdateError('Transaction interrompue : lancez ./update.sh pour restaurer avant vérification.')
        if not readonly:
            recover(locations)
        if args.state:
            print(install_state.encode(install_state.migrate(repo, locations)), end='')
            return 0
        if args.inspect:
            print(report(repo, locations), end='')
            return 0
        if args.repair:
            install_state.migrate(repo, locations)
            repair(locations, args.repair)
            return 0
        if args.record_component:
            record(repo, locations, args.record_component)
            return 0
        if args.forget_component:
            state = read_json(locations.manifest, None)
            if state:
                state['components'] = [c for c in state['components'] if c != args.forget_component]
                state['disabled_components'] = sorted(set(state.get('disabled_components', [])) | {args.forget_component})
                state['files'] = {k: v for k, v in state['files'].items() if v['component'] != args.forget_component}
                json_write(locations.manifest, state)
            return 0
        if args.rollback:
            backups = sorted((locations.data / 'backups').glob('*/journal.json'))
            candidates = [p.parent for p in backups if read_json(p, {}).get('status') == 'committed']
            if not candidates:
                raise UpdateError('Aucune sauvegarde restaurable')
            rollback(locations, candidates[-1], manual=True)
            return 0
        identity = install_state.migrate(repo, locations, persist=not readonly)
        url = identity['repository']
        target_branch = identity['branch']
        installed = identity['installed_commit']
        head = installed  # informational transaction label; never development HEAD
        old = read_json(locations.manifest, None)
        if old and old.get('schema') != 1:
            raise UpdateError('Version inconnue du manifest installé')
        if old and old['commit'] != installed:
            raise UpdateError('InstallState et manifest installé incohérents ; diagnostic requis')
        with tempfile.TemporaryDirectory(prefix='deblestia-update-') as directory:
            git_dir, latest, old_tree, new_tree, diff, renames = prepare(repo, url, target_branch, head, installed, Path(directory))
            version_label = identity['installed_version'] + ' / ' + installed[:12]
            print(f'Debian-Hyprland-Custom Updater\n\nVersion installée : {version_label}\nVersion distante   : {latest[:12]}')
            if args.check and args.cache_result:
                install_state.atomic_write(locations.cache / 'available.ini', {
                    'kind': 'file', 'value': base64.b64encode(install_state.encode(
                        install_state.next_state(identity, latest, new_tree)).encode()).decode(), 'mode': 0o600})
            if args.check:
                if installed == latest:
                    print('Debian-Hyprland-Custom est déjà à jour.')
                elif run(['git', '--git-dir', str(git_dir), 'merge-base', '--is-ancestor', installed, latest], check=False).returncode == 0:
                    print('Mise à jour disponible.')
                else:
                    print('Version locale en avance ou divergente ; aucune mise à jour automatique possible.')
                return 0
            components = detect_components(locations, old.get('components', []) if old else [])
            components -= set(old.get('disabled_components', []) if old else [])
            if old is None:
                old = baseline(old_tree, locations, components, installed)
                print('Installation historique : adoption des seuls fichiers identiques à la référence Git.')
            else:
                newly_detected = components - set(old.get('components', []))
                old['files'].update(baseline(old_tree, locations, newly_detected, installed)['files'])
            old['components'] = sorted(components)
            locations.roots['repo'] = locations.runtime
            desired = inventory(new_tree, locations, components)
            for key, entry in patch_inventory(old_tree, locations, components).items():
                actual = snapshot(locations.path(key))
                if key not in old['files'] and actual == entry['reference']:
                    old['files'][key] = {**entry, 'installed': actual, 'commit': installed}
            desired.update(patch_inventory(new_tree, locations, components, old['files']))
            packages = missing_packages(new_tree, components)
            builds = build_programs(new_tree, desired, old, locations, True, args.force)
            operations, conflicts, manifest = plan_files(locations, old, desired, latest, args.force)
            manifest['disabled_components'] = old.get('disabled_components', [])
            manifest['branch'] = target_branch
            names, removed, replacements, unit_changed = service_plan(operations, desired, old, recipe(new_tree), renames)
            print('\nChanges (Git):')
            for change in diff:
                print('  ' + ' -> '.join(change))
            for label, codes in [('Fichiers à ajouter', {'A'}), ('Fichiers à modifier', {'M'}), ('Fichiers à supprimer', {'D'}), ('Propositions .new', {'CONFLICT'})]:
                selected = [op['key'] for op in operations if op['action'] in codes]
                print(f'{label} : {len(selected)}')
                for key in selected:
                    print('  ' + str(locations.path(key)))
            for key, entry in desired.items():
                if 'build' in entry and (not old['files'].get(key) or old['files'][key].get('inputs') != entry['inputs']):
                    print('Fichier à compiler/installer : ' + str(locations.path(key)))
                    names.update(recipe(new_tree).get('services', {}).get(entry['component'], []))
            print('Services concernés : ' + (', '.join(sorted(names)) or 'aucun'))
            print('Daemon-reload : ' + ('oui' if unit_changed else 'non'))
            print('Paquets à ajouter : ' + (', '.join(packages) or 'aucun'))
            print('Configurations/fichiers en conflit : ' + (', '.join(conflicts) or 'aucun'))
            for build in builds:
                print('Compilation nécessaire : ' + build)
            components_file = new_tree / 'manifests/components.tsv'
            previous_components = old_tree / 'manifests/components.tsv'
            previous_ids = {line.split('\t')[0] for line in previous_components.read_text().splitlines()} if previous_components.exists() else set()
            if components_file.exists():
                for line in components_file.read_text().splitlines():
                    columns = line.split('\t')
                    if len(columns) >= 3 and not line.startswith('#') and columns[0] not in components and columns[0] not in previous_ids:
                        print(f'Nouveau composant disponible : {columns[1]}. Utilisez ./{columns[2]} pour l’installer.')
            if args.dry_run:
                print('Dry-run : aucune modification persistante. Les compilations ne sont pas exécutées.')
                return 0
            if not operations and installed == latest and not old.get('pending_reload') and not packages and not builds:
                # Bootstrap ownership once, without re-installing or a backup of media.
                if read_json(locations.manifest, None) != manifest:
                    json_write(locations.manifest, manifest)
                    json_write(locations.data / 'version', {'commit': latest, 'branch': target_branch})
                target = stage_runtime(new_tree, locations, latest)
                from files import atomic_write
                atomic_write(locations.runtime, target)
                current_identity = install_state.load(locations)
                if current_identity['installed_version'] != install_state.version(new_tree):
                    install_state.write(locations, install_state.next_state(identity, latest, new_tree))
                print('Debian-Hyprland-Custom est déjà à jour.')
                log(locations, f'NOOP {latest}')
                return 0
            if packages:
                if not args.yes:
                    if not sys.stdin.isatty() or input('Installer ces paquets avec apt ? [o/N] ').lower() not in ('o', 'oui', 'y', 'yes'):
                        raise UpdateError('Dépendances manquantes ; utilisez --yes pour autoriser leur installation.')
                run(['sudo', 'apt-get', 'install', '--no-install-recommends', '-y', *packages], timeout=1800)
            if builds:
                build_programs(new_tree, desired, old, locations, False, args.force)
                operations, conflicts, manifest = plan_files(locations, old, desired, latest, args.force)
                manifest['disabled_components'] = old.get('disabled_components', [])
                manifest['branch'] = target_branch
                names, removed, replacements, unit_changed = service_plan(operations, desired, old, recipe(new_tree), renames)
            target = stage_runtime(new_tree, locations, latest)
            operations.extend(runtime_operation(locations, target))
            services = Services(names, removed, replacements)
            backup = apply(locations, operations, manifest, services, unit_changed, installed, latest, False,
                           install_state.next_state(identity, latest, new_tree))
            print(f'Mise à jour terminée. Sauvegarde : {backup}')
            if conflicts:
                print('Personnalisations conservées : examinez les fichiers .new signalés.')
            if manifest.get('pending_reload'):
                print('Bus utilisateur absent : rechargement différé au prochain ./update.sh en session.')
    return 0


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    try:
        raise SystemExit(main())
    except (UpdateError, OSError, ValueError, SyntaxError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        # Subprocess exception strings may include credential-bearing URLs.
        message = str(error) if isinstance(error, (UpdateError, SyntaxError)) else type(error).__name__
        if not any(option in sys.argv for option in ('--check', '--dry-run')):
            try:
                log(Locations(Path(__file__).resolve().parents[2]), 'ERROR ' + message)
            except OSError:
                pass
        print('Mise à jour interrompue : ' + message, file=sys.stderr)
        raise SystemExit(1)
