from app.background_builder.base import BackgroundBuildDispatchResult, BackgroundBuilder


class CFBuilder(BackgroundBuilder):
    adapter_name = "cloudflare"

    def enqueue_build(self, build_id: str) -> BackgroundBuildDispatchResult:
        raise NotImplementedError(
            "CF_BUILDER_NOT_IMPLEMENTED: Cloudflare builder adapter is not implemented yet"
        )
