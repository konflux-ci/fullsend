//go:build e2e

package admin

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/playwright-community/playwright-go"
)

// githubLogin logs into GitHub by filling in the login form programmatically.
// This eliminates the need for stored browser sessions and manual refresh.
func githubLogin(page playwright.Page, username, password string) error {
	if _, err := page.Goto("https://github.com/login", playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateNetworkidle,
	}); err != nil {
		return fmt.Errorf("navigating to GitHub login: %w", err)
	}

	// Check if already logged in (redirected away from login page).
	if !isLoginPage(page.URL()) {
		return nil
	}

	// Fill in credentials.
	if err := page.Locator("#login_field").Fill(username); err != nil {
		return fmt.Errorf("filling username: %w", err)
	}
	if err := page.Locator("#password").Fill(password); err != nil {
		return fmt.Errorf("filling password: %w", err)
	}

	// Submit the form.
	if err := page.Locator("input[type='submit'], button[type='submit']").First().Click(); err != nil {
		return fmt.Errorf("clicking sign in: %w", err)
	}

	// Wait for the page to settle after submission.
	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateNetworkidle,
	}); err != nil {
		return fmt.Errorf("waiting for post-login page: %w", err)
	}

	// Poll for up to 30s until we're no longer on a login/session page.
	// GitHub may show intermediate pages (device verification, etc.).
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		currentURL := page.URL()

		// Success: navigated away from all auth pages.
		if !isLoginPage(currentURL) && !isDeviceVerificationPage(currentURL) {
			return nil
		}

		// 2FA page — fail immediately; the bot user must not have 2FA.
		if strings.Contains(currentURL, "/sessions/two-factor") {
			return fmt.Errorf("login incomplete: 2FA page detected at %s (bot user must not have 2FA enabled)", currentURL)
		}

		// Device verification page — GitHub sometimes asks to verify via
		// email/SMS even without 2FA. Wait for the user/bot to handle it
		// or for an auto-redirect.
		if isDeviceVerificationPage(currentURL) {
			fmt.Printf("[login] Device verification page detected at %s, waiting...\n", currentURL)
			time.Sleep(2 * time.Second)
			continue
		}

		// Still on login/session page — credentials may be wrong.
		if isLoginPage(currentURL) {
			// Check for error messages on the page.
			errMsg := page.Locator(".flash-error, .js-flash-alert")
			if visible, _ := errMsg.IsVisible(); visible {
				text, _ := errMsg.TextContent()
				return fmt.Errorf("login failed: %s", strings.TrimSpace(text))
			}
			// Wait a moment and check again — might still be processing.
			time.Sleep(1 * time.Second)
			continue
		}

		time.Sleep(500 * time.Millisecond)
	}

	return fmt.Errorf("login timed out, ended up at %s", page.URL())
}

// isLoginPage returns true if the URL looks like a GitHub login/session page.
func isLoginPage(url string) bool {
	return strings.Contains(url, "/login") || strings.Contains(url, "/session")
}

// isDeviceVerificationPage returns true if the URL is a device verification page.
func isDeviceVerificationPage(url string) bool {
	return strings.Contains(url, "/sessions/verified-device") ||
		strings.Contains(url, "/device-verification")
}

// handleSudoMode checks if GitHub is showing a "sudo" password confirmation
// page and fills in the password if so. GitHub requires password re-entry
// for sensitive operations like creating tokens or deleting apps.
func handleSudoMode(page playwright.Page) error {
	// Check if we're on a sudo confirmation page.
	sudoPassword := page.Locator("#sudo_password")
	visible, err := sudoPassword.IsVisible()
	if err != nil || !visible {
		return nil // Not a sudo page.
	}

	// We need the password from the environment.
	password := getPasswordFromEnv()
	if password == "" {
		return fmt.Errorf("sudo mode detected but E2E_GITHUB_PASSWORD not set")
	}

	if err := sudoPassword.Fill(password); err != nil {
		return fmt.Errorf("filling sudo password: %w", err)
	}

	// Click the confirm button.
	confirmBtn := page.Locator("button[type='submit']:has-text('Confirm')")
	if err := confirmBtn.Click(); err != nil {
		// Try alternative selectors.
		altBtn := page.Locator("button[type='submit']")
		if altErr := altBtn.Click(); altErr != nil {
			return fmt.Errorf("clicking sudo confirm: primary=%w, alt=%v", err, altErr)
		}
	}

	// Wait for the page to load after sudo confirmation.
	if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
		State: playwright.LoadStateNetworkidle,
	}); err != nil {
		return fmt.Errorf("waiting after sudo confirmation: %w", err)
	}

	return nil
}

// getPasswordFromEnv returns the GitHub password from environment.
func getPasswordFromEnv() string {
	return os.Getenv("E2E_GITHUB_PASSWORD")
}
