package vertex

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"strings"
)

// LiveGCPClient implements GCPClient using the GCP IAM REST API.
// It obtains access tokens via `gcloud auth print-access-token`.
type LiveGCPClient struct{}

// NewLiveGCPClient creates a new LiveGCPClient.
func NewLiveGCPClient() *LiveGCPClient {
	return &LiveGCPClient{}
}

// accessToken obtains a GCP access token from the gcloud CLI.
func (c *LiveGCPClient) accessToken(ctx context.Context) (string, error) {
	cmd := exec.CommandContext(ctx, "gcloud", "auth", "print-access-token")
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("getting GCP access token: %w (ensure 'gcloud auth login' has been run)", err)
	}
	token := strings.TrimSpace(string(out))
	if token == "" {
		return "", fmt.Errorf("gcloud returned empty access token")
	}
	return token, nil
}

// doRequest creates and executes an authenticated HTTP request.
func (c *LiveGCPClient) doRequest(ctx context.Context, method, url, body string) (*http.Response, error) {
	token, err := c.accessToken(ctx)
	if err != nil {
		return nil, err
	}

	var bodyReader io.Reader
	if body != "" {
		bodyReader = strings.NewReader(body)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}

	return http.DefaultClient.Do(req)
}

// GetServiceAccount checks that a service account exists in the project.
func (c *LiveGCPClient) GetServiceAccount(ctx context.Context, projectID, saName string) error {
	email := saName + "@" + projectID + ".iam.gserviceaccount.com"
	url := fmt.Sprintf("https://iam.googleapis.com/v1/projects/%s/serviceAccounts/%s", projectID, email)

	resp, err := c.doRequest(ctx, http.MethodGet, url, "")
	if err != nil {
		return fmt.Errorf("checking service account: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("service account %s not found in project %s", saName, projectID)
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status %d checking service account: %s", resp.StatusCode, body)
	}
	return nil
}

// CreateServiceAccount creates a new service account in the project.
func (c *LiveGCPClient) CreateServiceAccount(ctx context.Context, projectID, saName, displayName string) error {
	url := fmt.Sprintf("https://iam.googleapis.com/v1/projects/%s/serviceAccounts", projectID)
	payload := fmt.Sprintf(`{"accountId":%q,"serviceAccount":{"displayName":%q}}`, saName, displayName)

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return fmt.Errorf("creating service account: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusConflict {
		// SA already exists — treat as success for idempotency.
		return nil
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status %d creating service account: %s", resp.StatusCode, body)
	}
	return nil
}

// CreateServiceAccountKey generates a new JSON key for the service account.
func (c *LiveGCPClient) CreateServiceAccountKey(ctx context.Context, projectID, saEmail string) ([]byte, error) {
	url := fmt.Sprintf("https://iam.googleapis.com/v1/projects/%s/serviceAccounts/%s/keys", projectID, saEmail)
	payload := `{"keyAlgorithm":"KEY_ALG_RSA_2048","privateKeyType":"TYPE_GOOGLE_CREDENTIALS_FILE"}`

	resp, err := c.doRequest(ctx, http.MethodPost, url, payload)
	if err != nil {
		return nil, fmt.Errorf("creating service account key: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("unexpected status %d creating key: %s", resp.StatusCode, body)
	}

	var result struct {
		PrivateKeyData string `json:"privateKeyData"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding key response: %w", err)
	}

	// privateKeyData is base64-encoded JSON credentials.
	decoded, err := base64.StdEncoding.DecodeString(result.PrivateKeyData)
	if err != nil {
		return nil, fmt.Errorf("decoding private key data: %w", err)
	}

	return decoded, nil
}
