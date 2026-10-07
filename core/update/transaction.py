"""Durable file journal, bounded backups, and user-service lifecycle."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import signal
import time

from files import UpdateError, atomic_write, json_write, read_json, run, snapshot


class Lock:
    def __init__(self, locations):
        self.locations = locations
        self.stream = None

    def __enter__(self):
        self.locations.state.mkdir(parents=True, exist_ok=True)
        self.stream = (self.locations.state / 'update.lock').open('a')
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stream.close()
            raise UpdateError('Une mise à jour est déjà en cours.')
        return self

    def __exit__(self, *args):
        self.stream.close()


class Services:
    def __init__(self, names, removed=(), renames=None):
        self.names = sorted(set(names))
        self.removed = sorted(set(removed))
        self.renames = renames or {}
        self.states = {}
        self.available = False
        if self.names and shutil.which('systemctl'):
            self.available = run(['systemctl', '--user', 'show-environment'], check=False).returncode == 0
        if self.available:
            for name in self.names:
                self.states[name] = {
                    'active': run(['systemctl', '--user', 'is-active', name], check=False).stdout.strip() in {'active', 'activating', 'reloading'},
                    'enabled': run(['systemctl', '--user', 'is-enabled', name], check=False).stdout.strip() == 'enabled',
                }

    def stop(self):
        for name, state in self.states.items():
            if state['active']:
                run(['systemctl', '--user', 'stop', name])
            if name in self.removed and state['enabled']:
                run(['systemctl', '--user', 'disable', name])

    def reload(self, unit_changed):
        if not self.available:
            return bool(self.names or unit_changed)
        if unit_changed:
            run(['systemctl', '--user', 'daemon-reload'])
        for name, state in self.states.items():
            replacement = self.renames.get(name, name)
            if name in self.removed and replacement == name:
                continue
            if replacement != name and state['enabled']:
                run(['systemctl', '--user', 'enable', replacement])
            if state['active']:
                run(['systemctl', '--user', 'start', replacement])
                if run(['systemctl', '--user', 'is-active', replacement], check=False).stdout.strip() != 'active':
                    raise UpdateError(f"Service non actif : {replacement}")
        return False

    def restore(self):
        if not self.available:
            return
        run(['systemctl', '--user', 'daemon-reload'])
        for old, new in self.renames.items():
            run(['systemctl', '--user', 'disable', '--now', new], check=False)
        for name, state in self.states.items():
            if state['enabled'] and name in self.removed:
                run(['systemctl', '--user', 'enable', name])
            run(['systemctl', '--user', 'start' if state['active'] else 'stop', name])


def log(locations, message):
    locations.state.mkdir(parents=True, exist_ok=True)
    with (locations.state / 'update.log').open('a') as stream:
        stream.write(time.strftime('%Y-%m-%dT%H:%M:%S%z ') + message + '\n')


def rollback(locations, backup, *, manual=False):
    journal = read_json(backup / 'journal.json', None)
    if not journal:
        raise UpdateError('Journal de restauration absent')
    services = Services([])
    services.states = journal['services']
    services.renames = journal.get('renames', {})
    services.removed = journal.get('removed', [])
    services.available = journal['service_bus']
    # Refuse to destroy edits made after the transaction, including after SIGKILL.
    for operation in journal['operations']:
        current = snapshot(locations.path(operation['key']))
        if current not in (operation['before'], operation['after']):
            raise UpdateError(f"Rollback interrompu : modification ultérieure de {operation['key']}")
    if services.available:
        for name in set(services.states) | set(services.renames.values()):
            run(['systemctl', '--user', 'stop', name], check=False)
    for operation in reversed(journal['operations']):
        atomic_write(locations.path(operation['key']), operation['before'])
    atomic_write(locations.manifest, journal['manifest_before'])
    atomic_write(locations.data / 'version', journal['version_before'])
    services.restore()
    if 'install_state_before' in journal:
        atomic_write(locations.data / 'install-state.ini', journal['install_state_before'])
    for directory in reversed(journal.get('created_dirs', [])):
        try:
            locations.path(directory).rmdir()
        except OSError:
            pass
    journal['status'] = 'rolled_back'
    json_write(backup / 'journal.json', journal)
    (locations.state / 'pending.json').unlink(missing_ok=True)
    log(locations, 'ROLLBACK terminé')


def recover(locations):
    pending = read_json(locations.state / 'pending.json', None)
    if pending:
        backup = locations.data / 'backups' / pending['backup']
        journal = read_json(backup / 'journal.json', {})
        if journal.get('status') == 'committed':
            (locations.state / 'pending.json').unlink(missing_ok=True)
        else:
            print('Transaction interrompue : restauration avant nouvelle mise à jour.')
            rollback(locations, backup)


def apply(locations, operations, manifest, services, unit_changed, old_head, new_head, advance, install_state=None):
    backup = locations.data / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + f'-{time.time_ns()}')
    backup.mkdir(parents=True, mode=0o700)
    created = []
    for operation in operations:
        key = operation['key']
        root, rel = key.split(':', 1)
        parents = list(Path(rel).parents)[:-1]
        for parent in reversed(parents):
            directory = root + ':' + str(parent)
            if not locations.path(directory).exists() and directory not in created:
                created.append(directory)
    journal = {'status': 'pending', 'operations': operations, 'services': services.states,
               'service_bus': services.available, 'renames': services.renames, 'removed': services.removed,
               'manifest_before': snapshot(locations.manifest),
               'version_before': snapshot(locations.data / 'version'),
               'install_state_before': snapshot(locations.data / 'install-state.ini'),
               'old_head': old_head, 'new_head': new_head, 'created_dirs': created}
    json_write(backup / 'journal.json', journal)
    json_write(locations.state / 'pending.json', {'backup': backup.name})
    log(locations, f'BEGIN {old_head} -> {new_head}')
    try:
        services.stop()
        # All additions/replacements precede removals (including renames).
        for operation in sorted(operations, key=lambda op: op['after'] is None):
            path = locations.path(operation['key'])
            if snapshot(path) != operation['before']:
                raise UpdateError(f"Modification concurrente : {operation['key']}")
            atomic_write(path, operation['after'])
            if snapshot(path) != operation['after']:
                raise UpdateError(f"Vérification échouée : {operation['key']}")
            log(locations, operation['action'] + ' ' + operation['key'])
        manifest['pending_reload'] = services.reload(unit_changed)
        manifest['pending_services'] = services.names if manifest['pending_reload'] else []
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'):
            for command in ('monitors', 'clients'):
                if run(['hyprctl', command], check=False).returncode:
                    print(f'Avertissement : hyprctl {command} indisponible.')
        json_write(locations.manifest, manifest)
        json_write(locations.data / 'version', {'commit': manifest['commit'], 'branch': manifest['branch']})
        if install_state is not None:
            from install_state import write
            write(locations, install_state)
        journal['status'] = 'committed'
        json_write(backup / 'journal.json', journal)
        (locations.state / 'pending.json').unlink(missing_ok=True)
        for name, state in services.states.items():
            if state['active']:
                log(locations, 'SERVICE ' + services.renames.get(name, name))
        log(locations, 'COMMIT STATE réussi')
    except BaseException:
        log(locations, 'ERROR avant COMMIT STATE ; rollback')
        try:
            rollback(locations, backup)
        except Exception as error:
            log(locations, 'ROLLBACK incomplet ; journal conservé')
            print(str(error))
        raise
    backups = sorted((locations.data / 'backups').iterdir())
    for obsolete in backups[:-5]:
        if read_json(obsolete / 'journal.json', {}).get('status') in ('committed', 'rolled_back'):
            shutil.rmtree(obsolete)
    return backup
