// Package config defines the fullsend configuration types and defaults.
//
// The primary configuration lives in a .fullsend repo within the target
// GitHub organization as config.yaml. This package handles both the
// generation of initial configs and the (future) reading of existing ones.
package config

import (
	"fmt"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// OrgConfig is the top-level configuration stored in .fullsend/config.yaml.
type OrgConfig struct {
	// Repos holds per-repository configuration overrides.
	Repos map[string]RepoConfig `yaml:"repos"`

	// Agents lists the GitHub Apps created for each agent role.
	// Each agent has its own app with role-specific permissions.
	Agents []AgentEntry `yaml:"agents"`

	// Version of the config schema.
	Version string `yaml:"version"`

	// Dispatch configures the execution platform for agents.
	Dispatch DispatchConfig `yaml:"dispatch"`

	// Defaults apply to all repos unless overridden.
	Defaults RepoDefaults `yaml:"defaults"`
}

// AgentEntry records a GitHub App created for a specific agent role.
type AgentEntry struct {
	// Role is the agent role (triage, coder, review).
	Role string `yaml:"role"`

	// Name is the display name of the GitHub App.
	Name string `yaml:"name"`

	// Slug is the URL-friendly identifier (used in installation URLs).
	Slug string `yaml:"slug"`
}

// DispatchConfig specifies the agent execution platform.
type DispatchConfig struct {
	// Platform is the execution backend. Currently only "github-actions" is supported.
	Platform string `yaml:"platform"`
}

// RepoDefaults provides default settings applied to all repositories.
type RepoDefaults struct {
	// Roles lists which agent roles are enabled by default.
	Roles []string `yaml:"roles"`

	// MaxImplementationRetries caps implement-test loop iterations.
	MaxImplementationRetries int `yaml:"max_implementation_retries"`

	// AutoMerge controls whether agents can merge PRs automatically.
	AutoMerge bool `yaml:"auto_merge"`
}

// RepoConfig holds per-repository settings.
type RepoConfig struct {
	// Roles overrides the default role list for this repository.
	// If empty, the org defaults are used.
	Roles []string `yaml:"roles,omitempty"`

	// Enabled controls whether fullsend operates on this repository.
	Enabled bool `yaml:"enabled"`
}

// DefaultRoles returns the standard set of agent roles.
func DefaultRoles() []string {
	return []string{"triage", "coder", "review"}
}

// ValidRoles returns the set of recognized agent roles.
func ValidRoles() map[string]bool {
	return map[string]bool{"triage": true, "coder": true, "review": true}
}

// NewOrgConfig creates a new OrgConfig with safe defaults.
// All discovered repos are listed but disabled by default.
// agents is the list of AgentEntry structs from the app creation flow.
// roles is the list of role names to enable in defaults.
func NewOrgConfig(repos []string, enabledRepos []string, roles []string, agents []AgentEntry) *OrgConfig {
	if len(roles) == 0 {
		roles = DefaultRoles()
	}

	enabledSet := make(map[string]bool, len(enabledRepos))
	for _, r := range enabledRepos {
		enabledSet[r] = true
	}

	repoConfigs := make(map[string]RepoConfig, len(repos))
	for _, r := range repos {
		repoConfigs[r] = RepoConfig{
			Enabled: enabledSet[r],
		}
	}

	return &OrgConfig{
		Version: "1",
		Agents:  agents,
		Dispatch: DispatchConfig{
			Platform: "github-actions",
		},
		Defaults: RepoDefaults{
			AutoMerge:                false,
			MaxImplementationRetries: 2,
			Roles:                    roles,
		},
		Repos: repoConfigs,
	}
}

// Marshal serializes the config to YAML with a descriptive header comment.
func (c *OrgConfig) Marshal() ([]byte, error) {
	data, err := yaml.Marshal(c)
	if err != nil {
		return nil, fmt.Errorf("marshalling config: %w", err)
	}

	header := `# fullsend organization configuration
# https://github.com/fullsend-ai/fullsend
#
# This file controls how fullsend operates across your organization.
# Edit repo entries to enable/disable agent processing per repository.
# See docs at https://github.com/fullsend-ai/fullsend for details.
`
	return []byte(header + string(data)), nil
}

// Validate checks the config for common errors.
func (c *OrgConfig) Validate() error {
	if c.Version == "" {
		return fmt.Errorf("version is required")
	}

	validPlatforms := map[string]bool{"github-actions": true}
	if !validPlatforms[c.Dispatch.Platform] {
		return fmt.Errorf("unsupported dispatch platform: %q (supported: %s)",
			c.Dispatch.Platform, strings.Join(keys(validPlatforms), ", "))
	}

	if c.Defaults.MaxImplementationRetries < 0 {
		return fmt.Errorf("max_implementation_retries must be non-negative, got %d",
			c.Defaults.MaxImplementationRetries)
	}

	validRoles := ValidRoles()
	for _, r := range c.Defaults.Roles {
		if !validRoles[r] {
			return fmt.Errorf("unknown agent role %q (valid: %s)",
				r, strings.Join(keys(validRoles), ", "))
		}
	}

	for repoName, repo := range c.Repos {
		for _, r := range repo.Roles {
			if !validRoles[r] {
				return fmt.Errorf("repo %q: unknown agent role %q (valid: %s)",
					repoName, r, strings.Join(keys(validRoles), ", "))
			}
		}
	}

	return nil
}

// EnabledRepos returns the list of repos that have enabled: true.
func (c *OrgConfig) EnabledRepos() []string {
	var enabled []string
	for name, repo := range c.Repos {
		if repo.Enabled {
			enabled = append(enabled, name)
		}
	}
	return enabled
}

// AgentSlugs returns the slug for each agent entry.
func (c *OrgConfig) AgentSlugs() []string {
	slugs := make([]string, len(c.Agents))
	for i, a := range c.Agents {
		slugs[i] = a.Slug
	}
	return slugs
}

func keys(m map[string]bool) []string {
	result := make([]string, 0, len(m))
	for k := range m {
		result = append(result, k)
	}
	sort.Strings(result)
	return result
}
