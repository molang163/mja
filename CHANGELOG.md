# Changelog

This project follows semantic versioning as close as practical. Each release
entry enumerates user‑visible changes since the previous version.  Only
high‑level behaviour and documentation improvements are listed here; refer
to the commit history for fine grained details.

## v1.0 – Consolidated release

This release consolidates all maintenance and patch updates from the 1.0
series.  No new functionality has been added; the focus is on packaging
and documentation clean‑up, improved doctor behaviour, minimal automated
testing and metadata refinements.

* **Packaging and documentation clean‑up** – Updated the `MANIFEST.in`
  to avoid including outdated release notes and resolved warnings about
  missing files during source distribution builds.  Documentation tone
  has been harmonised across files.  Clarified the difference between
  source distributions (zip/tarball/sdist) and wheel distributions:
  the former include full documentation (`CHANGELOG.md`,
  version‑specific release notes, `TEST_MATRIX.md`) while the latter
  contain only the runtime modules and metadata.
* **Doctor command improvements** – Container checks (existence,
  ability to enter and presence of the AUR helper) are now performed
  only when a container is recorded in the state file or at least one
  package is installed from an AUR container.  On fresh installations
  these checks are flagged as *skipped* rather than *missing*, keeping
  the overall health status OK.
* **Minimal automated tests and release checks** – Introduced a small
  suite of smoke tests covering CLI argument parsing, state persistence,
  formatting helpers, state rebuild logic and error JSON output.  Added
  lightweight release pipeline checks to verify that the project can build
  a source distribution and wheel, and that the installed package exposes
  the `mja` command or equivalent entry point.  These tests do not
  replace manual testing but provide basic sanity checks.
* **Metadata refinements** – Added `project.urls` (homepage, repository
  and issue tracker) and expanded classifiers to better reflect the
  tool’s purpose and licensing.  The README now explicitly states that
  the tool is designed for Manjaro and does not guarantee compatibility
  with all Arch derivatives.

## v1.0.0 – First stable release

This release promotes the validated `v0.5.0rc1` candidate to the first
stable version of **mja**. The CLI workflow is considered stable for
public use. Compared with the release candidate, the focus here is on
version finalisation and release packaging rather than new features.

* **Release finalisation**: Unified version identifiers across the code,
  CLI description, packaging metadata and release documents to `1.0.0`.
* **Packaging**: Continued shipping the project with the documentation
  set (`README.md`, `LICENSE`, `CHANGELOG.md`, and `TEST_MATRIX.md`) required for
  end users and downstream packagers.  Prior versions of the release notes
  document are no longer bundled with the distribution to avoid references to
  outdated files.
* **Scope**: GUI functionality remains intentionally out of scope for
  `1.0.0`; this is the stable CLI release.

## v0.5.0rc1 – Release Candidate

This is the first release candidate (rc1) for the `mja` tool.  The core
functionality (search, install, remove, repair, rebuild, list, update and
doctor) remains stable and identical to v0.4.x.  The focus of this
release is on polishing the project for publication:

* **Documentation**: Added a dedicated `CHANGELOG.md` and
  a dedicated release-notes document with a concise summary of changes.  The
  README has been reorganised to clarify installation methods, command
  usage, test matrix and known limitations.  Where applicable, long
  explanations have been moved out of tables into prose to improve
  readability.
* **RC polish**: Addressed final release candidate issues: the `doctor`
  command now reports packages whose exportable artifacts are missing
  on the host (export status `export_missing`), ensuring the overall
  health check reflects this problem.  The `update` command no longer
  re‑executes update commands on failure; instead, it streams the
  initial attempt and returns a concise error message pointing to
  terminal/log output for diagnostics.  Installation instructions in
  the README were updated to clarify that `pip install --no-build-isolation`
  requires a pre‑installed `setuptools` and to avoid hardcoding a
  specific release filename.
* **License**: A `LICENSE` file has been added containing the full
  text of the GNU General Public License version 3 (or any later
  version).  The project is now officially distributed under the
  GPL‑3.0‑or‑later terms, as decided by the maintainer.
* **Test matrix**: Introduced a `TEST_MATRIX.md` file describing a
  minimal but representative set of scenarios to exercise before
  publishing a new release.  This matrix is intended to guide manual
  verification rather than automated test results.
* **Version bump**: Updated the internal version identifiers (`__version__`
  constant, CLI description and `pyproject.toml`) to `0.5.0rc1`.
* **Packaging cleanup**: Ensured no `__pycache__` directories or
  temporary files are included in the source distribution.  Packaging
  now includes the new documentation files and licence.

## v0.4.0 – Consolidation release

This release delivered the first complete workflow for managing AUR
packages in an isolated container on Manjaro.  Highlights include:

* A full set of lifecycle commands: `search`, `install`, `remove`,
  `repair export`, `state rebuild`, `list`, `doctor` and `update`.
* Automatic export of desktop entries or binary wrapper scripts when
  installing packages from the AUR.
* Tighter integration with the host package manager: official
  repository packages continue to be installed on the host using
  `pacman`/`pamac`, while AUR packages are built in a container.
* Improved installation experience: reduced `setuptools` requirement to
  avoid network downloads, added `--no-build-isolation` instructions
  and shipped a console‐script entry point for `mja`.
* Documented installation methods, known limitations and a suggested
  minimal test matrix in the README.

Earlier versions prior to v0.4.0 were experimental and lacked
comprehensive documentation.  They are not listed here.

