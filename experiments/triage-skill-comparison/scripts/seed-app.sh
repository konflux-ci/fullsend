#!/usr/bin/env bash
# =============================================================================
# seed-app.sh — Creates the fictional TaskFlow application
# =============================================================================
#
# Generates a minimal but functional Node.js/Express app ("TaskFlow") that
# contains the bugs referenced by the experiment scenarios:
#
#   - crash-on-save:       Title truncation crashes on strings > 255 chars
#   - slow-search:         Missing database indexes after migration
#   - auth-redirect-loop:  OAuth state parameter comparison is encoding-sensitive
#
# The code is intentionally minimal — just enough to demonstrate the bugs.
#
# Arguments:
#   $1  target_dir  — Directory to create the app in (will be created)
#
# Usage:
#   ./scripts/seed-app.sh /tmp/taskflow-app
# =============================================================================

set -euo pipefail

TARGET_DIR="${1:?Usage: $0 target_dir}"

echo "Creating TaskFlow app in: $TARGET_DIR"
mkdir -p "$TARGET_DIR"/{routes,db,public,test,middleware}

# ---------------------------------------------------------------------------
# package.json
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/package.json" << 'EOF'
{
  "name": "taskflow",
  "version": "2.4.0",
  "description": "TaskFlow — a minimal task management app (experiment fixture)",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "test": "node test/tasks.test.js"
  },
  "dependencies": {
    "express": "^4.18.0",
    "better-sqlite3": "^9.0.0",
    "express-session": "^1.17.0"
  }
}
EOF

# ---------------------------------------------------------------------------
# db/schema.sql — Database schema with the migration bug
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/db/schema.sql" << 'EOF'
-- TaskFlow database schema
-- Version 2.4.0 — includes full-text search migration

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  owner_id INTEGER REFERENCES users(id),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER REFERENCES projects(id),
  title TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'open',
  assignee_id INTEGER REFERENCES users(id),
  assignee_name TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- BUG: The v2.4.0 migration was supposed to recreate these indexes after
-- dropping them for the full-text search migration. The migration script
-- ran the DROP INDEX statements but the CREATE INDEX statements silently
-- failed due to a locking conflict during hot migration. The indexes below
-- are commented out to simulate the post-migration state.

-- These indexes SHOULD exist but DON'T after the botched migration:
-- CREATE INDEX idx_tasks_assignee_name ON tasks(assignee_name);
-- CREATE INDEX idx_tasks_assignee_id ON tasks(assignee_id);
-- CREATE INDEX idx_tasks_project_assignee ON tasks(project_id, assignee_id, status);
EOF

# ---------------------------------------------------------------------------
# db/init.js — Database initialization
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/db/init.js" << 'EOF'
const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

function initDatabase(dbPath) {
  const db = new Database(dbPath || ':memory:');
  const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');
  db.exec(schema);
  return db;
}

module.exports = { initDatabase };
EOF

# ---------------------------------------------------------------------------
# server.js — Express app entry point
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/server.js" << 'EOF'
const express = require('express');
const session = require('express-session');
const path = require('path');
const { initDatabase } = require('./db/init');
const tasksRouter = require('./routes/tasks');
const authRouter = require('./routes/auth');

const app = express();
const db = initDatabase();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

app.use(session({
  secret: 'taskflow-dev-secret',
  resave: false,
  saveUninitialized: false,
}));

// Make db available to routes
app.locals.db = db;

app.use('/api/tasks', tasksRouter);
app.use('/auth', authRouter);

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`TaskFlow v2.4.0 running on port ${PORT}`);
});

module.exports = app;
EOF

# ---------------------------------------------------------------------------
# routes/tasks.js — Task CRUD with the title truncation bug
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/routes/tasks.js" << 'EOF'
const express = require('express');
const router = express.Router();

// ---------------------------------------------------------------------------
// BUG: Title validation/truncation utility
//
// This function is supposed to validate and optionally truncate a task title.
// The bug: when the title exceeds 255 characters, validateTitle() returns
// undefined instead of the truncated string. The calling code then tries to
// call .slice() on undefined, causing a TypeError crash.
// ---------------------------------------------------------------------------

function validateTitle(title) {
  if (typeof title !== 'string' || title.length === 0) {
    return null; // clearly invalid
  }
  if (title.length <= 255) {
    return title;
  }
  // BUG: This was supposed to return the truncated title, but the developer
  // forgot the return statement. The function falls off the end and returns
  // undefined for any title exceeding 255 characters.
  title.slice(0, 255);
}

function formatTitle(title) {
  // This assumes validateTitle always returns a string or null.
  // When it returns undefined (the bug), .slice() throws TypeError.
  const validated = validateTitle(title);
  return validated.slice(0, 1).toUpperCase() + validated.slice(1);
}

