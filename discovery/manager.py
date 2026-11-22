# Copyright (c) 2026 Nagi(Nagisns)
# Licensed under the MIT License.
# See the LICENSE file for details.

import logging
from logging import Logger
from importlib import import_module
from pkgutil import iter_modules
from types import ModuleType
from typing import Any

from discord.ext import commands


logger: Logger = logging.getLogger(__name__)

class ExtensionManager:
    """Manages extension discovery and loading for Python packages."""

    @classmethod
    def _collect_extension_names(cls, package: ModuleType, *, exclude: str | None = None) -> list[str]:
        if not isinstance(package, ModuleType):
            raise TypeError("package must be a Python module")

        paths: Any | None = getattr(package, "__path__", None)

        if paths is None:
            raise TypeError("package must be a Python package")

        if exclude is not None and package.__name__ == exclude:
            logger.debug("Exclude package: %s", package.__name__)
            return []

        discovered: list[str] = []
        for module in iter_modules(paths, prefix=f"{package.__name__}."):
            if module.name.rsplit(".", 1)[-1].startswith("_"):
                continue

            if module.ispkg:
                logger.debug("Importing subpackage %s", module.name)
                discovered.extend(cls._collect_extension_names(import_module(module.name)))
            else:
                discovered.append(module.name)

        return discovered

    @classmethod
    def discover_extensions(cls, *packages: ModuleType, exclude: str | None = None) -> list[str]:
        """Find extension module names in Python packages.

        Subpackages are imported and searched recursively, but are not included
        in the results. Names starting with an underscore are ignored, including
        their descendants. A ``setup`` entry point is not required.

        Repeated or overlapping package arguments produce duplicate names;
        results are not deduplicated. Leaf modules are not imported by the
        traversal itself.

        Subpackage imports execute their ``__init__.py`` files. Directories
        without ``__init__.py`` are not discovered by this traversal.

        With no packages, returns an empty list.

        Parameters
        ----------
        *packages : types.ModuleType
            The imported Python packages to search, in order.
        exclude : str or None, optional
            The fully qualified name of a directly supplied package to skip.
            The recursive search can still reach that package through another
            supplied package. The default is ``None``.

        Returns
        -------
        list of str
            The fully qualified names of the discovered modules,
            sorted alphabetically within each package and combined in argument
            order.

        Raises
        ------
        TypeError
            An argument is not a module, or its ``__path__`` attribute is
            missing or ``None``.
        ImportError
            A subpackage cannot be imported. Other errors raised during
            subpackage initialization also propagate to the caller.
        """
        extensions: list[str] = []
        for package in packages:
            extensions.extend(sorted(cls._collect_extension_names(package, exclude=exclude)))

        return extensions

    @classmethod
    async def load_extensions(cls, bot: commands.Bot, *packages: ModuleType, exclude: str | None = None) -> list[str]:
        """Load extensions into the bot in discovery order.

        ``discover_extensions`` validates the packages and collects all module
        names before loading begins. Each call to ``bot.load_extension`` is
        awaited before the next begins. The first loading error propagates to
        the caller, and extensions loaded earlier in this call remain loaded.

        Parameters
        ----------
        bot : discord.ext.commands.Bot
            The bot into which the extensions are loaded.
        *packages : types.ModuleType
            The imported Python packages to search, in order.
        exclude : str or None, optional
            The fully qualified name of a directly supplied package to skip
            during discovery. Extensions in that package can still be loaded
            if discovery reaches it through another supplied package. The
            default is ``None``.

        Returns
        -------
        list of str
            Fully qualified module names in loading order once all loads succeed.

        Raises
        ------
        TypeError
            A package argument fails validation or ``exclude`` has an invalid
            type.
        discord.ext.commands.ExtensionNotFound
            An extension cannot be found.
        discord.ext.commands.ExtensionAlreadyLoaded
            An extension is already loaded into the bot.
        discord.ext.commands.NoEntryPointError
            An extension does not define a ``setup`` entry point.
        discord.ext.commands.ExtensionFailed
            An extension or its ``setup`` function raises an error during loading.
        """
        if exclude is None:
            extensions: list[str] = cls.discover_extensions(*packages)
        elif isinstance(exclude, str):
            extensions: list[str] = cls.discover_extensions(*packages, exclude=exclude)
        else:
            raise TypeError("exclude must be a string or None")

        for extension in extensions:
            logger.debug("Loading extension %s", extension)
            await bot.load_extension(extension)
            logger.debug("Loaded extension %s", extension)

        return extensions
