package cli

import (
	"bytes"
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestInstallCmd_NoArgs(t *testing.T) {
	cmd := newRootCmd()
	cmd.SetArgs([]string{"install"})

	err := cmd.Execute()
	assert.Error(t, err, "install without args should fail")
}

func TestInstallCmd_DryRun(t *testing.T) {
	cmd := newRootCmd()
	var buf bytes.Buffer
	cmd.SetOut(&buf)
	cmd.SetArgs([]string{"install", "my-org", "--dry-run"})

	err := cmd.Execute()
	require.NoError(t, err)
}

func TestInstallCmd_NoToken(t *testing.T) {
	// Clear all token sources so resolveToken returns empty
	t.Setenv("GH_TOKEN", "")
	t.Setenv("GITHUB_TOKEN", "")
	// gh auth token will also fail (not logged in in test env)

	cmd := newRootCmd()
	cmd.SetArgs([]string{"install", "my-org"})

	err := cmd.Execute()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "no GitHub token found")
}

func TestInstallCmd_Help(t *testing.T) {
	cmd := newInstallCmd()

	assert.Equal(t, "install <org>", cmd.Use)
	assert.Contains(t, cmd.Long, "safe defaults")
	assert.Contains(t, cmd.Long, "Nothing gets automatically merged")
	assert.Contains(t, cmd.Long, "GITHUB_TOKEN")
	assert.Contains(t, cmd.Long, "GH_TOKEN")
	assert.Contains(t, cmd.Long, "gh CLI")
}

func TestResolveToken_GHToken(t *testing.T) {
	t.Setenv("GH_TOKEN", "gh-tok")
	t.Setenv("GITHUB_TOKEN", "github-tok")

	token, source := resolveToken(context.Background())
	assert.Equal(t, "gh-tok", token)
	assert.Equal(t, "GH_TOKEN", source)
}

func TestResolveToken_GitHubToken(t *testing.T) {
	t.Setenv("GH_TOKEN", "")
	t.Setenv("GITHUB_TOKEN", "github-tok")

	token, source := resolveToken(context.Background())
	assert.Equal(t, "github-tok", token)
	assert.Equal(t, "GITHUB_TOKEN", source)
}

func TestResolveToken_None(t *testing.T) {
	t.Setenv("GH_TOKEN", "")
	t.Setenv("GITHUB_TOKEN", "")

	token, source := resolveToken(context.Background())
	// May or may not find gh CLI credentials depending on environment,
	// but at minimum source should be set if token is set
	if token == "" {
		assert.Empty(t, source)
	} else {
		assert.Equal(t, "gh CLI", source)
	}
}

func TestGhAuthToken_NotInstalled(t *testing.T) {
	// ghAuthToken should return empty if gh isn't available or not logged in.
	// We can't easily mock exec.Command, but we can verify it doesn't panic.
	result := ghAuthToken(context.Background())
	// Result depends on whether gh is installed and logged in, but must not panic
	_ = result
}
