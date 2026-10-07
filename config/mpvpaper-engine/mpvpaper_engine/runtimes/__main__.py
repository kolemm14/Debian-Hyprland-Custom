"""Runtime CLI. All mutations go through the existing engine session service."""
import argparse
import json
from ..ipc import EngineClient
from .lwe_runtime import LweRuntime
from .runtime_manager import RuntimeManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('diagnose', 'apply', 'apply-all', 'stop', 'stop-all', 'status', 'restore'))
    parser.add_argument('path', nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--assets-dir')
    parser.add_argument('--fps', type=int, default=30)
    args = parser.parse_args()
    client = EngineClient()
    try:
        if args.action == 'diagnose':
            if not args.path:
                parser.error('a local path is required')
            result = RuntimeManager(lwe=LweRuntime(assets_dir=args.assets_dir)).diagnose(args.path)
        elif args.action == 'apply':
            if not args.path or not args.output:
                parser.error('a local path and --output are required')
            options = {'fps': args.fps}
            if args.assets_dir:
                options['assets_dir'] = args.assets_dir
            result = client.request('play', {'output': args.output, 'wallpaper': args.path, 'options': options})
        elif args.action == 'stop-all':
            result = client.stop('*')
        elif args.action == 'stop':
            result = client.stop(args.output)
        elif args.action == 'status':
            result = client.request('runtime_status', {'output': args.output})
        elif args.action == 'restore':
            result = client.request('runtime_restore', {})
        else:
            result = client.request('apply_all', {})
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
