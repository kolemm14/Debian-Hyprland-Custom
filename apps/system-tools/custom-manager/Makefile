CC ?= cc
PKGS := gtk+-3.0 gio-2.0 glib-2.0
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
CFLAGS ?= -O2 -pipe
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
LDLIBS += $(shell pkg-config --libs $(PKGS)) -lm

CLI_SRC := src/cli.c src/cli_input.c src/cli_render.c src/cli_logo.c src/assistant_router.c
SRC := src/main.c src/ui.c src/paths.c src/component.c src/install_state.c src/runner.c $(CLI_SRC)
OBJ := $(patsubst src/%.c,build/%.o,$(SRC))
BIN := build/debian-custom-manager

.PHONY: all clean test install uninstall

all: $(BIN)

$(BIN): $(OBJ)
	@mkdir -p build
	$(CC) $(OBJ) $(LDLIBS) -o $@

build/%.o: src/%.c $(wildcard src/*.h)
	@mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

build/test-cli: tests/test-cli.c $(filter-out build/main.o build/ui.o,$(OBJ))
	@mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) -Isrc $^ $(LDLIBS) -o $@

test: $(BIN) build/test-cli
	bash tests/test-layout.sh
	bash tests/test-components.sh
	./build/test-cli
	python3 tests/test-cli-pty.py

install: all
	bash scripts/install.sh --skip-build

uninstall:
	bash scripts/uninstall.sh

clean:
	rm -f $(OBJ)
	rm -rf build
