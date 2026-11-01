#!/usr/bin/env bash
# Legacy entry point retained for existing installers and user scripts.
# shellcheck source=core/system/setup.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/system/setup.sh"
