# Custom Manager — maintenance instructions

The canonical application source is `apps/system-tools/custom-manager/`.
The historical `manager/` directory remains as a compatibility copy during
this staged migration; do not copy this directory to the repository root.

Do not redesign the application or change its public CLI/GUI behavior as part
of a path migration.

Run from the repository root:

```bash
bash -n apps/system-tools/custom-manager/scripts/*.sh
make -C apps/system-tools/custom-manager clean all test
```

The build requires GCC, Make, pkg-config and GTK3 development headers
(`build-essential pkg-config libgtk-3-dev` on Debian).

The installer must resolve the repository root from its canonical depth and
write the canonical repository path to the user's Manager configuration.
Component data lookup must prefer the canonical path and retain the legacy
`manager/data/components.ini` fallback until the compatibility phase ends.

Never remove the historical directory or claim a test passed unless the
command or CI job was actually executed and its result inspected.
