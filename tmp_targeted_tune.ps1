$ErrorActionPreference = 'Stop'
$py = 'd:/OneDrive/codebase/pinescripts-1/.venv/Scripts/python.exe'

# v1 failing crypto pairs
& $py backend/strategy_generator/tune_v1_profile.py --symbol ETH/BTC --profile guideline_closed --max-evals 240 --seed 501 --apply --apply-best-available --out docs/data/v1_profile_tuning_result_ethbtc_guideline_retry.json
& $py backend/strategy_generator/tune_v1_profile.py --symbol ETH/USDC --profile guideline_closed --max-evals 240 --seed 502 --apply --apply-best-available --out docs/data/v1_profile_tuning_result_ethusdc_guideline_retry.json
& $py backend/strategy_generator/tune_v1_profile.py --symbol ETH/USDT --profile guideline_closed --max-evals 240 --seed 503 --apply --apply-best-available --out docs/data/v1_profile_tuning_result_ethusdt_guideline_retry.json

# v2 failing crypto pairs
& $py backend/strategy_generator/tune_v2_profile.py --symbol ETH/BTC --profile guideline_closed --max-evals 500 --seed 601 --apply --apply-best-available --out docs/data/v2_profile_tuning_result_ethbtc_guideline_retry.json
& $py backend/strategy_generator/tune_v2_profile.py --symbol ETH/USDC --profile guideline_closed --max-evals 500 --seed 602 --apply --apply-best-available --out docs/data/v2_profile_tuning_result_ethusdc_guideline_retry.json
& $py backend/strategy_generator/tune_v2_profile.py --symbol ETH/USDT --profile guideline_closed --max-evals 500 --seed 603 --apply --apply-best-available --out docs/data/v2_profile_tuning_result_ethusdt_guideline_retry.json

# v3-v6 targeted failures
$targets = @(
  @{v='v3'; s='BTC/USDT'; seed=701}, @{v='v3'; s='ETH/BTC'; seed=702}, @{v='v3'; s='ETH/USDC'; seed=703}, @{v='v3'; s='ETH/USDT'; seed=704},
  @{v='v4'; s='BTC/USDT'; seed=705}, @{v='v4'; s='ETH/BTC'; seed=706}, @{v='v4'; s='ETH/USDC'; seed=707}, @{v='v4'; s='ETH/USDT'; seed=708},
  @{v='v5'; s='ETH/BTC'; seed=709}, @{v='v5'; s='ETH/USDC'; seed=710}, @{v='v5'; s='ETH/USDT'; seed=711},
  @{v='v6'; s='ETH/BTC'; seed=712}, @{v='v6'; s='ETH/USDC'; seed=713}, @{v='v6'; s='ETH/USDT'; seed=714}
)
foreach ($t in $targets) {
  $safe = ($t.s.ToLower() -replace '[^a-z0-9]', '')
  & $py backend/strategy_generator/tune_v3_v6_profile.py --version $t.v --symbol $t.s --max-evals 320 --seed $t.seed --min-win-rate 65 --min-net-return 15 --max-drawdown 4.5 --apply --apply-best-available --out "docs/data/$($t.v)_profile_tuning_result_$($safe)_guideline_retry.json"
}
