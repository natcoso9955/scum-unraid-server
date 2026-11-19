# Changes versus the previous publishing kit

1. GitHub Actions `publish` job now executes **only for pushed `v*` Git tags**. `workflow_dispatch` runs the tests without publishing a surprise `main` tag.
2. Added `compare-working-source.ps1`: compares the exact running project archive with the release candidate using SHA-256, prints `git diff` where available, and **never overwrites files**. Dockerfile/Compose differences may be intentional release changes; review, do not blindly replace.
3. Added `LICENSE.MIT-REPLACE-HOLDER.txt`: before publication, replace the placeholder copyright name, confirm you have rights to license all included source, rename it to `LICENSE`, and delete `LICENSE-DECISION-REQUIRED.txt`.

The working archive from Lupus is not bundled. Reconciliation remains **pending** until you supply it or run the comparison and review differences. Do not tag/publish until reconciled.
