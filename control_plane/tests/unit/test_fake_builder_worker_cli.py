def test_worker_cli_boots_celery_with_expected_queue(monkeypatch):
    captured: list[str] = []

    monkeypatch.setattr(
        "app.celery_builder.worker_cli.get_settings",
        lambda: type("Settings", (), {"fake_builder_queue_name": "fake-builder"})(),
    )
    monkeypatch.setattr(
        "app.celery_builder.worker_cli.celery_app.worker_main",
        lambda argv: captured.extend(argv),
    )

    from app.celery_builder.worker_cli import main

    main()

    assert captured == [
        "worker",
        "--loglevel=INFO",
        "--pool=solo",
        "-Q",
        "fake-builder",
    ]
