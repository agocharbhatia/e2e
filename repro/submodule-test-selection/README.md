# Reproduce missing submodule changes in e2e list

From this checkout's root, use Node 26, pnpm, Python 3, and Git.

```sh
pnpm install --frozen-lockfile
pnpm build
python3 repro/submodule-test-selection/reproduce.py .
```

The script creates temporary Git repos with a catalog submodule. A commit updates the submodule and an ordinary file. The submodule has Git's `ignore = all` setting.

In the JSON output, `reads the catalog` should have disposition `run`. Both tests have disposition `filtered` on the baseline. No browser, credentials, or model are needed.
