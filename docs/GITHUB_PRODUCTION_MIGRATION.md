# Production secrets and release synchronization

Deployment credentials belong only to the protected `production` environment.
It permits the `main` branch and requires approval by `sergeiBogdano`.
Do not put private keys in Git, documentation, or chat.

Migration order:

1. Add the four deployment secrets to `production` and verify the corresponding public keys on both servers.
2. Promote the environment binding to `main`, approve the deployment, and verify its success.
3. Delete obsolete repository-level deployment secrets, including the unused legacy `SSH_PRIVATE_KEY` after confirming no other workflow uses it.
4. Change develop protection to prevent deletion and force pushes while permitting normal updates. Keep all main PR, CI, and owner-only rules.
5. Promote `sync-develop.yml` to main and verify its first execution.

The synchronization workflow merges main ancestry into develop after a release.
It uses the temporary GitHub Actions token, without SSH or production secrets.
It never updates main and refuses to push if the merge changes develop's tree.
Concurrent pushes are handled by fetching and retrying; conflicts require a reviewed PR.
It will fail until develop allows normal updates. Do not bypass existing rules to activate it early.

GitHub Actions token pushes do not start another push CI run. This synchronization
changes only ancestry; normal developer pushes and PRs still run CI. Main retains
required checks before a release is accepted.

Invite collaborators only after repository secrets are removed. Collaborators can
read all branches and work on develop and feature branches. Production releases
remain subject to the owner's main merge and environment approval.
