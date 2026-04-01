// Package github implements the forge.Client interface for GitHub.
package github

// AppPermissions describes the GitHub App permissions.
type AppPermissions struct {
	Issues   string `json:"issues"`
	PullReqs string `json:"pull_requests"`
	Checks   string `json:"checks"`
	Contents string `json:"contents"`
}

// AppConfig holds the configuration for creating a GitHub App.
type AppConfig struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	URL         string         `json:"url"`
	Permissions AppPermissions `json:"permissions"`
	Events      []string       `json:"events"`
}

// DefaultAppConfig returns the standard GitHub App configuration for fullsend.
func DefaultAppConfig(org string) *AppConfig {
	return &AppConfig{
		Name:        "fullsend-" + org,
		Description: "Autonomous agentic development pipeline for " + org,
		URL:         "https://github.com/fullsend-ai/fullsend",
		Permissions: AppPermissions{
			Issues:   "write",
			PullReqs: "write",
			Checks:   "read",
			Contents: "write",
		},
		Events: []string{
			"issues",
			"issue_comment",
			"pull_request",
			"pull_request_review",
			"check_run",
			"check_suite",
		},
	}
}
