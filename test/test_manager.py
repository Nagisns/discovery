import sys
import unittest
from importlib import import_module, invalidate_caches
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import patch

import discord
from discord.ext import commands

from discovery import ExtensionManager


class ExtensionManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(sys, "path", [str(self.root), *sys.path]))
        self.enterContext(patch.dict(sys.modules))

    def make_package(self, name: str, files: dict[str, str]) -> ModuleType:
        package = self.root / name
        package.mkdir()
        (package / "__init__.py").touch()
        for relative_path, source in files.items():
            path = package / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        invalidate_caches()
        return import_module(name)

    async def make_bot(self) -> commands.Bot:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none(), help_command=None)
        return await self.enterAsyncContext(bot)

    def test_discovery_finds_only_public_modules_in_package_order(self):
        first = self.make_package("z_cogs", {
            "zeta.py": "raise AssertionError('discovery imported a leaf module')",
            "group/__init__.py": "",
            "group/alpha.py": "",
            "_private.py": "",
            "_hidden/__init__.py": "raise AssertionError('private package imported')",
            "_hidden/child.py": "",
        })
        second = self.make_package("a_cogs", {"beta.py": ""})

        self.assertEqual(
            ExtensionManager.discover_extensions(first, second),
            ["z_cogs.group.alpha", "z_cogs.zeta", "a_cogs.beta"],
        )

    def test_discovery_logs_subpackage_before_importing_it(self):
        package = self.make_package("logged_cogs", {
            "group/__init__.py": (
                "import logging\n"
                "logging.getLogger('discovery.manager').debug('Subpackage initializer ran')\n"
            ),
        })

        with self.assertLogs("discovery.manager", level="DEBUG") as logs:
            ExtensionManager.discover_extensions(package)

        expected_logs = [
            "DEBUG:discovery.manager:Importing subpackage logged_cogs.group",
            "DEBUG:discovery.manager:Subpackage initializer ran",
        ]
        relevant_logs = [message for message in logs.output if message in expected_logs]
        self.assertEqual(relevant_logs, expected_logs)

    def test_discovery_preserves_duplicates_in_argument_order_for_overlapping_packages(self):
        cogs = self.make_package("cogs", {
            "admin/__init__.py": "",
            "admin/ban.py": "",
            "music.py": "",
        })
        admin = import_module("cogs.admin")

        self.assertEqual(
            ExtensionManager.discover_extensions(cogs, admin),
            ["cogs.admin.ban", "cogs.music", "cogs.admin.ban"],
        )

    def test_discovery_skips_excluded_package_before_importing_subpackages(self):
        excluded = self.make_package("excluded_cogs", {
            "group/__init__.py": "raise AssertionError('excluded subpackage imported')",
        })
        included = self.make_package("included_cogs", {"active.py": ""})

        self.assertEqual(
            ExtensionManager.discover_extensions(excluded, included, exclude="excluded_cogs"),
            ["included_cogs.active"],
        )

    def test_discovery_excludes_only_direct_arguments_by_fully_qualified_name(self):
        cogs = self.make_package("cogs", {
            "admin/__init__.py": "",
            "admin/ban.py": "",
        })
        admin = import_module("cogs.admin")

        self.assertEqual(
            ExtensionManager.discover_extensions(cogs, admin, exclude="cogs.admin"),
            ["cogs.admin.ban"],
        )
        self.assertEqual(
            ExtensionManager.discover_extensions(admin, exclude="admin"),
            ["cogs.admin.ban"],
        )

    def test_discovery_validates_packages_before_excluding_them(self):
        name = "invalid_cogs"
        invalid_packages = (None, SimpleNamespace(__name__=name), ModuleType(name))

        for package in invalid_packages:
            with self.subTest(package=package):
                with self.assertRaises(TypeError):
                    # Pass the original value to test runtime validation.
                    ExtensionManager.discover_extensions(
                        cast(ModuleType, package), exclude=name
                    )

    async def test_loading_waits_for_each_extension_in_order(self):
        package = self.make_package("ordered_cogs", {
            "first.py": (
                "import asyncio\n"
                "async def setup(bot):\n"
                "    await asyncio.sleep(0)"
            ),
            "second.py": (
                "async def setup(bot):\n"
                "    assert 'ordered_cogs.first' in bot.extensions"
            ),
        })
        bot = await self.make_bot()

        loaded = await ExtensionManager.load_extensions(bot, package)

        expected = ["ordered_cogs.first", "ordered_cogs.second"]
        self.assertEqual(loaded, expected)
        self.assertEqual(list(bot.extensions), expected)

    async def test_loading_stops_at_duplicate_extension(self):
        repeated = self.make_package("duplicate_cogs", {
            "first.py": "async def setup(bot): pass",
        })
        unreached = self.make_package("unreached_cogs", {
            "later.py": "async def setup(bot): pass",
        })
        bot = await self.make_bot()

        with self.assertRaises(commands.ExtensionAlreadyLoaded) as error:
            await ExtensionManager.load_extensions(bot, repeated, repeated, unreached)

        self.assertEqual(error.exception.name, "duplicate_cogs.first")
        self.assertEqual(list(bot.extensions), ["duplicate_cogs.first"])

    async def test_load_error_keeps_loaded_extensions_and_logs_the_failed_attempt(self):
        package = self.make_package("broken_cogs", {
            "first.py": "async def setup(bot): pass",
            "second.py": "async def setup(bot): pass",
            "third.py": "",
            "unreached.py": "async def setup(bot): pass",
        })
        bot = await self.make_bot()

        with self.assertLogs("discovery.manager", level="DEBUG") as logs:
            with self.assertRaises(commands.NoEntryPointError) as error:
                await ExtensionManager.load_extensions(bot, package)

        self.assertEqual(error.exception.name, "broken_cogs.third")
        self.assertEqual(list(bot.extensions), ["broken_cogs.first", "broken_cogs.second"])
        load_logs = [
            (record.levelname, record.getMessage())
            for record in logs.records
            if record.getMessage().startswith(("Loading extension ", "Loaded extension "))
        ]
        self.assertEqual(load_logs, [
            ("DEBUG", "Loading extension broken_cogs.first"),
            ("DEBUG", "Loaded extension broken_cogs.first"),
            ("DEBUG", "Loading extension broken_cogs.second"),
            ("DEBUG", "Loaded extension broken_cogs.second"),
            ("DEBUG", "Loading extension broken_cogs.third"),
        ])

    async def test_discovery_error_prevents_any_extension_from_loading(self):
        valid = self.make_package("valid_cogs", {"first.py": "async def setup(bot): pass"})
        broken = self.make_package("unreadable_cogs", {
            "group/__init__.py": "raise ImportError('subpackage failed to import')",
        })
        bot = await self.make_bot()

        with self.assertLogs("discovery.manager", level="DEBUG") as logs:
            with self.assertRaisesRegex(ImportError, "subpackage failed to import"):
                await ExtensionManager.load_extensions(bot, valid, broken)

        self.assertIn(
            "DEBUG:discovery.manager:Importing subpackage unreadable_cogs.group",
            logs.output,
        )
        self.assertFalse(bot.extensions)