// GET /api/tasks — List tasks, with optional search
router.get('/', (req, res) => {
  const db = req.app.locals.db;
  const { search, project_id, scope } = req.query;

  let query = 'SELECT * FROM tasks';
  const params = [];

  // BUG: When scope is 'all' (or not specified), no project_id filter is
  // applied. Without the missing indexes, this results in a sequential scan
  // across all tasks — extremely slow on large datasets.
  if (search) {
    if (project_id && scope !== 'all') {
      query += ' WHERE project_id = ? AND (title LIKE ? OR assignee_name LIKE ?)';
      params.push(project_id, `%${search}%`, `%${search}%`);
    } else {
      // Full table scan — no index on assignee_name after migration
      query += ' WHERE title LIKE ? OR assignee_name LIKE ?';
      params.push(`%${search}%`, `%${search}%`);
    }
  }

  try {
    const tasks = db.prepare(query).all(...params);
    res.json(tasks);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// POST /api/tasks — Create a new task
router.post('/', (req, res) => {
  const db = req.app.locals.db;
  const { title, description, project_id, assignee_id, assignee_name } = req.body;

  try {
    // BUG: formatTitle calls validateTitle, which returns undefined for titles
    // > 255 chars, causing a TypeError in formatTitle's .slice() call.
    const formattedTitle = formatTitle(title);

    const stmt = db.prepare(
      'INSERT INTO tasks (title, description, project_id, assignee_id, assignee_name) VALUES (?, ?, ?, ?, ?)'
    );
    const result = stmt.run(formattedTitle, description, project_id, assignee_id, assignee_name);
    res.status(201).json({ id: result.lastInsertRowid });
  } catch (err) {
    // The TypeError from the title bug surfaces here as a 500 error.
    // The client sees "Cannot read properties of undefined (reading 'slice')"
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
EOF

# ---------------------------------------------------------------------------
# routes/auth.js — OAuth flow with the state parameter bug
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/routes/auth.js" << 'EOF'
const express = require('express');
const crypto = require('crypto');
const router = express.Router();

// ---------------------------------------------------------------------------
// BUG: OAuth state parameter comparison
//
// The OAuth flow generates a random state token (base64-encoded), stores it
// in the session, and includes it in the authorization URL. When the OAuth
// provider redirects back, the state parameter is compared against the stored
// value using strict equality (===).
//
// The problem: some corporate proxies (e.g., Zscaler) perform URL
// normalization during SSL inspection, re-encoding characters like '+' to
// '%2B' and '/' to '%2F' in query parameters. Base64 strings commonly
// contain '+' and '/', so the proxy's re-encoding changes the state value.
// The strict comparison then fails, and the auth middleware redirects back
// to /login, creating an infinite loop.
//
// A robust implementation would URL-decode both values before comparing,
// or use base64url encoding (which avoids +, /, and =).
// ---------------------------------------------------------------------------

// Generate a CSRF state token
function generateStateToken() {
  // Standard base64 — contains +, /, and = characters
  return crypto.randomBytes(32).toString('base64');
}

// Login page
router.get('/login', (req, res) => {
  res.send(`
    <h1>TaskFlow Login</h1>
    <a href="/auth/google">Sign in with Google</a>
  `);
});

// Initiate OAuth flow
router.get('/google', (req, res) => {
  const state = generateStateToken();
  req.session.oauthState = state;

  // In a real app, this would redirect to Google's OAuth endpoint.
  // For this fixture, we simulate the redirect URL structure.
  const authUrl = 'https://accounts.google.com/o/oauth2/v2/auth'
    + '?client_id=FAKE_CLIENT_ID'
    + '&redirect_uri=' + encodeURIComponent('http://localhost:3000/auth/google/callback')
    + '&response_type=code'
    + '&scope=openid+email+profile'
    + '&state=' + encodeURIComponent(state);

  res.redirect(authUrl);
});

// OAuth callback
router.get('/google/callback', (req, res) => {
  const { code, state } = req.query;
  const storedState = req.session.oauthState;

  // BUG: Strict comparison of state parameter.
  // If a proxy re-encoded the state in the redirect URL, the received
  // `state` will differ from `storedState` even though they represent
  // the same token. This causes CSRF validation to fail.
  if (!state || !storedState || state !== storedState) {
    // CSRF validation failed — redirect back to login.
    // This creates an infinite loop: login -> Google -> callback -> login -> ...
    console.log('CSRF state mismatch',
      { received: state?.substring(0, 10), stored: storedState?.substring(0, 10) });
    return res.redirect('/auth/login');
  }

  // Clear the state token
  delete req.session.oauthState;

  // In a real app, exchange the code for tokens here.
  // For this fixture, just set a session flag.
  req.session.authenticated = true;
  req.session.user = { email: 'user@example.com', name: 'Test User' };
  res.redirect('/');
});

module.exports = router;
EOF

# ---------------------------------------------------------------------------
# middleware/auth.js — Auth middleware
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/middleware/auth.js" << 'EOF'
function requireAuth(req, res, next) {
  if (req.session && req.session.authenticated) {
    return next();
  }
  res.redirect('/auth/login');
}

module.exports = { requireAuth };
EOF

# ---------------------------------------------------------------------------
# public/index.html — Minimal UI
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/public/index.html" << 'EOF'
<!DOCTYPE html>
<html>
<head>
  <title>TaskFlow</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 2em auto; }
    input, button { padding: 0.5em; margin: 0.25em; }
    .task { border: 1px solid #ccc; padding: 0.5em; margin: 0.5em 0; }
    #search-scope { margin-left: 0.5em; }
    .error { color: red; }
  </style>
</head>
<body>
  <h1>TaskFlow</h1>

  <div id="search-bar">
    <input type="text" id="search-input" placeholder="Search tasks...">
    <select id="search-scope">
      <option value="all">All Projects</option>
      <option value="current">Current Project</option>
    </select>
    <button onclick="searchTasks()">Search</button>
  </div>

  <div id="new-task">
    <h2>New Task</h2>
    <input type="text" id="task-title" placeholder="Task title">
    <textarea id="task-desc" placeholder="Description"></textarea>
    <button onclick="saveTask()">Save</button>
  </div>

  <div id="error-display" class="error"></div>
  <div id="task-list"></div>

  <script src="app.js"></script>
</body>
</html>
EOF

# ---------------------------------------------------------------------------
# public/app.js — Client-side JS
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/public/app.js" << 'EOF'
async function searchTasks() {
  const query = document.getElementById('search-input').value;
  const scope = document.getElementById('search-scope').value;

  const params = new URLSearchParams({ search: query, scope: scope });
  try {
    const res = await fetch(`/api/tasks?${params}`);
    const tasks = await res.json();
    renderTasks(tasks);
  } catch (err) {
    showError('Search failed: ' + err.message);
  }
}

async function saveTask() {
  const title = document.getElementById('task-title').value;
  const description = document.getElementById('task-desc').value;

  try {
    const res = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || 'Save failed');
    }

    document.getElementById('task-title').value = '';
    document.getElementById('task-desc').value = '';
    showError('');
    searchTasks(); // refresh list
  } catch (err) {
    // BUG: When the title > 255 chars, the server returns a 500 with
    // "Cannot read properties of undefined (reading 'slice')"
    // The UI shows a blank white page because this error handler doesn't
    // gracefully handle the crash — it just shows the raw error.
    showError('Save failed: ' + err.message);
  }
}

function renderTasks(tasks) {
  const list = document.getElementById('task-list');
  if (!tasks || tasks.length === 0) {
    list.innerHTML = '<p>No tasks found.</p>';
    return;
  }
  list.innerHTML = tasks.map(t =>
    `<div class="task"><strong>${t.title}</strong><br>${t.description || ''}</div>`
  ).join('');
}

function showError(msg) {
  document.getElementById('error-display').textContent = msg;
}
EOF

# ---------------------------------------------------------------------------
# test/tasks.test.js — Basic tests (some will fail due to bugs)
# ---------------------------------------------------------------------------

cat > "$TARGET_DIR/test/tasks.test.js" << 'EOF'
const assert = require('assert');

// Inline the validateTitle function for unit testing
function validateTitle(title) {
  if (typeof title !== 'string' || title.length === 0) {
    return null;
  }
  if (title.length <= 255) {
    return title;
  }
  // BUG: missing return — returns undefined for titles > 255 chars
  title.slice(0, 255);
}

function formatTitle(title) {
  const validated = validateTitle(title);
  return validated.slice(0, 1).toUpperCase() + validated.slice(1);
}

// Test 1: Normal title works fine
try {
  const result = formatTitle('fix the login page');
  assert.strictEqual(result, 'Fix the login page');
  console.log('PASS: normal title formatting');
} catch (e) {
  console.log('FAIL: normal title formatting -', e.message);
}

// Test 2: Long title should be truncated (this test exposes the bug)
try {
  const longTitle = 'a'.repeat(300);
  const result = formatTitle(longTitle);
  assert.strictEqual(result.length, 255);
  console.log('PASS: long title truncation');
} catch (e) {
  console.log('FAIL: long title truncation -', e.message);
}

// Test 3: Empty title returns null
try {
  const result = validateTitle('');
  assert.strictEqual(result, null);
  console.log('PASS: empty title validation');
} catch (e) {
  console.log('FAIL: empty title validation -', e.message);
}

console.log('\nDone. (Test 2 is expected to fail — it demonstrates the crash-on-save bug.)');
EOF

echo ""
echo "TaskFlow app created in: $TARGET_DIR"
echo ""
echo "Files created:"
find "$TARGET_DIR" -type f | sort | sed "s|$TARGET_DIR/|  |"
echo ""
echo "To test:"
echo "  cd $TARGET_DIR && npm install && npm test"
echo ""
echo "Test 2 (long title) will fail — this is the crash-on-save bug."
