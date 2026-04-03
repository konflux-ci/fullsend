//go:build e2e

package admin

import (
	"fmt"

	"github.com/playwright-community/playwright-go"
)

// patScopes are the classic PAT scopes needed for e2e tests.
var patScopes = []string{
	"repo",
	"admin:org",
	"delete_repo",
	"workflow",
}

// createPAT creates a classic GitHub Personal Access Token via the browser.
// The token is created with a 7-day expiry and the scopes needed for e2e tests.
// Returns the token string.
func createPAT(page playwright.Page, note string, logf func(string, ...any)) (string, error) {
	url := "https://github.com/settings/tokens/new"
	if _, err := page.Goto(url, playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateDomcontentloaded,
		Timeout:   playwright.Float(7500),
	}); err != nil {
		logf("[pat] Current URL after navigation failure: %s", page.URL())
		return "", fmt.Errorf("navigating to token creation page: %w", err)
	}
	logf("[pat] Navigated to: %s", page.URL())

	// Verify we're on the right page.
	if err := page.Locator("#oauth_access_description").WaitFor(playwright.LocatorWaitForOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		return "", fmt.Errorf("token creation form not found (may not be logged in): %w", err)
	}

	// Fill in the token note/description.
	if err := page.Locator("#oauth_access_description").Fill(note); err != nil {
		return "", fmt.Errorf("filling token note: %w", err)
	}

	// Set expiration to 7 days.
	expirationSelect := page.Locator("#token_expiration")
	if _, err := expirationSelect.SelectOption(playwright.SelectOptionValues{
		Values: playwright.StringSlice("seven_days"),
	}, playwright.LocatorSelectOptionOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		logf("[pat] Warning: could not set expiration, using default: %v", err)
	}

	// Check the required scope checkboxes.
	for _, scope := range patScopes {
		checkbox := page.Locator(fmt.Sprintf("input[type='checkbox'][value='%s']", scope))
		if err := checkbox.Check(); err != nil {
			return "", fmt.Errorf("checking scope %s: %w", scope, err)
		}
	}

	// Click "Generate token".
	generateBtn := page.Locator("button:has-text('Generate token')")
	if err := generateBtn.Click(); err != nil {
		return "", fmt.Errorf("clicking Generate token: %w", err)
	}

	// Wait for the page to load with the new token displayed.
	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateDomcontentloaded,
	}); err != nil {
		return "", fmt.Errorf("waiting for token page to load: %w", err)
	}

	// Extract the token value.
	tokenElement := page.Locator("#new-oauth-token")
	if err := tokenElement.WaitFor(playwright.LocatorWaitForOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		return "", fmt.Errorf("token element not found on page: %w", err)
	}

	token, err := tokenElement.TextContent()
	if err != nil {
		return "", fmt.Errorf("extracting token text: %w", err)
	}

	if token == "" {
		return "", fmt.Errorf("extracted token is empty")
	}

	logf("[pat] Created PAT: %s...%s (note: %s)", token[:4], token[len(token)-4:], note)
	return token, nil
}

