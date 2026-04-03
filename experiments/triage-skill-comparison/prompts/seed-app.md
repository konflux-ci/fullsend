# Seed Application Prompt

You are an initialization agent. Your job is to create a minimal but realistic codebase for a fictional web application called **TaskFlow** — a simple task management app. This codebase will be used as the backdrop for a triage experiment, so the code must be real enough that bug reports about it make sense.

## Stack

- **Backend:** Node.js with Express
- **Frontend:** Vanilla JavaScript (no framework)
- **Database:** PostgreSQL
- **Tests:** Basic test file using Node's built-in test runner

## Files to Create

Create the following files with realistic, functional code. The code should be simple and readable — this is a small app, not a production system.

### `package.json`

Standard Node.js package.json. Dependencies: `express`, `pg` (PostgreSQL client), `bcrypt`, `express-session`. Scripts: `start`, `test`, `db:migrate`.

### `server.js`

Express server setup. Mounts route modules, serves static files from `public/`, configures session middleware, connects to PostgreSQL. Listens on `PORT` env var or 3000.

### `routes/tasks.js`

Express router for task CRUD operations:
- `GET /tasks` — list tasks with optional search (query param `q`). Search filters by task title and assignee name.
- `POST /tasks` — create a task. Accepts `title`, `description`, `assignee`, `project_id`.
- `PUT /tasks/:id` — update a task.
- `DELETE /tasks/:id` — delete a task.

**IMPORTANT — include these bugs:**

1. **The 255-character title crash:** In the `POST /tasks` and `PUT /tasks/:id` handlers, there is a utility function `sanitizeTitle(title)` that is supposed to truncate titles to 255 characters. However, the function has a bug: if the input string is longer than 255 characters, a validation step returns `undefined` instead of the string, and then a subsequent `.slice(0, 255)` call on `undefined` throws a `TypeError`. The function should look approximately like this:

```javascript
function sanitizeTitle(title) {
  // Validate title length
  const validated = title.length <= 255 ? title : undefined; // BUG: should return title, not undefined
  // Truncate to max length
  return validated.slice(0, 255); // TypeError when validated is undefined
}
```

2. **The missing search index:** The `GET /tasks` search route performs a query like:
```sql
SELECT * FROM tasks WHERE title ILIKE $1 OR assignee_name ILIKE $1
```
There is no bug in the code itself, but the `db/schema.sql` file does NOT include indexes on `title` or `assignee_name`. Additionally, add a comment in the search handler noting that the v2.4.0 migration was supposed to add these indexes. The code works correctly but will be extremely slow on large datasets.

### `routes/auth.js`

Express router for authentication:
- `POST /auth/login` — email/password login using bcrypt.
- `POST /auth/register` — create account.
- `GET /auth/callback` — OAuth callback handler.

**IMPORTANT — include this bug:**

3. **The OAuth callback proxy bug:** The `GET /auth/callback` handler constructs a redirect URL after successful OAuth authentication. It reads `req.headers.host` to build the redirect URL but does NOT check for `X-Forwarded-Host` or `X-Forwarded-Proto` headers. When the app is behind a reverse proxy (nginx, AWS ALB, etc.), `req.headers.host` returns the internal hostname (e.g., `localhost:3000`) instead of the public hostname, causing an infinite redirect loop. The code should look approximately like:

```javascript
router.get('/auth/callback', async (req, res) => {
  // ... OAuth token exchange ...
  const redirectUrl = `${req.protocol}://${req.headers.host}/dashboard`;
  // BUG: Behind a proxy, req.protocol is 'http' and req.headers.host is 'localhost:3000'
  // instead of 'https' and 'app.example.com'
  res.redirect(redirectUrl);
});
```

### `public/app.js`

Minimal frontend JavaScript:
- Fetches and renders tasks from the API.
- Has a form to create new tasks (title, description, assignee fields).
- Has a search input that calls the search API.
- **No error handling on the fetch calls for task creation** — if the API returns a 500 (from the title crash bug), the UI has no catch block and the page state corrupts silently.

### `db/schema.sql`

PostgreSQL schema:
- `users` table: `id`, `email`, `password_hash`, `name`, `created_at`.
- `projects` table: `id`, `name`, `owner_id`, `created_at`.
- `tasks` table: `id`, `project_id`, `title` (VARCHAR(500) — note: larger than the 255-char validation limit in code), `description`, `assignee_name`, `assignee_id`, `status`, `created_at`, `updated_at`.
- **NO indexes on `tasks.title`, `tasks.assignee_name`, or `tasks.assignee_id`.** This is deliberate — it's the missing index bug.
- Include a comment: `-- TODO: v2.4.0 migration should add indexes on tasks(title), tasks(assignee_name), tasks(project_id, assignee_id, status)`

### `test/tasks.test.js`

Basic tests using Node's built-in `node:test` and `node:assert`:
- Test that creating a task with a valid title succeeds.
- Test that creating a task with a short title (under 255 chars) succeeds.
- **Do NOT include a test for titles over 255 characters** — this is a gap that the triage process should identify.
- Test that search returns matching results.
- Test format only — these can mock the database layer or test the sanitizeTitle function directly.

## Code Style

- Use `const`/`let`, not `var`.
- Use async/await, not callbacks.
- Include brief comments explaining what each section does.
- Keep each file under 100 lines. This is a minimal app.
- Use CommonJS (`require`) not ESM (`import`).

## Output

Create all files listed above with complete, working (modulo the intentional bugs) code. Write each file to the `taskflow/` directory within the experiment workspace.
