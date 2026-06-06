
from builder_profile.cache import LLMCache


class TestLLMCache:
    def test_put_and_get(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        cache.put("prompt1", "haiku", '{"summary": "test"}')

        result = cache.get("prompt1", "haiku")
        assert result == '{"summary": "test"}'
        cache.close()

    def test_miss_returns_none(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        assert cache.get("nonexistent", "haiku") is None
        cache.close()

    def test_different_models_different_keys(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        cache.put("prompt1", "haiku", "haiku-result")
        cache.put("prompt1", "sonnet", "sonnet-result")

        assert cache.get("prompt1", "haiku") == "haiku-result"
        assert cache.get("prompt1", "sonnet") == "sonnet-result"
        cache.close()

    def test_invalidation_by_mtime(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        cache.put("prompt1", "haiku", "old-result", source_mtime=1000.0)

        assert cache.get("prompt1", "haiku", source_mtime=999.0) == "old-result"
        assert cache.get("prompt1", "haiku", source_mtime=1001.0) is None
        cache.close()

    def test_clear(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        cache.put("prompt1", "haiku", "result1")
        cache.put("prompt2", "haiku", "result2")

        cache.clear()
        assert cache.get("prompt1", "haiku") is None
        assert cache.get("prompt2", "haiku") is None
        cache.close()

    def test_stats(self, tmp_path):
        cache = LLMCache(tmp_path / "test.db")
        assert cache.stats()["entries"] == 0

        cache.put("p1", "h", "r1")
        cache.put("p2", "h", "r2")
        assert cache.stats()["entries"] == 2
        cache.close()
