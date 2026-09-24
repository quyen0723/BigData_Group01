# Verify skeleton runs (WBS 0.1 gate): config loads, Spark session starts, folders exist.
import sys, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

failures = []

# 1. Config loads
cfg = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
assert cfg["paths"]["curated_dir"] == "data/curated", "curated_dir mismatch"
print("[1/4] configs/spark.yaml OK:", list(cfg.keys()))

# 2. Expected folders exist
for d in ["configs", "contracts", "data/raw", "data/curated", "src/etl",
          "src/analytics", "src/modeling", "notebooks/colab", "artifacts", "evidence"]:
    p = ROOT / d
    if not p.is_dir():
        failures.append(f"missing dir: {d}")
print("[2/4] folder structure OK" if not failures else f"[2/4] FAILURES: {failures}")

# 3. Frozen contract file exists (WBS 0.2 dependency)
contract = ROOT / "contracts" / "CONTRACTS.md"
print("[3/4] contracts/CONTRACTS.md:", "EXISTS" if contract.exists() else "MISSING")

# 4. Spark session starts
from pyspark.sql import SparkSession
spark = (SparkSession.builder
         .appName("skeleton-verify")
         .master("local[2]")
         .config("spark.sql.shuffle.partitions", cfg["spark"]["sql"]["shuffle_partitions"])
         .getOrCreate())
df = spark.createDataFrame([(1, "ok")], ["id", "status"])
n = df.count()
spark.stop()
print(f"[4/4] Spark session OK, count={n}")

if contract.exists() and not failures and n == 1:
    print("SKELETON VERIFY: PASS")
else:
    print("SKELETON VERIFY: FAIL")
    sys.exit(1)