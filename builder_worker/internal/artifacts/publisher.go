package artifacts

type PublisherConfig struct {
	Root              string
	R2EndpointURL     string
	R2AccessKeyID     string
	R2SecretAccessKey string
	R2SessionToken    string
	R2Region          string
}

type Publisher interface {
	PublishSimulatedStaticRelease(input PublishInput) (PublishResult, error)
	PublishStaticReleaseFromDirectory(input PublishInput, outputRoot string) (PublishResult, error)
}

type PublishInput struct {
	ProjectID       string
	BuildID         string
	ReleaseID       string
	ProjectName     string
	OutputDirectory string
	Bucket          string
	Prefix          string
	ManifestKey     string
}

type PublishResult struct {
	ArtifactRef string
	ManifestRef string
}
