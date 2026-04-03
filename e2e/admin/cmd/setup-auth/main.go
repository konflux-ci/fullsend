// Command setup-auth launches a headed Playwright browser for manual GitHub
// login. The resulting session state is saved to E2E_BROWSER_STATE_DIR for
// use by e2e tests.
//
// Usage:
//
//	E2E_BROWSER_STATE_DIR=/tmp/pw-state go run ./e2e/admin/cmd/setup-auth/
package main

import (
	"bufio"
	"fmt"
	"os"

	"github.com/playwright-community/playwright-go"
)

func main() {
	stateDir := os.Getenv("E2E_BROWSER_STATE_DIR")
	if stateDir == "" {
		fmt.Fprintln(os.Stderr, "E2E_BROWSER_STATE_DIR must be set")
		os.Exit(1)
	}

	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "creating state dir: %v\n", err)
		os.Exit(1)
	}

	if err := playwright.Install(&playwright.RunOptions{
		Browsers: []string{"chromium"},
	}); err != nil {
		fmt.Fprintf(os.Stderr, "installing Playwright browsers: %v\n", err)
		os.Exit(1)
	}

	pw, err := playwright.Run()
	if err != nil {
		fmt.Fprintf(os.Stderr, "starting Playwright: %v\n", err)
		os.Exit(1)
	}
	defer pw.Stop()

	// Launch in headed mode so the user can log in.
	browser, err := pw.Chromium.LaunchPersistentContext(stateDir, playwright.BrowserTypeLaunchPersistentContextOptions{
		Headless: playwright.Bool(false),
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "launching browser: %v\n", err)
		os.Exit(1)
	}

	page, err := browser.NewPage()
	if err != nil {
		fmt.Fprintf(os.Stderr, "creating page: %v\n", err)
		os.Exit(1)
	}

	if _, err := page.Goto("https://github.com/login"); err != nil {
		fmt.Fprintf(os.Stderr, "navigating to GitHub login: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("=== GitHub Login ===")
	fmt.Println("Log in as the 'botsend' user in the browser window.")
	fmt.Println("Complete any 2FA prompts.")
	fmt.Println("")
	fmt.Println("When you're fully logged in, press Enter here to save the session.")

	scanner := bufio.NewScanner(os.Stdin)
	scanner.Scan()

	// Close the browser — this saves the persistent context state.
	if err := browser.Close(); err != nil {
		fmt.Fprintf(os.Stderr, "closing browser: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("")
	fmt.Printf("Session state saved to: %s\n", stateDir)
	fmt.Println("")
	fmt.Println("To convert to a CI secret:")
	fmt.Printf("  tar czf - -C %s . | base64 > state.b64\n", stateDir)
	fmt.Println("  gh secret set E2E_BROWSER_STATE < state.b64")
}
