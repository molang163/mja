# Release notes for v1.0

This 1.0 release consolidates all previous patch releases in the 1.0
series.  There are no functional differences compared to earlier
1.0.x versions.  The focus remains on packaging clean‑up,
documentation consistency, and minimal release checks.

## Highlights

* **Packaging clean‑up** – The `MANIFEST.in` has been updated to exclude
  build artefacts such as `__pycache__`, `.pyc` files, `build/`, `dist/`
  and any `*.egg-info` directories.  The source distribution bundles
  the documentation (`CHANGELOG.md`, this `RELEASE_NOTES_v1.0.md`,
  `TEST_MATRIX.md`) along with the source code, while the wheel only
  contains runtime modules and metadata.

* **Documentation alignment** – The README now uses a consistent tone
  and refers to a single 1.0 version.  Instructions clarify how to
  install GUI dependencies on Arch/Manjaro, how to run the GUI via
  `mja-gui` and how to copy the `.desktop` file from the installed
  package into `~/.local/share/applications/` if a menu entry is desired.

* **Minimal automated tests** – A lightweight suite of smoke tests
  checks CLI argument parsing, state persistence, formatting helpers,
  state rebuild logic and JSON error reporting.  Additional checks
  ensure that a source distribution and wheel can be built and that
  the declared entry points (`mja` and `mja-gui`) exist.  These do
  not replace manual testing but catch obvious regressions.

## Migration notes

* There are no changes to the internal state file format compared to
  earlier 1.0.x releases.  Upgrading requires no manual intervention.
* When installing from source, ensure that the `build` module is
  available to run packaging tests; if not present, those tests will
  be skipped.