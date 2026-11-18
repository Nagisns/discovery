# Changelog

Notable changes to this project are documented here.

## v1.0.0 - 2026-11-18

Initial release.

### Added

- Public `ExtensionManager` API, available through `from discovery import ExtensionManager`.
- Recursive discovery of extension modules in imported Python packages, excluding discovered names that start with `_` and their descendants.
- Module names sorted within each supplied package and combined in argument order, with duplicate names preserved.
- Sequential asynchronous loading of discovered extensions into a discord.py bot. Loading stops at the first error, preserving extensions already loaded successfully.
- Type annotations and a `py.typed` marker.
- Documentation covering API behavior, usage, maintenance policy, and security considerations.
- MIT license.

### Requirements

- Python 3.15 or later.
- discord.py 2.7.1 or later.
