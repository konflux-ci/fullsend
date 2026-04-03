//go:build e2e

package admin

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"testing"
	"time"

	gh "github.com/fullsend-ai/fullsend/internal/forge/github"
)

const (
	testOrg            = "halfsend"
	testRepo           = "test-repo"
	lockRepo           = "e2e-lock"
	defaultLockTimeout = 30 * time.Minute
	lockPollInterval   = 1 * time.Minute
	freshLockThreshold = 2 * time.Minute
)

var defaultRoles = []string{"fullsend", "triage", "coder", "review"}

type envConfig struct {
	token           string
	browserStateDir string
	lockTimeout     time.Duration
}

func loadEnvConfig(t *testing.T) envConfig {
	t.Helper()

	token := os.Getenv("E2E_GITHUB_TOKEN")
	if token == "" {
		t.Skip("E2E_GITHUB_TOKEN not set, skipping e2e test")
	}

	browserStateDir := os.Getenv("E2E_BROWSER_STATE_DIR")
	if browserStateDir == "" {
		t.Skip("E2E_BROWSER_STATE_DIR not set, skipping e2e test")
	}

	lockTimeout := defaultLockTimeout
	if v := os.Getenv("E2E_LOCK_TIMEOUT"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			t.Fatalf("invalid E2E_LOCK_TIMEOUT %q: %v", v, err)
		}
		lockTimeout = d
	}

	return envConfig{
		token:           token,
		browserStateDir: browserStateDir,
		lockTimeout:     lockTimeout,
	}
}

func newLiveClient(token string) *gh.LiveClient {
	return gh.New(token)
}

func getRepoCreatedAt(ctx context.Context, token, org, repo string) (time.Time, error) {
	url := fmt.Sprintf("https://api.github.com/repos/%s/%s", org, repo)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return time.Time{}, fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return time.Time{}, fmt.Errorf("fetching repo: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return time.Time{}, fmt.Errorf("unexpected status %d: %s", resp.StatusCode, body)
	}

	var result struct {
		CreatedAt time.Time `json:"created_at"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return time.Time{}, fmt.Errorf("decoding response: %w", err)
	}

	return result.CreatedAt, nil
}
