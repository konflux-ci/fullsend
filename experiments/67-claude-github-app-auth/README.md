# PoC FullSend #67

This experiment folder addresses: https://github.com/konflux-ci/fullsend/issues/67

1. Create an app with: contents, pull requests, issues. Make it public so it can be installed on any org.
2. Go to the public URL of the app (available on the setting app page after creating it)
3. Install the app on the org of your chosing.
4. Generate a private PEM key for the app (in its settings page).
5. Generate a JWT using the PEM and the App Client ID.
6. Use the JWT to list installations, get the installation id you want.
7. Generate a short lived access token scoped to the repository that you want using the JWT and the installation ID.
8. Export the token and execute claude.

## Results

Passing GH_TOKEN to the environment when executing the agent be enough.

## Example Output

```
Found 2 installation(s):

Installation ID: 119153102
  Account:     rh-hemartin-konflux (Organization)
  Target type: Organization
  Token:       ghs_4FRsI532... (expires 2026-03-27T11:14:29Z)
  Repositories (2):
    - rh-hemartin-konflux/konflux-test-app (id: 945843843)
      Scoped token: ghs_S9ANYTn2... (expires 2026-03-27T11:14:29Z)
      Launching Claude agent for rh-hemartin-konflux/konflux-test-app...
      Agent output:
        Done! Here's a summary:

        - **Issue created:** https://github.com/rh-hemartin-konflux/konflux-test-app/issues/4
        - **PR opened:** https://github.com/rh-hemartin-konflux/konflux-test-app/pull/5

        The PR adds a description line to the README and references the issue with `Closes #4`, so merging the PR will automatically close the issue.
    - rh-hemartin-konflux/testrepo (id: 945993967)
      Scoped token: ghs_655syxbA... (expires 2026-03-27T11:15:18Z)
      Launching Claude agent for rh-hemartin-konflux/testrepo...
      Agent output:
        All done. Here's what was created:

        - **Issue:** https://github.com/rh-hemartin-konflux/testrepo/issues/20
        - **PR:** https://github.com/rh-hemartin-konflux/testrepo/pull/21 (closes issue #20)

        The PR adds a small "Claude Agent Test" section to the README on branch `claude-agent-test-20`.

Installation ID: 119149070
  Account:     rh-hemartin (User)
  Target type: User
  Token:       ghs_h0W4j49l... (expires 2026-03-27T11:16:11Z)
  Repositories (1):
    - rh-hemartin/nonflux-integration-service (id: 1191345201)
      Scoped token: ghs_KlpL3FSB... (expires 2026-03-27T11:16:11Z)
      Launching Claude agent for rh-hemartin/nonflux-integration-service...
      Agent output:
        All done. Here's a summary:

        1. **Issue created:** https://github.com/rh-hemartin/nonflux-integration-service/issues/7 — "Testing Claude Agent"
        2. **Branch pushed:** `testing-claude-agent-2` with a dummy change adding a "Contributing" section to the README
        3. **PR opened:** https://github.com/nonflux/integration-service/pull/6 — "Add contributing section to README" (references `Closes #7`)

        Note: The PR was opened against the upstream `nonflux/integration-service` repo since your repo is a fork. The `Closes #7` reference points to the issue in your fork. If you'd prefer the PR to target your fork instead, let me know.
```
