from __future__ import annotations

from scripts.build_training_dataset import _source_family, _split_pairs_by_family


def test_source_family_groups_synthetic_variants() -> None:
    assert _source_family("synthetic:telemedicine:small") == "synthetic:telemedicine"
    assert _source_family("existing:project_brief_sample.txt") == "existing:project_brief_sample.txt"


def test_split_pairs_by_family_creates_held_out_domains() -> None:
    pairs = [
        {"source": "synthetic:alpha:small"},
        {"source": "synthetic:alpha:large"},
        {"source": "synthetic:beta:small"},
        {"source": "synthetic:beta:large"},
        {"source": "synthetic:gamma:small"},
        {"source": "synthetic:gamma:large"},
        {"source": "synthetic:delta:small"},
        {"source": "synthetic:delta:large"},
    ]

    split = _split_pairs_by_family(pairs, val_ratio=0.25, test_ratio=0.25)

    train_families = set(split["train_families"])
    val_families = set(split["val_families"])
    test_families = set(split["test_families"])

    assert len(split["train"]) + len(split["val"]) + len(split["test"]) == len(pairs)
    assert train_families.isdisjoint(val_families)
    assert train_families.isdisjoint(test_families)
    assert val_families.isdisjoint(test_families)
    assert split["val"]
    assert split["test"]
    assert split["strategy"] == "deterministic_family_holdout"
