import json

from run_trend_sweep import _seed_completion_issue


def _write_valid_seed(seed_dir):
    seed_dir.mkdir()
    (seed_dir / "example.csv").write_text("cycle_idx\n1\n", encoding="utf-8")
    coverage = {
        "valid_rows": 1000,
        "slotframe_counts": {str(value): 1 for value in range(10, 40)},
        "profile_counts": {"balanced": 1000},
    }
    (seed_dir / "coverage_summary.json").write_text(
        json.dumps(coverage),
        encoding="utf-8",
    )
    metric = {"coefficients": [1.0, 0.0]}
    trends = {
        "power": metric,
        "delay": metric,
        "reliability": metric,
    }
    (seed_dir / "trend_vectors.json").write_text(
        json.dumps(trends),
        encoding="utf-8",
    )


def _completion_issue(seed_dir):
    return _seed_completion_issue(
        seed_dir,
        min_valid_rows=1000,
        min_slotframes=30,
        required_profile="balanced",
    )


def test_complete_seed_is_accepted(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)

    assert _completion_issue(seed_dir) is None


def test_missing_or_corrupt_artifacts_are_rejected(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)
    (seed_dir / "trend_vectors.json").write_text("{", encoding="utf-8")

    assert _completion_issue(seed_dir).startswith("unreadable JSON:")


def test_low_coverage_is_rejected(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)
    coverage_path = seed_dir / "coverage_summary.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["valid_rows"] = 999
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")

    assert _completion_issue(seed_dir) == "valid_rows=999 < 1000"


def test_wrong_profile_is_rejected(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)
    coverage_path = seed_dir / "coverage_summary.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["profile_counts"] = {"delay": 1000}
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")

    assert "expected {'balanced': 1000}" in _completion_issue(seed_dir)


def test_non_object_json_is_rejected(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)
    (seed_dir / "coverage_summary.json").write_text("[]", encoding="utf-8")

    assert _completion_issue(seed_dir) == (
        "coverage_summary.json must contain an object"
    )


def test_non_numeric_coefficients_are_rejected(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)
    trend_path = seed_dir / "trend_vectors.json"
    trends = json.loads(trend_path.read_text(encoding="utf-8"))
    trends["delay"]["coefficients"] = ["invalid"]
    trend_path.write_text(json.dumps(trends), encoding="utf-8")

    assert _completion_issue(seed_dir) == (
        "non-numeric coefficients for trend metric: delay"
    )


def test_graph_dataset_can_be_required_for_gnn_collection(tmp_path):
    seed_dir = tmp_path / "cycle_r500_s1"
    _write_valid_seed(seed_dir)

    issue = _seed_completion_issue(
        seed_dir,
        min_valid_rows=1000,
        min_slotframes=30,
        required_profile="balanced",
        require_graph_dataset=True,
    )

    assert issue.startswith("missing graph files:")
