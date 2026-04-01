// Package uninstall removes fullsend from a GitHub organization.
//
// The uninstall process:
//  1. Reads config.yaml from the .fullsend repo to find the app slug
//  2. Checks token scopes to decide API vs browser for repo deletion
//  3. Deletes the .fullsend configuration repository (API or browser)
//  4. Uninstalls the app from the org (browser — API requires app JWT)
//  5. Directs the user to delete the app registration (browser)
package uninstall

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/fullsend-ai/fullsend/internal/config"
	"github.com/fullsend-ai/fullsend/internal/forge"
	"github.com/fullsend-ai/fullsend/internal/ui"
	"gopkg.in/yaml.v3"
)

// Options holds the parameters for an uninstall operation.
type Options struct {
	// Org is the GitHub organization to uninstall fullsend from.
	Org string

	// Yolo skips the confirmation prompt.
	Yolo bool
}

// Prompter reads user input from the terminal.
type Prompter interface {
	// ConfirmWithInput asks the user to type a specific string to confirm.
	ConfirmWithInput(prompt, expected string) (bool, error)

	// WaitForEnter prints a message and blocks until the user presses Enter.
	WaitForEnter(prompt string) error
}

// BrowserOpener opens URLs in the user's browser.
type BrowserOpener interface {
	Open(ctx context.Context, url string) error
}

// Uninstaller performs the fullsend uninstall workflow.
type Uninstaller struct {
	client  forge.Client
	printer *ui.Printer
	prompt  Prompter
	browser BrowserOpener
	token   string
	baseURL string
	webURL  string
}

// Option configures an Uninstaller.
type Option func(*Uninstaller)

// WithBaseURL overrides the GitHub API base URL (for testing).
func WithBaseURL(u string) Option {
	return func(un *Uninstaller) { un.baseURL = u }
}

// WithWebURL overrides the GitHub web base URL (for testing).
func WithWebURL(u string) Option {
	return func(un *Uninstaller) { un.webURL = u }
}

// New creates an Uninstaller.
func New(client forge.Client, printer *ui.Printer, prompt Prompter, browser BrowserOpener, token string, opts ...Option) *Uninstaller {
	un := &Uninstaller{
		client:  client,
		printer: printer,
		prompt:  prompt,
		browser: browser,
		token:   token,
		baseURL: "https://api.github.com",
		webURL:  "https://github.com",
	}
	for _, opt := range opts {
		opt(un)
	}
	return un
}

// Run executes the uninstall workflow.
func (un *Uninstaller) Run(ctx context.Context, opts Options) error {
	un.printer.Banner()
	un.printer.Header(fmt.Sprintf("Uninstalling fullsend from %s", opts.Org))
	un.printer.Blank()

	// Step 0: Verify .fullsend repo exists by reading config
	un.printer.StepStart("Reading configuration from .fullsend repo...")

	agents, err := un.readAgents(ctx, opts.Org)
	if err != nil {
		un.printer.StepFail(fmt.Sprintf("Could not read %s/.fullsend/config.yaml", opts.Org))
		un.printer.Blank()
		un.printer.ErrorBox("Nothing to uninstall",
			fmt.Sprintf("The .fullsend repository does not exist in %s, or its config.yaml\n"+
				"  is missing or unreadable. fullsend does not appear to be installed.\n\n"+
				"  If you need to clean up manually, check:\n"+
				"    %s/organizations/%s/settings/installations\n"+
				"    %s/organizations/%s/settings/apps",
				opts.Org, un.webURL, opts.Org, un.webURL, opts.Org))
		return fmt.Errorf(".fullsend repo not found in %s — nothing to uninstall", opts.Org)
	}

	un.printer.StepDone(fmt.Sprintf("Found %d agent apps:", len(agents)))
	for _, a := range agents {
		un.printer.StepInfo(fmt.Sprintf("  %s: %s", a.Role, a.Slug))
	}

	// Step 1: Confirm with the user (unless --yolo)
	if !opts.Yolo {
		un.printer.Blank()
		un.printer.StepWarn("This will permanently delete:")
		un.printer.StepInfo(fmt.Sprintf("  • The %s/.fullsend repository and all its contents", opts.Org))
		for _, a := range agents {
			un.printer.StepInfo(fmt.Sprintf("  • The %s app installation and registration", a.Slug))
		}
		un.printer.Blank()

		confirmed, confirmErr := un.prompt.ConfirmWithInput(
			fmt.Sprintf("Type the organization name (%s) to confirm: ", opts.Org),
			opts.Org,
		)
		if confirmErr != nil {
			return fmt.Errorf("reading confirmation: %w", confirmErr)
		}
		if !confirmed {
			un.printer.StepInfo("Aborted.")
			return nil
		}
		un.printer.Blank()
	}

	// Step 2: Check token scopes to see if we can delete via API
	un.printer.StepStart("Checking token permissions...")
	scopes := un.checkTokenScopes(ctx)
	hasDeleteRepo := strings.Contains(scopes, "delete_repo")

	if hasDeleteRepo {
		un.printer.StepDone("Token has delete_repo scope")
	} else {
		un.printer.StepInfo("Token does not have delete_repo scope — will use browser for repo deletion")
	}

	// Step 3: Delete the .fullsend repo
	if deleteErr := un.deleteConfigRepo(ctx, opts.Org, hasDeleteRepo); deleteErr != nil {
		_ = deleteErr
	}

	// Step 4: Uninstall and delete each agent app
	for _, agent := range agents {
		un.printer.Header(fmt.Sprintf("Removing %s agent (%s)", agent.Role, agent.Slug))
		un.printer.Blank()

		if uninstallErr := un.uninstallApp(ctx, opts.Org, agent.Slug); uninstallErr != nil {
			_ = uninstallErr
		}

		if deleteErr := un.deleteAppRegistration(ctx, opts.Org, agent.Slug); deleteErr != nil {
			_ = deleteErr
		}
	}

	summaryItems := []string{
		fmt.Sprintf("Deleted: %s/.fullsend", opts.Org),
	}
	for _, a := range agents {
		summaryItems = append(summaryItems,
			fmt.Sprintf("Removed: %s (%s)", a.Slug, a.Role))
	}

	un.printer.Summary("Uninstall complete", summaryItems)

	return nil
}

