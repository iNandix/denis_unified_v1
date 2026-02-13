# Minimal NOOP implementations for compatibility

class Counter:
    def inc(self):
        pass

    def labels(self, **kwargs):
        return self

cognitive_router_decisions = Counter()
l1_pattern_usage = Counter()
