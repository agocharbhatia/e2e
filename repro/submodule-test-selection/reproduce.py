import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


# Fixture construction

def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=repo, text=True,
    ).strip()


def scenario(root, checkout):
    """Keep the test package and the built CLI on the same checkout."""
    root.mkdir()
    dependency = root / "dependency"
    dependency.mkdir()
    git(dependency, "init", "--quiet")
    (dependency / "catalog.json").write_text('{"version": 1}\n')
    git(dependency, "add", "catalog.json")
    git(dependency, "commit", "--quiet", "-m", "Original catalog")

    app = root / "app"
    app.mkdir()
    git(app, "init", "--quiet")
    git(app, "-c", "protocol.file.allow=always", "submodule", "add", "--quiet",
        str(dependency), "fixtures/catalog")
    git(app, "config", "-f", ".gitmodules", "submodule.fixtures/catalog.ignore", "all")
    (app / ".gitignore").write_text("node_modules/\n")
    (app / "product.txt").write_text("Product docs\n")
    (app / "tests").mkdir()
    (app / "tests/check.e2e.ts").write_text("""import { test } from 'e2e';
test('reads the catalog', async () => {});
test('signs in', async () => {});
""")
    (app / "e2e.config.mjs").write_text("""import { web } from '@e2e-dev/web';
export default {
  tests: 'tests/**/*.e2e.ts',
  targets: [{ engine: web(), app: { url: 'http://127.0.0.1:9' } }],
  filters: [{
    name: 'catalog',
    filter(tests, { changes }) {
      const catalogChanged = changes.files.includes('fixtures/catalog');
      return {
        exclude: Object.fromEntries(
          tests.filter(test => !catalogChanged || test.titlePath.at(-1) !== 'reads the catalog')
            .map(test => [test.id, 'Catalog dependency did not affect this test'])
        )
      };
    }
  }],
};
""")
    packages = app / "node_modules"
    (packages / "@e2e-dev").mkdir(parents=True)
    (packages / "e2e").symlink_to(checkout / "packages/e2e", target_is_directory=True)
    (packages / "@e2e-dev/web").symlink_to(checkout / "packages/web", target_is_directory=True)
    git(app, "add", ".")
    git(app, "commit", "--quiet", "-m", "Register catalog dependency")
    base = git(app, "rev-parse", "HEAD")

    (dependency / "catalog.json").write_text('{"version": 2}\n')
    git(dependency, "add", "catalog.json")
    git(dependency, "commit", "--quiet", "-m", "Update catalog")
    new_catalog = git(dependency, "rev-parse", "HEAD")
    catalog = app / "fixtures/catalog"
    git(catalog, "-c", "protocol.file.allow=always", "fetch", "--quiet", "origin")
    git(catalog, "checkout", "--quiet", "--detach", new_catalog)
    git(app, "add", "--force", "fixtures/catalog")
    (app / "product.txt").write_text("Updated product docs\n")
    git(app, "add", "product.txt")
    git(app, "commit", "--quiet", "-m", "Update the catalog and product docs")
    assert git(app, "diff", "--name-only", base) == "product.txt"
    assert git(app, "diff", "--name-only", "--ignore-submodules=none", base).splitlines() == [
        "fixtures/catalog", "product.txt",
    ]
    return app, base


# End fixture construction

def list_tests(directory, build):
    app, base = scenario(directory, build)
    process = subprocess.run(
        ["node", str(build / "packages/e2e/dist/cli/bin.js"),
         "list", "--changed-since", base, "--reporter", "json"],
        cwd=app, check=True, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "E2E_TELEMETRY_DISABLED": "1"},
    )
    return json.loads(process.stdout)


def main():
    parser = argparse.ArgumentParser(description="Reproduce e2e dropping a catalog submodule from test selection.")
    parser.add_argument("baseline", type=Path, help="built upstream e2e checkout")
    parser.add_argument("patched", type=Path, nargs="?", help="optional built checkout with the fix")
    args = parser.parse_args()
    builds = {"main": args.baseline.resolve()}
    if args.patched is not None:
        builds["patch"] = args.patched.resolve()
    with TemporaryDirectory(prefix="e2e-list-catalog-") as temp:
        output = {
            label: list_tests(Path(temp) / label, build)
            for label, build in builds.items()
        }
    print(json.dumps(output, indent=2))
    if args.patched is not None:
        expected = {"main": ["filtered", "filtered"], "patch": ["run", "filtered"]}
        for variant, summary in output.items():
            statuses = {pair["title"]: pair["disposition"] for pair in summary["pairs"]}
            assert [statuses["reads the catalog"], statuses["signs in"]] == expected[variant]


if __name__ == "__main__":
    main()
