package contracts

import "fmt"

const BuildRequestedSchema = "build.requested.v1"

type BuildRequestedMessage struct {
	SchemaName     string              `json:"schema"`
	BuildID        string              `json:"build_id"`
	ProjectID      string              `json:"project_id"`
	EnvironmentID  string              `json:"environment_id"`
	ReleaseID      string              `json:"release_id"`
	CorrelationID  string              `json:"correlation_id"`
	Attempt        int                 `json:"attempt"`
	GitCheckout    GitCheckoutMetadata `json:"git_checkout"`
	BuildSpec      StaticBuildSpec     `json:"build_spec"`
	ArtifactTarget ArtifactTarget      `json:"artifact_target"`
}

type GitCheckoutMetadata struct {
	RepoURL        string         `json:"repo_url"`
	SourceProvider string         `json:"source_provider"`
	Repository     map[string]any `json:"repository"`
	DefaultBranch  string         `json:"default_branch"`
	SourceRef      string         `json:"source_ref"`
	CommitSHA      string         `json:"commit_sha"`
}

type StaticBuildSpec struct {
	Kind            string         `json:"kind"`
	RootDirectory   string         `json:"root_directory"`
	InstallCommand  string         `json:"install_command"`
	BuildCommand    string         `json:"build_command"`
	OutputDirectory string         `json:"output_directory"`
	FrameworkPreset string         `json:"framework_preset"`
	PackageManager  string         `json:"package_manager"`
	EnvSnapshot     map[string]any `json:"env_snapshot"`
}

type ArtifactTarget struct {
	Provider    string `json:"provider"`
	Bucket      string `json:"bucket"`
	Prefix      string `json:"prefix"`
	ManifestKey string `json:"manifest_key"`
}

func (m BuildRequestedMessage) Validate() error {
	if m.SchemaName != BuildRequestedSchema {
		return fmt.Errorf("unexpected schema: %s", m.SchemaName)
	}
	if m.BuildID == "" || m.ProjectID == "" || m.ReleaseID == "" || m.CorrelationID == "" {
		return fmt.Errorf("build_id, project_id, release_id, and correlation_id are required")
	}
	if m.Attempt < 1 {
		return fmt.Errorf("attempt must be >= 1")
	}
	if m.GitCheckout.RepoURL == "" {
		return fmt.Errorf("git_checkout.repo_url is required")
	}
	if m.BuildSpec.Kind != "" && m.BuildSpec.Kind != "static" {
		return fmt.Errorf("unsupported build_spec.kind: %s", m.BuildSpec.Kind)
	}
	if m.ArtifactTarget.Provider != "" && m.ArtifactTarget.Provider != "r2" {
		return fmt.Errorf("unsupported artifact_target.provider: %s", m.ArtifactTarget.Provider)
	}
	if m.ArtifactTarget.Bucket == "" || m.ArtifactTarget.Prefix == "" || m.ArtifactTarget.ManifestKey == "" {
		return fmt.Errorf("artifact_target.bucket, prefix, and manifest_key are required")
	}
	return nil
}
