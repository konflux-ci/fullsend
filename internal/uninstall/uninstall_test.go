package uninstall

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/fullsend-ai/fullsend/internal/config"
	"github.com/fullsend-ai/fullsend/internal/forge"
	"github.com/fullsend-ai/fullsend/internal/ui"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const testInstallationsPath = "/orgs/my-org/installations"

type fakePrompter struct {
	prompts          []string
	confirmResponses []bool
	confirmIdx       int
}

func (f *fakePrompter) ConfirmWithInput(prompt, _ string) (bool, error) {
	f.prompts = append(f.prompts, prompt)
	if f.confirmIdx < len(f.confirmResponses) {
		r := f.confirmResponses[f.confirmIdx]
		f.confirmIdx++
		return r, nil
	}
	return true, nil
}

func (f *fakePrompter) WaitForEnter(prompt string) error {
	f.prompts = append(f.prompts, prompt)
	return nil
}

type fakeBrowser struct {
	opened []string
}

func (f *fakeBrowser) Open(_ context.Context, url string) error {
	f.opened = append(f.opened, url)
	return nil
}

func scopeServer(scopes string, apps ...map[string]any) *httptest.Server {
	if len(apps) == 0 {
		apps = []map[string]any{
			{"app_slug": "fullsend-my-org-triage", "id": 42},
			{"app_slug": "fullsend-my-org-coder", "id": 43},
		}
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		if r.URL.Path == "/user" {
			w.Header().Set("X-OAuth-Scopes", scopes)
			w.WriteHeader(http.StatusOK)
			_, _ = fmt.Fprint(w, `{"login":"test"}`)
			return
		}

		if r.URL.Path == testInstallationsPath {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"installations": apps,
			})
			return
		}

		w.WriteHeader(http.StatusNotFound)
		_, _ = fmt.Fprint(w, `{"message":"Not Found"}`)
	}))
}

const twoAgentConfig = "version: '1'\nagents:\n- role: triage\n  name: fullsend-my-org-triage\n  slug: fullsend-my-org-triage\n- role: coder\n  name: fullsend-my-org-coder\n  slug: fullsend-my-org-coder\n"
const oneAgentConfig = "version: '1'\nagents:\n- role: review\n  name: my-app-review\n  slug: my-app-review\n"

func newTestUninstaller(t *testing.T, client *forge.FakeClient, apiSrv *httptest.Server, confirmed bool) (*Uninstaller, *bytes.Buffer, *fakeBrowser) {
	t.Helper()

	var buf bytes.Buffer
	printer := ui.NewPrinter(&buf)

	prompt := &fakePrompter{confirmResponses: []bool{confirmed}}
	browser := &fakeBrowser{}

	var opts []Option
	if apiSrv != nil {
		opts = append(opts, WithBaseURL(apiSrv.URL))
	}
	opts = append(opts, WithWebURL("https://github.com"))

	un := New(client, printer, prompt, browser, "test-token", opts...)
	return un, &buf, browser
}

func TestUninstall_FullFlowWithDeleteScope(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, err)

	apiSrv := scopeServer("repo, delete_repo, admin:org")
	defer apiSrv.Close()

	un, output, browser := newTestUninstaller(t, client, apiSrv, true)

	runErr := un.Run(context.Background(), Options{Org: "my-org"})
	require.NoError(t, runErr)

	assert.Contains(t, output.String(), "fullsend-my-org-triage")
	assert.Contains(t, output.String(), "fullsend-my-org-coder")
	assert.Contains(t, output.String(), "Deleted .fullsend repository")
	assert.Len(t, client.DeletedRepos, 1)
	assert.Contains(t, output.String(), "Uninstall complete")

	// Browser should open installation page for each agent
	foundTriage := false
	foundCoder := false
	for _, url := range browser.opened {
		if url == "https://github.com/organizations/my-org/settings/installations/42" {
			foundTriage = true
		}
		if url == "https://github.com/organizations/my-org/settings/installations/43" {
			foundCoder = true
		}
	}
	assert.True(t, foundTriage, "should open installation page for triage agent")
	assert.True(t, foundCoder, "should open installation page for coder agent")
}

func TestUninstall_NoDeleteScope_UsesBrowser(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, err)

	apiSrv := scopeServer("repo, admin:org") // no delete_repo
	defer apiSrv.Close()

	un, output, browser := newTestUninstaller(t, client, apiSrv, true)

	runErr := un.Run(context.Background(), Options{Org: "my-org"})
	require.NoError(t, runErr)

	// Should NOT have deleted via API
	assert.Empty(t, client.DeletedRepos)
	// Should have opened repo settings in browser
	foundRepoSettings := false
	for _, url := range browser.opened {
		if url == "https://github.com/my-org/.fullsend/settings" {
			foundRepoSettings = true
		}
	}
	assert.True(t, foundRepoSettings, "should open repo settings page in browser")
	assert.Contains(t, output.String(), "delete_repo scope")
}

func TestUninstall_Aborted(t *testing.T) {
	client := forge.NewFakeClient()
	createErr := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, createErr)

	apiSrv := scopeServer("")
	defer apiSrv.Close()

	un, output, _ := newTestUninstaller(t, client, apiSrv, false)

	err := un.Run(context.Background(), Options{Org: "my-org"})
	require.NoError(t, err)

	assert.Contains(t, output.String(), "Aborted")
	assert.Empty(t, client.DeletedRepos)
}

