// `make pack` runs this on the staged copies: each file must still parse after the comment strip.
// Parse only, nothing runs: import/export keywords are cut so the body compiles as a plain function.
import GLib from 'gi://GLib';
import System from 'system';

const AsyncFunction = (async () => {}).constructor;
for (const f of System.programArgs) {
    const src = new TextDecoder().decode(GLib.file_get_contents(f)[1])
        .replace(/^import .*$/gm, '').replace(/^export (default )?/gm, '');
    try {
        new AsyncFunction(src);
    } catch (e) {
        printerr(`${f}: ${e.message}`);
        System.exit(1);
    }
}
