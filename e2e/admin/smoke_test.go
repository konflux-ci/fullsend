//go:build e2e

package admin

import (
	"os"
	"testing"

	"github.com/playwright-community/playwright-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestPlaywrightSmoke validates that Playwright can launch a browser and
// navigate to GitHub's login page. This test does NOT require credentials
// and serves as a basic infrastructure check.
func TestPlaywrightSmoke(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping e2e test in short mode")
	}

	pw, err := playwright.Run()
	require.NoError(t, err, "starting Playwright")
	t.Cleanup(func() { _ = pw.Stop() })

	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(os.Getenv("E2E_HEADED") != "true"),
	})
	require.NoError(t, err, "launching browser")
	t.Cleanup(func() { _ = browser.Close() })

	page, err := browser.NewPage()
	require.NoError(t, err, "creating page")

	// Navigate to GitHub's login page.
	_, err = page.Goto("https://github.com/login", playwright.PageGotoOptions{
		WaitUntil: playwright.WaitUntilStateNetworkidle,
	})
	require.NoError(t, err, "navigating to GitHub login")

	// Verify we can see the login form elements.
	loginField := page.Locator("#login_field")
	visible, err := loginField.IsVisible()
	require.NoError(t, err, "checking login field visibility")
	assert.True(t, visible, "login field should be visible on GitHub login page")

	passwordField := page.Locator("#password")
	visible, err = passwordField.IsVisible()
	require.NoError(t, err, "checking password field visibility")
	assert.True(t, visible, "password field should be visible on GitHub login page")

	title, err := page.Title()
	require.NoError(t, err, "getting page title")
	assert.Contains(t, title, "GitHub", "page title should contain 'GitHub'")
}

// TestLoginHelpers validates the URL classification helper functions.
func TestLoginHelpers(t *testing.T) {
	tests := []struct {
		name     string
		fn       func(string) bool
		url      string
		expected bool
	}{
		{"login page", isLoginPage, "https://github.com/login", true},
		{"session page", isLoginPage, "https://github.com/session", true},
		{"dashboard", isLoginPage, "https://github.com/dashboard", false},
		{"settings", isLoginPage, "https://github.com/settings/tokens", false},
		{"device verification", isDeviceVerificationPage, "https://github.com/sessions/verified-device/confirm", true},
		{"device verification 2", isDeviceVerificationPage, "https://github.com/device-verification", true},
		{"normal page", isDeviceVerificationPage, "https://github.com/settings", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := tt.fn(tt.url)
			assert.Equal(t, tt.expected, result, "for URL %s", tt.url)
		})
	}
}