// createDispatchPAT creates a fine-grained GitHub Personal Access Token
// scoped to the .fullsend repo with Actions read/write permission.
// This mirrors what the real CLI does in promptDispatchToken — the user
// is guided to create a fine-grained PAT at GitHub's token creation page.
// The e2e test automates the browser interaction instead.
//
// Prerequisites: the .fullsend repo must already exist (the config-repo
// and workflows layers must be installed first, just like the real CLI).
func createDispatchPAT(page playwright.Page, org, screenshotDir string, logf func(string, ...any)) (string, error) {
	// Navigate to the fine-grained PAT creation page with pre-filled params.
	// These match the URL the CLI builds in promptDispatchToken.
	patURL := fmt.Sprintf(
		"https://github.com/settings/personal-access-tokens/new"+
			"?name=fullsend-dispatch-%s-e2e"+
			"&description=E2E+test+dispatch+token+for+%s"+
			"&target_name=%s",
		org, org, org,
	)

	logf("[dispatch-pat] Navigating to fine-grained PAT creation page")
	if _, err := page.Goto(patURL, playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateDomcontentloaded,
		Timeout:   playwright.Float(15000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-goto-failed", logf)
		return "", fmt.Errorf("navigating to fine-grained PAT page: %w", err)
	}
	logf("[dispatch-pat] Page URL: %s", page.URL())

	// Select "Only select repositories" radio button.
	selectReposRadio := page.Locator("input[type='radio'][value='select']")
	if err := selectReposRadio.WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(10000),
	}); err != nil {
		// The radio might be in a shadow DOM or custom element — try clicking the label.
		label := page.Locator("label:has-text('Only select repositories')")
		if labelErr := label.Click(playwright.LocatorClickOptions{
			Timeout: playwright.Float(5000),
		}); labelErr != nil {
			saveDebugScreenshot(page, screenshotDir, "dispatch-pat-select-repos-radio", logf)
			return "", fmt.Errorf("selecting 'Only select repositories': radio=%w, label=%v", err, labelErr)
		}
	} else {
		if err := selectReposRadio.Click(); err != nil {
			saveDebugScreenshot(page, screenshotDir, "dispatch-pat-select-repos-click", logf)
			return "", fmt.Errorf("clicking 'Only select repositories': %w", err)
		}
	}
	logf("[dispatch-pat] Selected 'Only select repositories'")

	// Search for and select the .fullsend repo in the repo picker.
	// The repo picker is typically a combo-box / search input that appears
	// after selecting "Only select repositories".
	repoSearch := page.Locator("input[placeholder*='Search for a repository'], input[aria-label*='Select repositories'], input[placeholder*='repo']")
	if err := repoSearch.First().WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(5000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-repo-search-wait", logf)
		return "", fmt.Errorf("waiting for repository search input: %w", err)
	}
	if err := repoSearch.First().Fill(".fullsend"); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-repo-search-fill", logf)
		return "", fmt.Errorf("typing .fullsend into repo search: %w", err)
	}
	logf("[dispatch-pat] Typed '.fullsend' into repo search")

	// Wait for the dropdown option and click it.
	repoOption := page.Locator("li:has-text('.fullsend'), [role='option']:has-text('.fullsend'), label:has-text('.fullsend')")
	if err := repoOption.First().WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(5000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-repo-option-wait", logf)
		return "", fmt.Errorf("waiting for .fullsend repo option: %w", err)
	}
	if err := repoOption.First().Click(); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-repo-option-click", logf)
		return "", fmt.Errorf("selecting .fullsend repo: %w", err)
	}
	logf("[dispatch-pat] Selected .fullsend repository")

	// Expand the "Repository permissions" section if collapsed.
	repoPermsSection := page.Locator("summary:has-text('Repository permissions'), button:has-text('Repository permissions')")
	if err := repoPermsSection.First().Click(playwright.LocatorClickOptions{
		Timeout: playwright.Float(3000),
	}); err != nil {
		logf("[dispatch-pat] Note: could not expand Repository permissions (may already be open): %v", err)
	}

	// Set Actions permission to "Read and write".
	// GitHub's fine-grained PAT page uses select dropdowns for each permission.
	actionsSelect := page.Locator("select[id*='actions'], select[name*='actions']")
	if err := actionsSelect.First().WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(5000),
	}); err != nil {
		// If the query param pre-filled it, it might not be a visible select.
		// Try to find by label text instead.
		actionsLabel := page.Locator("text=Actions")
		nearbySelect := actionsLabel.Locator("xpath=ancestor::*[contains(@class,'permission')]//select")
		if _, selectErr := nearbySelect.First().SelectOption(playwright.SelectOptionValues{
			Values: playwright.StringSlice("write"),
		}); selectErr != nil {
			saveDebugScreenshot(page, screenshotDir, "dispatch-pat-actions-perm", logf)
			return "", fmt.Errorf("setting Actions permission: select=%w, nearby=%v", err, selectErr)
		}
	} else {
		if _, err := actionsSelect.First().SelectOption(playwright.SelectOptionValues{
			Values: playwright.StringSlice("write"),
		}); err != nil {
			saveDebugScreenshot(page, screenshotDir, "dispatch-pat-actions-select", logf)
			return "", fmt.Errorf("selecting Actions write permission: %w", err)
		}
	}
	logf("[dispatch-pat] Set Actions permission to Read and write")

	// Click "Generate token".
	generateBtn := page.Locator("button:has-text('Generate token')")
	if err := generateBtn.Click(playwright.LocatorClickOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-generate-click", logf)
		return "", fmt.Errorf("clicking 'Generate token': %w", err)
	}
	logf("[dispatch-pat] Clicked 'Generate token'")

	// Wait for page to show the generated token.
	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateDomcontentloaded,
	}); err != nil {
		return "", fmt.Errorf("waiting for token result page: %w", err)
	}

	// Fine-grained PATs display the token in a different element than classic PATs.
	// Try multiple selectors.
	tokenLocator := page.Locator("#new-oauth-token, [data-testid='new-token'], input[readonly][value^='github_pat_'], code:has-text('github_pat_')")
	if err := tokenLocator.First().WaitFor(playwright.LocatorWaitForOptions{
		Timeout: playwright.Float(10000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-token-extract", logf)
		return "", fmt.Errorf("waiting for generated token element: %w", err)
	}

	// Try extracting the token value — could be text content, input value, or attribute.
	token, err := tokenLocator.First().TextContent()
	if err != nil || token == "" {
		token, err = tokenLocator.First().InputValue()
		if err != nil || token == "" {
			saveDebugScreenshot(page, screenshotDir, "dispatch-pat-token-value", logf)
			return "", fmt.Errorf("extracting dispatch PAT value: %w", err)
		}
	}

	if token == "" {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-empty-token", logf)
		return "", fmt.Errorf("extracted dispatch PAT is empty")
	}

	logf("[dispatch-pat] Created fine-grained PAT: %s...%s", token[:10], token[len(token)-4:])
	return token, nil
}

// deleteDispatchPAT deletes a fine-grained GitHub PAT by navigating to the
// fine-grained tokens page and clicking delete for the matching token.
func deleteDispatchPAT(page playwright.Page, org, screenshotDir string, logf func(string, ...any)) error {
	tokenName := fmt.Sprintf("fullsend-dispatch-%s-e2e", org)

	if _, err := page.Goto("https://github.com/settings/personal-access-tokens", playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateDomcontentloaded,
		Timeout:   playwright.Float(7500),
	}); err != nil {
		return fmt.Errorf("navigating to fine-grained tokens page: %w", err)
	}

	// Find the row containing our token name.
	tokenRow := page.Locator(fmt.Sprintf("a:has-text('%s')", tokenName)).Locator("xpath=ancestor::li | ancestor::div[contains(@class, 'list-group-item')]")
	if err := tokenRow.First().WaitFor(playwright.LocatorWaitForOptions{
		Timeout: playwright.Float(5000),
		State:   playwright.WaitForSelectorStateVisible,
	}); err != nil {
		logf("[dispatch-pat] Token %q not found on page, may already be deleted", tokenName)
		return nil
	}

	// Click the delete/revoke button.
	deleteBtn := tokenRow.First().Locator("button:has-text('Delete'), button:has-text('Revoke')")
	if err := deleteBtn.First().Click(); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-delete-click", logf)
		return fmt.Errorf("clicking delete for dispatch PAT %q: %w", tokenName, err)
	}

	// Wait for and click the confirmation button.
	confirmBtn := page.Locator("button:has-text('I understand'), button:has-text('Yes, revoke')")
	if err := confirmBtn.First().WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(5000),
	}); err != nil {
		saveDebugScreenshot(page, screenshotDir, "dispatch-pat-confirm-wait", logf)
		return fmt.Errorf("waiting for deletion confirmation for dispatch PAT: %w", err)
	}
	if err := confirmBtn.First().Click(playwright.LocatorClickOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		return fmt.Errorf("confirming dispatch PAT deletion: %w", err)
	}

	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateDomcontentloaded,
	}); err != nil {
		return fmt.Errorf("waiting for dispatch PAT deletion to complete: %w", err)
	}

	logf("[dispatch-pat] Deleted fine-grained PAT: %s", tokenName)
	return nil
}

