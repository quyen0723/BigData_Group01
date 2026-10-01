#!/usr/bin/env python3
"""promotion_gate.py — WBS 7.4/7.5. design.md D-12 step 5-6.

Recomputes RMSE for both the active and candidate models independently via
`ALSModel.load()` on the SAME fixed holdout — the candidate's self-reported
`model_card.json` RMSE is never trusted on its own (spec: "Self-reported
metrics not trusted"). Checks G1-G7; PASS activates atomically (single
`serving_meta` update), FAIL leaves `serving_meta` byte-for-byte unchanged.

Defaults (epsilon, RMSE band) come from configs/streaming.yaml `promotion_gate`
— PROVISIONAL until Person 1 confirms (design.md Open Question D3).

Run inside the spark container:
    python -m orchestration.promotion_gate --version v1.1.0
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from pymongo import MongoClient
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALSModel

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, mongo_uri


def _rmse(spark, model_dir: str, holdout) -> float:
    model = ALSModel.load(model_dir)
    predictions = model.transform(holdout).na.drop(subset=["prediction"])
    evaluator = RegressionEvaluator(metricName="rmse", labelCol="rating", predictionCol="prediction")
    return evaluator.evaluate(predictions)


def _semver_tuple(v: str) -> tuple[int, int, int]:
    core = v.lstrip("v")
    major, minor, patch = (int(x) for x in core.split("."))
    return major, minor, patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="candidate version, must already be staged (7.3)")
    args = parser.parse_args()

    streaming_cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    gate_cfg = streaming_cfg["promotion_gate"]
    db_name = serving_cfg["mongo"]["db"]
    paths = streaming_cfg["paths"]

    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=10000)
    db = client[db_name]

    candidate_reg = db.model_registry.find_one({"_id": args.version})
    if not candidate_reg or candidate_reg.get("status") != "staged":
        print(f"FAIL: {args.version} is not staged (run orchestration.stage_candidate first)")
        client.close()
        return 1

    pointer = db.serving_meta.find_one({"_id": "active"})
    if not pointer:
        print("FAIL: no active version — run loaders.bootstrap_registry first")
        client.close()
        return 1
    active_version = pointer["modelVersion"]
    active_reg = db.model_registry.find_one({"_id": active_version})
    active_card = (active_reg or {}).get("modelCard", {})
    candidate_card = candidate_reg.get("modelCard", {})

    checks: list[tuple[str, bool, str]] = []

    # --- G7 first: version numbering (cheap, no Spark/RMSE needed if this fails) ---
    try:
        active_t, cand_t = _semver_tuple(active_version), _semver_tuple(args.version)
        g7_ok = cand_t > active_t and cand_t[0] == active_t[0]
    except ValueError:
        g7_ok = False
    already_used = db.model_registry.count_documents(
        {"_id": args.version, "status": {"$in": ["active", "retired", "rejected"]}}
    ) > 0
    checks.append(("G7 version numbering", g7_ok and not already_used,
                    f"active={active_version} candidate={args.version} already_used={already_used}"))

    # --- G1-G3: RMSE, recomputed independently on the same fixed holdout ---
    # NOTE: model_card.json's "artifacts.als_model_dir" is whatever path was true
    # in the environment that GENERATED the card (e.g. a Colab session path like
    # /content/drive/MyDrive/...) — never trust it for where the model is mounted
    # HERE. Always resolve from our own configured layout (verified: crashes with
    # "Input path does not exist" otherwise).
    active_model_dir = f"{paths['models']}/als_{active_version}"
    candidate_model_dir = f"{candidate_reg['candidateDir']}/model"
    cut_test = candidate_card.get("split", {}).get("cut_test") or active_card.get("split", {}).get("cut_test")
    baseline_rmse = active_card.get("metrics", {}).get("rmse_movemean_test") \
        or candidate_card.get("metrics", {}).get("rmse_movemean_test")
    reported_candidate_rmse = candidate_card.get("metrics", {}).get("rmse_test")

    # RMSE recomputation can fail for reasons that have nothing to do with the
    # candidate's quality (a corrupt/incomplete model directory, a bad path) —
    # never let that crash the whole gate uncontrolled. Treat it as an explicit
    # G1-G3 FAIL with the real reason, and still evaluate G4-G7 below so a
    # partial, honest result is always produced.
    active_rmse = candidate_rmse = None
    rmse_error: str | None = None
    spark = build_spark("movielens-promotion-gate")
    try:
        holdout = spark.read.parquet(paths["curated_ratings"])
        if cut_test is not None:
            holdout = holdout.filter(f"timestamp >= {float(cut_test)}")

        active_rmse = _rmse(spark, active_model_dir, holdout)
        candidate_rmse = _rmse(spark, candidate_model_dir, holdout)
    except Exception as exc:  # noqa: BLE001 - any load/compute failure is a gate concern, not a crash
        rmse_error = f"{type(exc).__name__}: {exc}"
    finally:
        spark.stop()

    epsilon = float(gate_cfg["epsilon_rmse"])
    band_lo, band_hi = gate_cfg["rmse_sanity_band"]

    if rmse_error is not None:
        checks.append(("G1 candidate RMSE <= active RMSE * (1+eps)", False, f"RMSE computation failed: {rmse_error}"))
        checks.append(("G2 candidate RMSE < MovieMean baseline", False, f"RMSE computation failed: {rmse_error}"))
        checks.append(("G3 candidate RMSE within sanity band", False, f"RMSE computation failed: {rmse_error}"))
    else:
        checks.append((
            "G1 candidate RMSE <= active RMSE * (1+eps)",
            candidate_rmse <= active_rmse * (1 + epsilon),
            f"active={active_rmse:.4f} candidate={candidate_rmse:.4f} eps={epsilon} "
            f"(reported in model_card: {reported_candidate_rmse})",
        ))
        if baseline_rmse is not None:
            checks.append((
                "G2 candidate RMSE < MovieMean baseline",
                candidate_rmse < float(baseline_rmse),
                f"candidate={candidate_rmse:.4f} baseline={float(baseline_rmse):.4f}",
            ))
        checks.append((
            "G3 candidate RMSE within sanity band",
            band_lo <= candidate_rmse <= band_hi,
            f"candidate={candidate_rmse:.4f} band=[{band_lo},{band_hi}]",
        ))

    # --- G4: staged doc schema validity (rank 1..n, n<=10, no dup userId) ---
    coll = serving_cfg["mongo"]["collections"]["user_recommendations"]
    bad_shape = db[coll].count_documents({
        "modelVersion": args.version,
        "$expr": {"$gt": [{"$size": "$recommendations"}, 10]},
    })
    total_cand_recs = db[coll].count_documents({"modelVersion": args.version})
    dup_users = list(db[coll].aggregate([
        {"$match": {"modelVersion": args.version}},
        {"$group": {"_id": "$userId", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$limit": 1},
    ]))
    checks.append((
        "G4 staged user_recommendations schema valid",
        total_cand_recs > 0 and bad_shape == 0 and not dup_users,
        f"docs={total_cand_recs:,} oversized_lists={bad_shape} duplicate_users={len(dup_users)}",
    ))

    # --- G5: zero already-rated items (against user_rated = curated base ∪ delta) ---
    leaked = list(db[coll].aggregate([
        {"$match": {"modelVersion": args.version}},
        {"$unwind": "$recommendations"},
        {"$lookup": {
            "from": "user_rated",
            "let": {"uid": "$userId", "mid": "$recommendations.movieId"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$userId", "$$uid"]}, {"$eq": ["$movieId", "$$mid"]},
            ]}}}],
            "as": "m",
        }},
        {"$match": {"m": {"$ne": []}}},
        {"$count": "n"},
    ]))
    leaked_count = leaked[0]["n"] if leaked else 0
    checks.append(("G5 no already-rated in candidate recommendations", leaked_count == 0, f"{leaked_count} leaked"))

    # --- G6: candidate user coverage >= active user coverage ---
    active_coverage = db[coll].count_documents({"modelVersion": active_version})
    checks.append((
        "G6 candidate user coverage >= active",
        total_cand_recs >= active_coverage,
        f"candidate={total_cand_recs:,} active={active_coverage:,}",
    ))

    print(f"=== Promotion gate: {active_version} (active) -> {args.version} (candidate) ===")
    all_ok = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        all_ok = all_ok and ok

    now = dt.datetime.now(dt.timezone.utc)
    report = {
        "activeVersion": active_version, "candidateVersion": args.version,
        "activeRmse": active_rmse, "candidateRmse": candidate_rmse,
        "candidateRmseSelfReported": reported_candidate_rmse,
        "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks],
        "result": "PASS" if all_ok else "FAIL", "ranAt": now.isoformat(),
    }
    report_path = Path("evidence") / f"p2_6_2_promotion_{'pass' if all_ok else 'fail'}_{args.version}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if all_ok:
        db.model_registry.update_one({"_id": args.version}, {"$set": {
            "status": "active", "gateReport": report, "activatedAt": now,
        }})
        db.model_registry.update_one({"_id": active_version}, {"$set": {"status": "retired", "retiredAt": now}})
        artifacts_map = pointer.get("artifacts", {})
        for key in artifacts_map:
            artifacts_map[key] = args.version
        db.serving_meta.replace_one(
            {"_id": "active"},
            {"_id": "active", "modelVersion": args.version, "previousVersion": active_version,
             "artifacts": artifacts_map, "activatedAt": now, "gateReport": str(report_path)},
        )
        print(f"\nOK: PASS — {args.version} is now the active serving version (previous: {active_version})")
    else:
        db.model_registry.update_one({"_id": args.version}, {"$set": {
            "status": "rejected", "gateReport": report, "rejectedAt": now,
        }})
        print(f"\nFAIL — {args.version} rejected. serving_meta unchanged, {active_version} keeps serving.")

    client.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