func TestUninstall_Yolo(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(oneAgentConfig))
	require.NoError(t, err)

	apiSrv := scopeServer("repo, delete_repo", map[string]any{"app_slug": "my-app-review", "id": 99})
	defer apiSrv.Close()

	un, _, _ := newTestUninstaller(t, client, apiSrv, false)

	runErr := un.Run(context.Background(), Options{Org: "my-org", Yolo: true})
	require.NoError(t, runErr)

	assert.Len(t, client.DeletedRepos, 1)
}

func TestUninstall_NoConfigRepo_Aborts(t *testing.T) {
	client := forge.NewFakeClient()
	client.Errors["GetFileContent"] = errors.New("not found")

	apiSrv := scopeServer("repo, delete_repo")
	defer apiSrv.Close()

	un, output, _ := newTestUninstaller(t, client, apiSrv, true)

	err := un.Run(context.Background(), Options{Org: "my-org", Yolo: true})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "nothing to uninstall")
	assert.Contains(t, output.String(), "Nothing to uninstall")
	// Should NOT have tried to delete anything
	assert.Empty(t, client.DeletedRepos)
}

func TestUninstall_AppInstallBrowser(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, err)

	apiSrv := scopeServer("repo, delete_repo",
		map[string]any{"app_slug": "fullsend-my-org-triage", "id": 42},
		map[string]any{"app_slug": "fullsend-my-org-coder", "id": 43},
	)
	defer apiSrv.Close()

	un, _, browser := newTestUninstaller(t, client, apiSrv, true)

	runErr := un.Run(context.Background(), Options{Org: "my-org", Yolo: true})
	require.NoError(t, runErr)

	// Should have opened the installation page for each agent
	foundTriage := false
	foundCoder := false
	for _, url := range browser.opened {
		if url == "https://github.com/organizations/my-org/settings/installations/42" {
			foundTriage = true
		}
		if url == "https://github.com/organizations/my-org/settings/installations/43" {
			foundCoder = true
		}
	}
	assert.True(t, foundTriage, "should open installation page for triage agent")
	assert.True(t, foundCoder, "should open installation page for coder agent")
}

func TestUninstall_AppSettingsURL(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "my-org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, err)

	apiSrv := scopeServer("repo, delete_repo",
		map[string]any{"app_slug": "fullsend-my-org-triage", "id": 42},
		map[string]any{"app_slug": "fullsend-my-org-coder", "id": 43},
	)
	defer apiSrv.Close()

	un, _, browser := newTestUninstaller(t, client, apiSrv, true)

	runErr := un.Run(context.Background(), Options{Org: "my-org", Yolo: true})
	require.NoError(t, runErr)

	// Should open org-scoped app settings URL for each agent
	foundTriageSettings := false
	foundCoderSettings := false
	for _, url := range browser.opened {
		if url == "https://github.com/organizations/my-org/settings/apps/fullsend-my-org-triage/advanced" {
			foundTriageSettings = true
		}
		if url == "https://github.com/organizations/my-org/settings/apps/fullsend-my-org-coder/advanced" {
			foundCoderSettings = true
		}
	}
	assert.True(t, foundTriageSettings, "should open org-scoped app settings page for triage agent")
	assert.True(t, foundCoderSettings, "should open org-scoped app settings page for coder agent")
}

func TestReadAgents(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "org", ".fullsend", "config.yaml", "init",
		[]byte(twoAgentConfig))
	require.NoError(t, err)

	var buf bytes.Buffer
	un := New(client, ui.NewPrinter(&buf), nil, nil, "tok")

	agents, readErr := un.readAgents(context.Background(), "org")
	require.NoError(t, readErr)
	require.Len(t, agents, 2)

	assert.Equal(t, config.AgentEntry{Role: "triage", Name: "fullsend-my-org-triage", Slug: "fullsend-my-org-triage"}, agents[0])
	assert.Equal(t, config.AgentEntry{Role: "coder", Name: "fullsend-my-org-coder", Slug: "fullsend-my-org-coder"}, agents[1])
}

func TestReadAgents_Empty(t *testing.T) {
	client := forge.NewFakeClient()
	err := client.CreateFile(context.Background(), "org", ".fullsend", "config.yaml", "init",
		[]byte("version: '1'\n"))
	require.NoError(t, err)

	var buf bytes.Buffer
	un := New(client, ui.NewPrinter(&buf), nil, nil, "tok")

	_, readErr := un.readAgents(context.Background(), "org")
	assert.Error(t, readErr)
	assert.Contains(t, readErr.Error(), "no agents")
}

func TestCheckTokenScopes(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-OAuth-Scopes", "repo, delete_repo, admin:org")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	var buf bytes.Buffer
	un := New(nil, ui.NewPrinter(&buf), nil, nil, "tok", WithBaseURL(srv.URL))

	scopes := un.checkTokenScopes(context.Background())
	assert.Contains(t, scopes, "delete_repo")
	assert.Contains(t, scopes, "repo")
}
