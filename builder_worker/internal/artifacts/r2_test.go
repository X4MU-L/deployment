package artifacts

import (
	"bytes"
	"context"
	"io"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func TestBuildPublisherReturnsR2Publisher(t *testing.T) {
	publisher, err := BuildPublisher("r2", PublisherConfig{
		R2EndpointURL:     "https://example.r2.cloudflarestorage.com",
		R2AccessKeyID:     "access-key",
		R2SecretAccessKey: "secret-key",
		R2Region:          "auto",
	})
	if err != nil {
		t.Fatalf("BuildPublisher returned error: %v", err)
	}
	if _, ok := publisher.(*R2Publisher); !ok {
		t.Fatalf("expected *R2Publisher, got %T", publisher)
	}
}

func TestR2PublisherUploadsReleaseFilesAndManifest(t *testing.T) {
	client := &stubS3Client{}
	publisher := &R2Publisher{client: client}

	result, err := publisher.PublishSimulatedStaticRelease(PublishInput{
		ProjectID:       "project-1",
		BuildID:         "build-12345678",
		ReleaseID:       "release-1",
		ProjectName:     "demo-app",
		OutputDirectory: "dist",
		Bucket:          "static-artifacts",
		Prefix:          "projects/project-1/releases/release-1",
		ManifestKey:     "projects/project-1/releases/release-1/static_release_manifest.v1.json",
	})
	if err != nil {
		t.Fatalf("PublishSimulatedStaticRelease returned error: %v", err)
	}

	if result.ArtifactRef != "r2://static-artifacts/projects/project-1/releases/release-1" {
		t.Fatalf("unexpected artifact ref: %s", result.ArtifactRef)
	}
	if result.ManifestRef != "r2://static-artifacts/projects/project-1/releases/release-1/static_release_manifest.v1.json" {
		t.Fatalf("unexpected manifest ref: %s", result.ManifestRef)
	}
	if len(client.calls) != 3 {
		t.Fatalf("expected 3 upload calls, got %d", len(client.calls))
	}

	indexCall := assertHasKey(t, client.calls, "projects/project-1/releases/release-1/index.html")
	if indexCall.bucket != "static-artifacts" {
		t.Fatalf("unexpected index bucket: %s", indexCall.bucket)
	}
	if indexCall.contentType != "text/html; charset=utf-8" && indexCall.contentType != "text/html" {
		t.Fatalf("unexpected index content-type: %s", indexCall.contentType)
	}

	assetCall := assertHasKey(t, client.calls, "projects/project-1/releases/release-1/assets/app-build-12.js")
	if assetCall.contentType == "" {
		t.Fatalf("expected asset content-type to be set")
	}

	manifestCall := assertHasKey(t, client.calls, "projects/project-1/releases/release-1/static_release_manifest.v1.json")
	if manifestCall.contentType != "application/json" {
		t.Fatalf("expected manifest content-type application/json, got %s", manifestCall.contentType)
	}
	if !strings.Contains(manifestCall.body, "\"schema\": \"static_release_manifest.v1\"") {
		t.Fatalf("expected manifest body to contain schema, got %s", manifestCall.body)
	}
}

func TestNewR2PublisherRequiresCredentials(t *testing.T) {
	_, err := NewR2Publisher(PublisherConfig{})
	if err == nil {
		t.Fatalf("expected error for missing R2 config")
	}
}

type stubS3Client struct {
	calls []putObjectCall
}

type putObjectCall struct {
	bucket      string
	key         string
	contentType string
	body        string
}

func (s *stubS3Client) PutObject(_ context.Context, input *s3.PutObjectInput, _ ...func(*s3.Options)) (*s3.PutObjectOutput, error) {
	content, err := io.ReadAll(input.Body)
	if err != nil {
		return nil, err
	}
	s.calls = append(s.calls, putObjectCall{
		bucket:      aws.ToString(input.Bucket),
		key:         aws.ToString(input.Key),
		contentType: aws.ToString(input.ContentType),
		body:        string(content),
	})
	input.Body = io.NopCloser(bytes.NewReader(content))
	return &s3.PutObjectOutput{}, nil
}

func assertHasKey(t *testing.T, calls []putObjectCall, key string) putObjectCall {
	t.Helper()
	for _, call := range calls {
		if call.key == key {
			return call
		}
	}
	t.Fatalf("expected upload key %s, got %#v", key, calls)
	return putObjectCall{}
}