// deleteConfigRepo deletes the .fullsend repo via API if we have permission,
// otherwise walks the user through doing it in the browser.
func (un *Uninstaller) deleteConfigRepo(ctx context.Context, org string, canDeleteViaAPI bool) error {
	if canDeleteViaAPI {
		un.printer.StepStart("Deleting .fullsend repository...")

		if deleteErr := un.client.DeleteRepo(ctx, org, ".fullsend"); deleteErr != nil {
			un.printer.StepFail(fmt.Sprintf("Failed to delete .fullsend repo: %v", deleteErr))
			un.printer.StepInfo("You may need to delete it manually in your browser.")
			// Fall through to browser flow
		} else {
			un.printer.StepDone("Deleted .fullsend repository")
			return nil
		}
	}

	// Browser flow
	repoURL := fmt.Sprintf("%s/%s/.fullsend/settings", un.webURL, org)

	un.printer.StepInfo("We need you to delete the .fullsend repository in your browser.")
	un.printer.StepInfo("Go to Settings → Danger Zone → Delete this repository.")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] to open the repo settings page..."); promptErr != nil {
		return promptErr
	}

	if openErr := un.browser.Open(ctx, repoURL); openErr != nil {
		un.printer.StepWarn("Could not open browser automatically")
		un.printer.StepInfo(fmt.Sprintf("Open this URL manually: %s", repoURL))
	} else {
		un.printer.StepInfo("Opened repo settings in your browser.")
	}

	un.printer.StepInfo("Delete the repository, then return here.")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] when the repository has been deleted..."); promptErr != nil {
		return promptErr
	}

	un.printer.StepDone("Proceeding with .fullsend repo deleted")
	return nil
}

