CC ?= cc
PKGS := gtk+-3.0 gio-2.0 glib-2.0
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
CFLAGS ?= -O2 -pipe
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
LDLIBS += $(shell pkg-config --libs $(PKGS))

SRC := src/main.c src/ui.c src/paths.c src/component.c src/runner.c
OBJ := $(SRC:.c=.o)
BIN := build/debian-custom-manager

.PHONY: all clean test install uninstall

all: $(BIN)

$(BIN): $(OBJ)
	@mkdir -p build
	$(CC) $(OBJ) $(LDLIBS) -o $@

src/%.o: src/%.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

test:
	bash tests/test-layout.sh
	bash tests/test-components.sh

install: all
	bash scripts/install.sh --skip-build

uninstall:
	bash scripts/uninstall.sh

clean:
	rm -f $(OBJ)
	rm -rf build
