UUID = interactive-wallpaper@lil-klorox
ZIP = $(UUID).shell-extension.zip
JS = $(filter-out check.js,$(wildcard *.js))

.PHONY: check pack install clean

check:
	gjs -m check.js

# Stage only what ships: no blender/, tools/, *.py or self-checks.
pack: check
	rm -rf build && mkdir -p build
	cp metadata.json $(JS) build/
	mkdir build/schemas && cp schemas/*.gschema.xml build/schemas/
	tar -c --exclude=blender --exclude='*.py' --exclude=__pycache__ --exclude=check.js scenes | tar -x -C build
	gnome-extensions pack build --force --out-dir=. $(addprefix --extra-source=,$(filter-out extension.js prefs.js,$(JS))) --extra-source=scenes

install: pack
	gnome-extensions install --force $(ZIP)

clean:
	rm -rf build $(ZIP) schemas/gschemas.compiled