// uninstallApp walks the user through uninstalling the app from their org
// via the browser. The API endpoint for this requires app-level JWT auth
// which we don't have with a PAT.
func (un *Uninstaller) uninstallApp(ctx context.Context, org, appSlug string) error {
	// Find the installation ID so we can build the right URL
	installations, err := un.listInstallations(ctx, org)
	if err != nil {
		un.printer.StepWarn(fmt.Sprintf("Could not list installations: %v", err))
		un.printer.StepInfo("You may need to uninstall the app manually at:")
		un.printer.StepInfo(fmt.Sprintf("  %s/organizations/%s/settings/installations", un.webURL, org))
		return err
	}

	var installID int
	for _, inst := range installations {
		if inst.AppSlug == appSlug {
			installID = inst.ID
			break
		}
	}

	if installID == 0 {
		un.printer.StepDone(fmt.Sprintf("App %q is not installed on this organization — nothing to uninstall", appSlug))
		return nil
	}

	installURL := fmt.Sprintf("%s/organizations/%s/settings/installations/%d",
		un.webURL, org, installID)

	un.printer.StepInfo(fmt.Sprintf("We need you to uninstall the %s app from your organization.", appSlug))
	un.printer.StepInfo("Click \"Uninstall\" on the app's installation page.")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] to open the app installation page..."); promptErr != nil {
		return promptErr
	}

	if openErr := un.browser.Open(ctx, installURL); openErr != nil {
		un.printer.StepWarn("Could not open browser automatically")
		un.printer.StepInfo(fmt.Sprintf("Open this URL manually: %s", installURL))
	} else {
		un.printer.StepInfo("Opened app installation page in your browser.")
	}

	un.printer.StepInfo("Uninstall the app, then return here.")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] when the app has been uninstalled..."); promptErr != nil {
		return promptErr
	}

	un.printer.StepDone(fmt.Sprintf("Proceeding with %s uninstalled", appSlug))
	return nil
}

// deleteAppRegistration walks the user through deleting the app registration
// via the browser. This is the final cleanup step.
func (un *Uninstaller) deleteAppRegistration(ctx context.Context, org, appSlug string) error {
	// App created under the org lives at /organizations/{org}/settings/apps/{slug}
	appSettingsURL := fmt.Sprintf("%s/organizations/%s/settings/apps/%s/advanced",
		un.webURL, org, appSlug)

	un.printer.StepInfo(fmt.Sprintf("Finally, we need you to delete the %s app registration.", appSlug))
	un.printer.StepInfo("Scroll to \"Danger Zone\" and click \"Delete GitHub App\".")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] to open the app settings page..."); promptErr != nil {
		return promptErr
	}

	if openErr := un.browser.Open(ctx, appSettingsURL); openErr != nil {
		un.printer.StepWarn("Could not open browser automatically")
		un.printer.StepInfo(fmt.Sprintf("Open this URL manually: %s", appSettingsURL))
	} else {
		un.printer.StepInfo("Opened app settings in your browser.")
	}

	un.printer.StepInfo("Delete the app, then return here.")
	un.printer.Blank()

	if promptErr := un.prompt.WaitForEnter("Press [Enter] when the app has been deleted..."); promptErr != nil {
		return promptErr
	}

	un.printer.StepDone(fmt.Sprintf("App %s deleted", appSlug))
	return nil
}

// checkTokenScopes makes a lightweight API call and reads the X-OAuth-Scopes
// response header to determine what the token can do.
func (un *Uninstaller) checkTokenScopes(ctx context.Context) string {
	reqURL := fmt.Sprintf("%s/user", un.baseURL)

	req, err := http.NewRequestWithContext(ctx, http.MethodHead, reqURL, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("Authorization", "Bearer "+un.token)
	req.Header.Set("Accept", "application/vnd.github+json")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return ""
	}
	_ = resp.Body.Close()

	return resp.Header.Get("X-OAuth-Scopes")
}

// readAgents reads the agent entries from .fullsend/config.yaml.
func (un *Uninstaller) readAgents(ctx context.Context, org string) ([]config.AgentEntry, error) {
	data, err := un.client.GetFileContent(ctx, org, ".fullsend", "config.yaml")
	if err != nil {
		return nil, fmt.Errorf("reading config.yaml: %w", err)
	}

	var cfg config.OrgConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parsing config.yaml: %w", err)
	}

	if len(cfg.Agents) == 0 {
		return nil, fmt.Errorf("no agents found in config.yaml")
	}

	return cfg.Agents, nil
}

type orgInstallation struct {
	AppSlug string `json:"app_slug"`
	ID      int    `json:"id"`
}

// listInstallations fetches all app installations for the org.
func (un *Uninstaller) listInstallations(ctx context.Context, org string) ([]orgInstallation, error) {
	reqURL := fmt.Sprintf("%s/orgs/%s/installations?per_page=100",
		un.baseURL, url.PathEscape(org))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+un.token)
	req.Header.Set("Accept", "application/vnd.github+json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 10*1024*1024))
	if err != nil {
		return nil, err
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("listing installations (HTTP %d): %s",
			resp.StatusCode, string(body))
	}

	var result struct {
		Installations []orgInstallation `json:"installations"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("decoding installations: %w", err)
	}

	return result.Installations, nil
}
