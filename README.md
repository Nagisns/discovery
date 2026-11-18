# discovery

A small library for discovering discord.py extension modules in Python packages
and loading them into a bot in order.

## Requirements

- Python 3.15 or later
- discord.py 2.7.1 or later

These are the version requirements declared in `pyproject.toml`.

## Installation

Run the following command from the project root to install the local package:

```sh
python -m pip install .
```

For development, use `python -m pip install -e .` instead.

## Public API

Import `ExtensionManager` from the top-level package:

```python
from discovery import ExtensionManager
```

Both methods are class methods and can be called without creating an instance.
Pass imported Python packages as arguments, rather than strings or directory paths.

### `ExtensionManager.discover_extensions(*packages: ModuleType) -> list[str]`

- Recursively searches the supplied packages and returns fully qualified module names.
- Searches inside subpackages without including the subpackages themselves in the results.
- Skips discovered modules and subpackages whose final name component starts with `_`, including all descendants of skipped subpackages. This filter does not apply to packages passed directly as arguments.
- Does not check for a `setup` function. The traversal itself does not import leaf modules.
- Imports subpackages, executing their `__init__.py` files. These imports may have side effects or raise exceptions.
- Does not discover descendant directories without an `__init__.py` file.
- Sorts the results for each supplied package by fully qualified name, then combines them in argument order. The combined list is not sorted globally.
- Preserves duplicate names when the same package or overlapping parent and child packages are supplied.
- Returns an empty list when called without arguments.
- Raises `TypeError` if an argument is not a `ModuleType`, or if its `__path__` attribute is missing or `None`.
- Propagates exceptions raised while importing subpackages to the caller.

### `await ExtensionManager.load_extensions(bot: commands.Bot, *packages: ModuleType) -> list[str]`

- Collects all module names using `discover_extensions`, then calls `await bot.load_extension(name)` sequentially in that order.
- Does not begin loading extensions if discovery fails. Side effects from imports during discovery are not rolled back.
- Returns the fully qualified module names in loading order only after every extension has loaded successfully.
- Loads nothing and returns an empty list when no packages are supplied.
- Does not skip duplicate names or extensions that are already loaded. If discord.py raises an exception for an already-loaded extension, loading stops at that point.
- Stops at the first loading error and propagates the exception to the caller. Extensions loaded successfully earlier in the call remain loaded. There is no automatic rollback or retry.
- Attempts to load modules even if they have no `setup` function, so supply packages dedicated to extensions.

## Usage

This example assumes your application provides an extension package named `extensions`.

```python
import discord
from discord.ext import commands

import extensions
from discovery import ExtensionManager


class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        await ExtensionManager.load_extensions(self, extensions)


bot = MyBot(command_prefix="!", intents=discord.Intents.default())
```

To discover modules without loading them as extensions, call
`ExtensionManager.discover_extensions(extensions)`.

## Maintenance and support

This project was developed for personal use and is shared as open source under
the MIT License. Ongoing maintenance, compatibility, individual support, security
fixes, and response times are not guaranteed. Issues and pull requests may be
addressed as the author's time permits.

Before adopting this project, review the code and its dependencies and assess
whether they are suitable for your use case.

## Security considerations

Only discover and load extensions from packages you trust. Discovery imports
subpackages and executes their `__init__.py` files; loading extensions executes
their code and setup functions. This library does not sandbox extensions or
check whether their code is safe.

## License

MIT License. See [LICENSE](LICENSE) for the full terms, including the warranty
disclaimer and limitation of liability.
