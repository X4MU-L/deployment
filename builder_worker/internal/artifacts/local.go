package artifacts

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type LocalPublisher struct {
	root string
}

func NewLocalPublisher(root string) *LocalPublisher {
	return &LocalPublisher{root: root}
}

func (p *LocalPublisher) PublishSimulatedStaticRelease(input PublishInput) (PublishResult, error) {
	outputRoot, cleanup, err := createSimulatedOutput(input)
	if err != nil {
		return PublishResult{}, err
	}
	defer cleanup()

	return p.PublishStaticReleaseFromDirectory(input, outputRoot)
}

func (p *LocalPublisher) PublishStaticReleaseFromDirectory(input PublishInput, outputRoot string) (PublishResult, error) {
	targetRoot := filepath.Join(p.root, input.Bucket, filepath.FromSlash(input.Prefix))
	if err := os.RemoveAll(targetRoot); err != nil {
		return PublishResult{}, fmt.Errorf("reset target root: %w", err)
	}
	if err := copyDir(outputRoot, targetRoot); err != nil {
		return PublishResult{}, fmt.Errorf("publish directory: %w", err)
	}

	manifest, err := buildManifest(outputRoot, input.ProjectID, input.ReleaseID, input.BuildID)
	if err != nil {
		return PublishResult{}, err
	}
	manifestPath := filepath.Join(p.root, input.Bucket, filepath.FromSlash(input.ManifestKey))
	if err := os.MkdirAll(filepath.Dir(manifestPath), 0o755); err != nil {
		return PublishResult{}, fmt.Errorf("create manifest dir: %w", err)
	}
	encodedManifest, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return PublishResult{}, fmt.Errorf("marshal manifest: %w", err)
	}
	if err := os.WriteFile(manifestPath, encodedManifest, 0o644); err != nil {
		return PublishResult{}, fmt.Errorf("write manifest: %w", err)
	}

	return PublishResult{
		ArtifactRef: buildR2URI(input.Bucket, input.Prefix),
		ManifestRef: buildR2URI(input.Bucket, input.ManifestKey),
	}, nil
}

func copyDir(sourceDir string, targetDir string) error {
	return filepath.Walk(sourceDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		relative, err := filepath.Rel(sourceDir, path)
		if err != nil {
			return err
		}
		targetPath := filepath.Join(targetDir, relative)

		if info.IsDir() {
			return os.MkdirAll(targetPath, 0o755)
		}

		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		return os.WriteFile(targetPath, content, 0o644)
	})
}
