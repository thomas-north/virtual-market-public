from vmarket.research.wiki import append_log_entry, init_research_workspace


def test_init_research_workspace_creates_private_wiki(tmp_path):
    created = init_research_workspace(tmp_path)

    assert tmp_path.joinpath("raw").is_dir()
    assert tmp_path.joinpath("normalized").is_dir()
    assert tmp_path.joinpath("wiki", "entities").is_dir()
    assert tmp_path.joinpath("wiki", "index.md").is_file()
    assert tmp_path.joinpath("wiki", "log.md").is_file()
    assert created


def test_append_log_entry(tmp_path):
    init_research_workspace(tmp_path)
    log = append_log_entry("ingest META.US", root=tmp_path)

    assert "ingest META.US" in log.read_text(encoding="utf-8")