// deletePAT deletes a classic GitHub PAT by navigating to the tokens page
// and clicking delete for the token matching the given note.
func deletePAT(page playwright.Page, note string, logf func(string, ...any)) error {
	if _, err := page.Goto("https://github.com/settings/tokens", playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateDomcontentloaded,
		Timeout:   playwright.Float(7500),
	}); err != nil {
		return fmt.Errorf("navigating to tokens page: %w", err)
	}

	// Find the row containing our token note and click its delete button.
	tokenRow := page.Locator(fmt.Sprintf("a:has-text('%s')", note)).Locator("xpath=ancestor::div[contains(@class, 'list-group-item')]")

	// Wait for the token row to appear.
	if err := tokenRow.WaitFor(playwright.LocatorWaitForOptions{
		Timeout: playwright.Float(5000),
		State:   playwright.WaitForSelectorStateVisible,
	}); err != nil {
		logf("[pat] Token %q not found on page, may already be deleted", note)
		return nil
	}

	deleteBtn := tokenRow.Locator("button:has-text('Delete')")
	if err := deleteBtn.Click(); err != nil {
		return fmt.Errorf("clicking delete for token %q: %w", note, err)
	}

	// Wait for confirmation button in the modal.
	confirmBtn := page.Locator("button:has-text('I understand, delete this token')")
	if err := confirmBtn.WaitFor(playwright.LocatorWaitForOptions{
		State:   playwright.WaitForSelectorStateVisible,
		Timeout: playwright.Float(5000),
	}); err != nil {
		return fmt.Errorf("waiting for deletion confirmation for %q: %w", note, err)
	}
	if err := confirmBtn.Click(playwright.LocatorClickOptions{
		Timeout: playwright.Float(5000),
	}); err != nil {
		return fmt.Errorf("confirming token deletion for %q: %w", note, err)
	}

	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateDomcontentloaded,
	}); err != nil {
		return fmt.Errorf("waiting for deletion to complete: %w", err)
	}

	logf("[pat] Deleted PAT: %s", note)
	return nil
}
