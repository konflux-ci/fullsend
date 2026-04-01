package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gopkg.in/yaml.v3"
)

func TestNewOrgConfig_Defaults(t *testing.T) {
	repos := []string{"api", "web", "docs"}
	cfg := NewOrgConfig(repos, nil, nil, nil)

	assert.Equal(t, "1", cfg.Version)
	assert.Equal(t, "github-actions", cfg.Dispatch.Platform)
	assert.False(t, cfg.Defaults.AutoMerge, "auto_merge should default to false")
	assert.Equal(t, 2, cfg.Defaults.MaxImplementationRetries)
	assert.Equal(t, DefaultRoles(), cfg.Defaults.Roles)

	// All repos should be listed but disabled
	assert.Len(t, cfg.Repos, 3)
	for _, name := range repos {
		repo, ok := cfg.Repos[name]
		require.True(t, ok, "repo %s should be in config", name)
		assert.False(t, repo.Enabled, "repo %s should be disabled by default", name)
	}
}

func TestNewOrgConfig_EnabledRepos(t *testing.T) {
	repos := []string{"api", "web", "docs"}
	enabled := []string{"api", "docs"}

	cfg := NewOrgConfig(repos, enabled, nil, nil)

	assert.True(t, cfg.Repos["api"].Enabled)
	assert.False(t, cfg.Repos["web"].Enabled)
	assert.True(t, cfg.Repos["docs"].Enabled)
}

func TestNewOrgConfig_CustomRoles(t *testing.T) {
	cfg := NewOrgConfig(nil, nil, []string{"review", "coder"}, nil)

	assert.Equal(t, []string{"review", "coder"}, cfg.Defaults.Roles)
}

func TestNewOrgConfig_EmptyRepos(t *testing.T) {
	cfg := NewOrgConfig(nil, nil, nil, nil)

	assert.Empty(t, cfg.Repos)
	assert.Equal(t, DefaultRoles(), cfg.Defaults.Roles)
}

func TestOrgConfig_EnabledRepos(t *testing.T) {
	cfg := &OrgConfig{
		Repos: map[string]RepoConfig{
			"api":  {Enabled: true},
			"web":  {Enabled: false},
			"docs": {Enabled: true},
			"cli":  {Enabled: false},
		},
	}

	enabled := cfg.EnabledRepos()
	assert.Len(t, enabled, 2)
	assert.Contains(t, enabled, "api")
	assert.Contains(t, enabled, "docs")
}

func TestOrgConfig_EnabledRepos_NoneEnabled(t *testing.T) {
	cfg := &OrgConfig{
		Repos: map[string]RepoConfig{
			"api": {Enabled: false},
			"web": {Enabled: false},
		},
	}

	assert.Empty(t, cfg.EnabledRepos())
}

func TestOrgConfig_Marshal(t *testing.T) {
	agents := []AgentEntry{
		{Role: "triage", Name: "fullsend-myorg-triage", Slug: "fullsend-myorg-triage"},
		{Role: "coder", Name: "fullsend-myorg-coder", Slug: "fullsend-myorg-coder"},
	}
	cfg := NewOrgConfig([]string{"api", "web"}, []string{"api"}, nil, agents)

	data, err := cfg.Marshal()
	require.NoError(t, err)

	// Should have a header comment
	assert.Contains(t, string(data), "# fullsend organization configuration")
	assert.Contains(t, string(data), "https://github.com/fullsend-ai/fullsend")

	// Should be valid YAML after the comments
	var parsed OrgConfig
	err = yaml.Unmarshal(data, &parsed)
	require.NoError(t, err)

	assert.Equal(t, "1", parsed.Version)
	assert.Equal(t, "github-actions", parsed.Dispatch.Platform)
	assert.False(t, parsed.Defaults.AutoMerge)
	assert.True(t, parsed.Repos["api"].Enabled)
	assert.False(t, parsed.Repos["web"].Enabled)

	// Agents should round-trip through YAML
	require.Len(t, parsed.Agents, 2)
	assert.Equal(t, "triage", parsed.Agents[0].Role)
	assert.Equal(t, "fullsend-myorg-triage", parsed.Agents[0].Name)
	assert.Equal(t, "fullsend-myorg-triage", parsed.Agents[0].Slug)
	assert.Equal(t, "coder", parsed.Agents[1].Role)
	assert.Equal(t, "fullsend-myorg-coder", parsed.Agents[1].Name)
	assert.Equal(t, "fullsend-myorg-coder", parsed.Agents[1].Slug)
}

