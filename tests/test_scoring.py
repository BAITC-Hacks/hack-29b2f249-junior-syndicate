import numpy as np
import pandas as pd
import pytest

from src.features import percentile_score
from src.scoring import ROLES, assign_roles, assign_priority, generate_evidence, load_config


def test_zero_features_do_not_receive_positive_percentile():
    assert percentile_score(pd.Series([0, 0, np.nan])).eq(0).all()
    assert percentile_score(pd.Series([0, 2, 4])).tolist() == [0, .5, 1]


@pytest.mark.parametrize("gid,role", [(100, "consolidator"), (200, "distributor"), (300, "transit"), (400, "terminal"), (900, "peripheral")])
def test_known_synthetic_patterns(features, config, gid, role):
    scores = assign_roles(features, config).set_index("gid")
    assert scores.loc[gid, "role"] == role
    if role != "peripheral":
        assert scores.loc[gid, f"{role}_score"] >= .5


def test_no_boundary_terminal_and_isolate_coordinator(features, config):
    result = assign_roles(features, config).set_index("gid")
    assert result.loc[500, "terminal_score"] == 0
    assert result.loc[500, "role"] != "terminal"
    assert result.loc[900, "coordinator_score"] == 0


def test_contributions_reconstruct_all_scores(features, config):
    result = assign_priority(assign_roles(features, config), config)
    for role in ROLES:
        np.testing.assert_allclose(result[f"{role}_score"], result.filter(like=f"role_factor__{role}__").sum(axis=1))
    np.testing.assert_allclose(result.priority_score, result.filter(like="priority_factor__").sum(axis=1))
    assert result.role_score.between(0, 1).all()
    assert result.priority_score.between(0, 1).all()
    assert result.loc[result.gid == 900, "priority_score"].item() == 0


def test_seed_cannot_use_retention_to_become_terminal(features, config):
    changed = features.copy()
    changed.loc[changed.gid == 400, "is_seed"] = True
    result = assign_roles(changed, config).set_index("gid")
    assert result.loc[400, "terminal_score"] == 0


def test_extreme_nonseed_ratio_is_not_transit(features, config):
    changed = features.copy()
    changed.loc[changed.gid == 300, "flow_through_ratio"] = 150
    result = assign_roles(changed, config).set_index("gid")
    assert result.loc[300, "transit_score"] == 0


def test_evidence_limits_survive_long_amounts(features, config):
    scored = assign_roles(features, config)
    row = scored[scored.gid == 100].iloc[0].copy()
    row["sum_in"] = 1e18
    row["is_seed"], row["is_boundary_node"] = True, True
    evidence = generate_evidence(row)
    assert 0 < len(evidence) <= 200
    assert "Seed" in evidence and "depth=4" in evidence
    assert "terminal не подтверждён" in evidence


def test_bad_weights_rejected(config, tmp_path):
    import yaml
    config["priority"]["financial"] = 2
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="sum to 1"):
        load_config(path)
