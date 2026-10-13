// `make pack` runs this on the staged copies: each file must parse after the comment strip (import/export
// cut so the body compiles as a plain function, nothing runs) and its relative imports must be staged too.
import GLib from 'gi://GLib';
import System from 'system';

const AsyncFunction = (async () => {}).constructor;
for (const f of System.programArgs) {
    const raw = new TextDecoder().decode(GLib.file_get_contents(f)[1]);
    const src = raw.replace(/^import .*$/gm, '').replace(/^export (default )?/gm, '');
    try {
        for (const [, rel] of raw.matchAll(/(?:from |import\()'(\.\.?\/[^']+)'/g)) {
            if (!GLib.file_test(GLib.build_filenamev([GLib.path_get_dirname(f), rel]), GLib.FileTest.EXISTS))
                throw new Error(`imports ${rel}, which is not packed`);
        }
        new AsyncFunction(src);
    } catch (e) {
        printerr(`${f}: ${e.message}`);
        System.exit(1);
    }
}
