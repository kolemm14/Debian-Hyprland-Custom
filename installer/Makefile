.PHONY: build release test clean install deb

build:
	cargo build
	cargo build --manifest-path helper/Cargo.toml

release:
	cargo build --release
	cargo build --release --manifest-path helper/Cargo.toml

test:
	cargo test
	cargo test --manifest-path helper/Cargo.toml

clean:
	cargo clean

install: release
	install -Dm755 target/release/deblestia-installer /usr/bin/deblestia-installer
	install -Dm755 helper/target/release/deblestia-installer-helper /usr/lib/deblestia/deblestia-installer-helper
	install -Dm644 polkit/org.deblestia.installer.policy /usr/share/polkit-1/actions/org.deblestia.installer.policy
	install -Dm644 data/org.deblestia.installer.desktop /usr/share/applications/org.deblestia.installer.desktop

check:
	cargo fmt --check
	cargo clippy --all-targets --all-features -- -D warnings
	cargo test