func TestOrgConfig_Validate_Valid(t *testing.T) {
	cfg := NewOrgConfig([]string{"api"}, nil, nil, nil)
	assert.NoError(t, cfg.Validate())
}

func TestOrgConfig_Validate_MissingVersion(t *testing.T) {
	cfg := &OrgConfig{
		Dispatch: DispatchConfig{Platform: "github-actions"},
		Defaults: RepoDefaults{Roles: DefaultRoles()},
	}

	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "version is required")
}

func TestOrgConfig_Validate_InvalidPlatform(t *testing.T) {
	cfg := &OrgConfig{
		Version:  "1",
		Dispatch: DispatchConfig{Platform: "kubernetes"},
		Defaults: RepoDefaults{Roles: DefaultRoles()},
	}

	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "unsupported dispatch platform")
}

func TestOrgConfig_Validate_NegativeRetries(t *testing.T) {
	cfg := &OrgConfig{
		Version:  "1",
		Dispatch: DispatchConfig{Platform: "github-actions"},
		Defaults: RepoDefaults{
			MaxImplementationRetries: -1,
			Roles:                    DefaultRoles(),
		},
	}

	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "max_implementation_retries must be non-negative")
}

func TestOrgConfig_Validate_InvalidRole(t *testing.T) {
	cfg := &OrgConfig{
		Version:  "1",
		Dispatch: DispatchConfig{Platform: "github-actions"},
		Defaults: RepoDefaults{
			Roles: []string{"triage", "foobar"},
		},
	}

	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "unknown agent role")
}

func TestOrgConfig_Validate_InvalidRoleInRepo(t *testing.T) {
	cfg := &OrgConfig{
		Version:  "1",
		Dispatch: DispatchConfig{Platform: "github-actions"},
		Defaults: RepoDefaults{
			Roles: DefaultRoles(),
		},
		Repos: map[string]RepoConfig{
			"api": {Roles: []string{"badrole"}, Enabled: true},
		},
	}

	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "unknown agent role")
}

func TestNewOrgConfig_AgentEntries(t *testing.T) {
	agents := []AgentEntry{
		{Role: "triage", Name: "fullsend-org-triage", Slug: "fullsend-org-triage"},
		{Role: "coder", Name: "fullsend-org-coder", Slug: "fullsend-org-coder"},
		{Role: "review", Name: "fullsend-org-review", Slug: "fullsend-org-review"},
	}

	cfg := NewOrgConfig(nil, nil, nil, agents)

	require.Len(t, cfg.Agents, 3)
	assert.Equal(t, "triage", cfg.Agents[0].Role)
	assert.Equal(t, "fullsend-org-triage", cfg.Agents[0].Name)
	assert.Equal(t, "fullsend-org-triage", cfg.Agents[0].Slug)
	assert.Equal(t, "coder", cfg.Agents[1].Role)
	assert.Equal(t, "review", cfg.Agents[2].Role)
}

func TestOrgConfig_AgentSlugs(t *testing.T) {
	cfg := &OrgConfig{
		Agents: []AgentEntry{
			{Role: "triage", Name: "triage-app", Slug: "triage-slug"},
			{Role: "coder", Name: "coder-app", Slug: "coder-slug"},
		},
	}

	slugs := cfg.AgentSlugs()
	assert.Equal(t, []string{"triage-slug", "coder-slug"}, slugs)
}

func TestOrgConfig_AgentSlugs_Empty(t *testing.T) {
	cfg := &OrgConfig{}

	slugs := cfg.AgentSlugs()
	assert.Empty(t, slugs)
}

func TestDefaultRoles(t *testing.T) {
	assert.Equal(t, []string{"triage", "coder", "review"}, DefaultRoles())
}

func TestValidRoles(t *testing.T) {
	valid := ValidRoles()

	assert.True(t, valid["triage"])
	assert.True(t, valid["coder"])
	assert.True(t, valid["review"])
	assert.False(t, valid["implementation"])
	assert.False(t, valid["foobar"])
}
