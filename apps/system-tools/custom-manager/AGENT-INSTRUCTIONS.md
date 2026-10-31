# Minimal agent task

The architecture and source code are already decided. Do not redesign or refactor them.

1. Copy the provided `manager/` directory exactly to the root of `Debian-Hyprland-Custom`.
2. Do not modify existing project files yet.
3. Run:

```bash
cd manager
bash tests/test-layout.sh
bash tests/test-components.sh
bash -n scripts/install.sh scripts/uninstall.sh tests/*.sh
```

4. If GTK3 development files are already installed, also run:

```bash
make clean all test
./build/debian-custom-manager --diagnose
```

5. If compilation dependencies are missing, report only the missing packages. Do not install or change architecture automatically.
6. Return the exact command output and errors. Do not rewrite any source file unless explicitly instructed.
