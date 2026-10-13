UUID = $(shell sed -n 's/.*"uuid": "\(.*\)".*/\1/p' metadata.json)
ZIP = build/$(UUID).shell-extension.zip
JS = $(filter-out check.js,$(wildcard *.js))
APPS = $(HOME)/.local/share/applications
DESKTOP = interactive-wallpaper.desktop

.PHONY: check pack install uninstall clean

check:
	gjs -m check.js

# Stage only what ships: no blender/, tools/, *.py or self-checks.
pack: check
	rm -rf build && mkdir -p build
	cp metadata.json LICENSE $(JS) build/
	# Tagged commits get a version-name (letters, digits, dots only).
	v=$$(git describe --tags --exact-match 2>/dev/null | sed 's/^v//'); if echo "$$v" | grep -qE '^[A-Za-z0-9.]{1,16}$$'; then sed -i "1a\  \"version-name\": \"$$v\"," build/metadata.json; fi
	mkdir build/schemas && cp schemas/*.gschema.xml build/schemas/
	tar -c --exclude=blender --exclude='*.py' --exclude=__pycache__ --exclude=check.js --exclude=fish-check.js scenes | tar -x -C build
	# Shipped copies drop the `ponytail:` notes (maintainer shortcut markers); each file must still parse.
	find build -name '*.js' -exec sed -i '/^[[:space:]]*\/\/ ponytail:/d; s|[[:space:]]*// ponytail:.*$$||' {} +
	! grep -rn 'ponytail:' build
	gjs -m tools/parse-check.js $$(find build -name '*.js')
	gnome-extensions pack build --force --out-dir=build $(addprefix --extra-source=,$(filter-out extension.js prefs.js,$(JS))) --extra-source=scenes --extra-source=LICENSE

# Also adds "Interactive Wallpaper" to the app search, which opens the settings window.
install: pack
	gnome-extensions install --force $(ZIP)
	mkdir -p $(APPS) && cp tools/$(DESKTOP) $(APPS)/
	-update-desktop-database $(APPS) 2>/dev/null

# disable() puts the user's wallpaper back; restore-wallpaper is the net for when it isn't running.
uninstall:
	-gnome-extensions disable $(UUID)
	glib-compile-schemas schemas
	gjs -m tools/restore-wallpaper.js schemas $(UUID)
	rm -f $(APPS)/$(DESKTOP)
	-update-desktop-database $(APPS) 2>/dev/null
	gnome-extensions uninstall $(UUID)

clean:
	rm -rf build schemas/gschemas.compiled
