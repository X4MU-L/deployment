package artifacts

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"mime"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const StaticReleaseManifestSchema = "static_release_manifest.v1"

func createSimulatedOutput(input PublishInput) (string, func(), error) {
	tempDir, err := os.MkdirTemp("", "build-"+input.BuildID+"-")
	if err != nil {
		return "", func() {}, fmt.Errorf("create temp dir: %w", err)
	}
	cleanup := func() {
		_ = os.RemoveAll(tempDir)
	}

	outputRoot := filepath.Join(tempDir, input.OutputDirectory)
	assetDir := filepath.Join(outputRoot, "assets")
	if err := os.MkdirAll(assetDir, 0o755); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("create asset dir: %w", err)
	}

	indexHTML := "<!doctype html>\n" +
		"<html><head><meta charset='utf-8'><title>" + input.ProjectName + "</title></head><body>" +
		"<h1>" + input.ProjectName + "</h1>" +
		"<p>build " + input.BuildID + "</p>" +
		"<script src=\"/assets/app-" + prefix(input.BuildID, 8) + ".js\"></script>" +
		"</body></html>\n"
	if err := os.WriteFile(filepath.Join(outputRoot, "index.html"), []byte(indexHTML), 0o644); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("write index.html: %w", err)
	}

	assetFile := filepath.Join(assetDir, "app-"+prefix(input.BuildID, 8)+".js")
	assetBody := "console.log('build " + input.BuildID + " for project " + input.ProjectID + "');\n"
	if err := os.WriteFile(assetFile, []byte(assetBody), 0o644); err != nil {
		cleanup()
		return "", func() {}, fmt.Errorf("write asset file: %w", err)
	}

	return outputRoot, cleanup, nil
}

type collectedFile struct {
	relativePath string
	content      []byte
}

func collectFiles(rootDir string) ([]collectedFile, error) {
	files := make([]collectedFile, 0)
	err := filepath.Walk(rootDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}

		relativePath, err := filepath.Rel(rootDir, path)
		if err != nil {
			return err
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		files = append(files, collectedFile{
			relativePath: filepath.ToSlash(relativePath),
			content:      content,
		})
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("collect files: %w", err)
	}

	sort.Slice(files, func(i int, j int) bool { return files[i].relativePath < files[j].relativePath })
	return files, nil
}

func buildManifest(rootDir string, projectID string, releaseID string, buildID string) (map[string]any, error) {
	type asset struct {
		Path        string `json:"path"`
		SHA256      string `json:"sha256"`
		ContentType string `json:"content_type"`
	}

	assets := make([]asset, 0)
	err := filepath.Walk(rootDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}

		relative, err := filepath.Rel(rootDir, path)
		if err != nil {
			return err
		}
		normalized := filepath.ToSlash(relative)
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		hash := sha256.Sum256(content)
		contentType := mime.TypeByExtension(filepath.Ext(normalized))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
		assets = append(assets, asset{
			Path:        normalized,
			SHA256:      hex.EncodeToString(hash[:]),
			ContentType: contentType,
		})
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("walk output dir: %w", err)
	}

	sort.Slice(assets, func(i int, j int) bool { return assets[i].Path < assets[j].Path })

	return map[string]any{
		"schema":         StaticReleaseManifestSchema,
		"project_id":     projectID,
		"release_id":     releaseID,
		"build_id":       buildID,
		"generated_at":   time.Now().UTC().Format(time.RFC3339),
		"index_document": "index.html",
		"error_document": nil,
		"cache_policy": map[string]any{
			"html_max_age_seconds":  30,
			"asset_max_age_seconds": 31536000,
			"asset_cache_control":   "public, max-age=31536000, immutable",
		},
		"assets": assets,
	}, nil
}

func buildR2URI(bucket string, key string) string {
	return "r2://" + bucket + "/" + strings.TrimLeft(key, "/")
}

func prefix(value string, size int) string {
	if len(value) <= size {
		return value
	}
	return value[:size]
}
