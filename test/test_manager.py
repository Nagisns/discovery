import sys
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
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

    async def test_load_error_keeps_and_logs_only_successful_extensions(self):
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
        success_logs = [
            (record.levelname, record.getMessage())
            for record in logs.records
            if record.getMessage().startswith("Loaded extension ")
        ]
        self.assertEqual(success_logs, [
            ("DEBUG", "Loaded extension broken_cogs.first"),
            ("DEBUG", "Loaded extension broken_cogs.second"),
        ])

    async def test_discovery_error_prevents_any_extension_from_loading(self):
        valid = self.make_package("valid_cogs", {"first.py": "async def setup(bot): pass"})
        broken = self.make_package("unreadable_cogs", {
            "group/__init__.py": "raise ImportError('subpackage failed to import')",
        })
        bot = await self.make_bot()

        with self.assertRaisesRegex(ImportError, "subpackage failed to import"):
            await ExtensionManager.load_extensions(bot, valid, broken)

        self.assertFalse(bot.extensions)
