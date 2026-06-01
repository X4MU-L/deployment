package artifacts

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"mime"
	"path/filepath"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type S3PutObjectAPI interface {
	PutObject(ctx context.Context, params *s3.PutObjectInput, optFns ...func(*s3.Options)) (*s3.PutObjectOutput, error)
}

type R2Publisher struct {
	client S3PutObjectAPI
}

func NewR2Publisher(config PublisherConfig) (*R2Publisher, error) {
	if config.R2EndpointURL == "" || config.R2AccessKeyID == "" || config.R2SecretAccessKey == "" {
		return nil, fmt.Errorf(
			"R2 publisher requires endpoint, access key id, and secret access key",
		)
	}

	region := config.R2Region
	if region == "" {
		region = "auto"
	}

	awsConfig := aws.Config{
		Region: region,
		Credentials: aws.NewCredentialsCache(
			credentials.NewStaticCredentialsProvider(
				config.R2AccessKeyID,
				config.R2SecretAccessKey,
				config.R2SessionToken,
			),
		),
	}
	client := s3.NewFromConfig(awsConfig, func(options *s3.Options) {
		options.UsePathStyle = true
		options.BaseEndpoint = aws.String(config.R2EndpointURL)
	})
	return &R2Publisher{client: client}, nil
}

func (p *R2Publisher) PublishSimulatedStaticRelease(input PublishInput) (PublishResult, error) {
	outputRoot, cleanup, err := createSimulatedOutput(input)
	if err != nil {
		return PublishResult{}, err
	}
	defer cleanup()

	return p.PublishStaticReleaseFromDirectory(input, outputRoot)
}

func (p *R2Publisher) PublishStaticReleaseFromDirectory(input PublishInput, outputRoot string) (PublishResult, error) {
	files, err := collectFiles(outputRoot)
	if err != nil {
		return PublishResult{}, err
	}
	for _, file := range files {
		contentType := mime.TypeByExtension(filepath.Ext(file.relativePath))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
		key := joinR2Key(input.Prefix, file.relativePath)
		if err := p.putObject(input.Bucket, key, file.content, contentType); err != nil {
			return PublishResult{}, err
		}
	}

	manifest, err := buildManifest(outputRoot, input.ProjectID, input.ReleaseID, input.BuildID)
	if err != nil {
		return PublishResult{}, err
	}
	encodedManifest, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return PublishResult{}, fmt.Errorf("marshal manifest: %w", err)
	}
	if err := p.putObject(input.Bucket, input.ManifestKey, encodedManifest, "application/json"); err != nil {
		return PublishResult{}, err
	}

	return PublishResult{
		ArtifactRef: buildR2URI(input.Bucket, input.Prefix),
		ManifestRef: buildR2URI(input.Bucket, input.ManifestKey),
	}, nil
}

func (p *R2Publisher) putObject(bucket string, key string, body []byte, contentType string) error {
	_, err := p.client.PutObject(context.Background(), &s3.PutObjectInput{
		Bucket:      aws.String(bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(body),
		ContentType: aws.String(contentType),
	})
	if err != nil {
		return fmt.Errorf("upload object %s: %w", key, err)
	}
	return nil
}

func joinR2Key(prefix string, relativePath string) string {
	normalizedPrefix := strings.TrimRight(prefix, "/")
	normalizedPath := strings.TrimLeft(relativePath, "/")
	if normalizedPrefix == "" {
		return normalizedPath
	}
	if normalizedPath == "" {
		return normalizedPrefix
	}
	return normalizedPrefix + "/" + normalizedPath
}
