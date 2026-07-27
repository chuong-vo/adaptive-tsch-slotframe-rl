# Toi uu thich nghi kich thuoc slotframe TSCH bang hoc tang cuong trong SDWSN

Repository nay chua ma nguon va artifact cuoi cua quy trinh toi uu kich thuoc
slotframe TSCH bang PPO trong kien truc SDWSN. Quy trinh thuc nghiem gom ba giai
doan:

1. Thu thap du lieu Cooja va xay dung vector xu huong theo kich thuoc slotframe.
2. Huan luyen chinh sach PPO tren moi truong so hoa tu cac vector xu huong.
3. Trien khai model vao vong dieu khien Cooja va danh gia long-run tren nhieu seed.

> **Luu y ve ten bien:** mot so bien moi truong van dung tien to `ELISE_` de
> tuong thich voi ma nguon ke thua. Tien to nay khong lam thay doi pham vi cua
> de tai: bien dieu khien duy nhat trong thi nghiem la kich thuoc slotframe TSCH.

## 1. Cau truc repository

```text
.
|-- SDWSN-controller/       # Control plane, moi truong RL, train va phan tich
|-- contiki-ng/             # Data plane Contiki-NG va kich ban Cooja
|-- results/
|   |-- trend/              # Du lieu trend cuoi: 20 seed
|   |-- training/           # Model PPO duoc chon va ket qua danh gia
|   `-- long_run/           # Long-run cuoi: seed 43-50
|-- run_trend_sweep.py
|-- run_long_run_with_seed.sh
|-- run_long_run_seed_range.sh
`-- setup_rl_env.sh
```

Repository khong chua log trung gian, checkpoint khong duoc chon, cache, virtual
environment hoac file bao cao/luan van.

## 2. Moi truong da kiem chung

Lan chay cuoi su dung:

- Ubuntu 22.04/WSL2;
- Python 3.10;
- OpenJDK 17;
- Contiki-NG va Cooja duoc dong goi trong `contiki-ng/`;
- PyTorch 2.8.0;
- Stable-Baselines3 2.0.0a5;
- GPU NVIDIA CUDA 12.8 cho pha train. GPU khong bat buoc.

Khuyen nghi toi thieu 16 GB RAM va 30 GB dung luong trong. Log Cooja cua mot dot
long-run day du co the lon, du log khong duoc commit vao Git.

## 3. Clone repository

Repository dang o che do private. Tai khoan GitHub can duoc cap quyen truoc khi
clone.

```bash
git clone https://github.com/chuong-vo/adaptive-tsch-slotframe-rl.git
cd adaptive-tsch-slotframe-rl
```

Hoac dung GitHub CLI:

```bash
gh auth login
gh repo clone chuong-vo/adaptive-tsch-slotframe-rl
cd adaptive-tsch-slotframe-rl
```

## 4. Cai dependency he thong

Lenh tham khao cho Ubuntu 22.04:

```bash
sudo apt update
sudo apt install -y \
  git \
  build-essential \
  python3 \
  python3-dev \
  python3-venv \
  openjdk-17-jdk \
  psmisc
```

Kiem tra:

```bash
python3 --version
java -version
```

Python phai tu 3.10 tro len. Moi truong cua lan chay cuoi la Python 3.10; nen uu
tien dung cung phien ban khi can tai lap chinh xac.

## 5. Tao Python environment

Script setup nhan hai tham so:

```text
./setup_rl_env.sh [VENV_DIR] [auto|cpu|cu128]
```

### Tu dong chon CPU/GPU

```bash
./setup_rl_env.sh .venv-rl auto
source .venv-rl/bin/activate
```

Che do `auto` chon CUDA 12.8 neu tim thay `nvidia-smi`; nguoc lai cai ban CPU.

### Buoc dung CPU

```bash
./setup_rl_env.sh .venv-rl cpu
source .venv-rl/bin/activate
```

### Buoc dung CUDA 12.8

```bash
./setup_rl_env.sh .venv-rl cu128
source .venv-rl/bin/activate
```

Khai bao duong dan workspace:

```bash
export CONTIKI_NG="$PWD/contiki-ng"
export PYTHONPATH="$PWD/SDWSN-controller${PYTHONPATH:+:$PYTHONPATH}"
```

Kiem tra Python, PyTorch va controller:

```bash
python -c "import torch; print('torch=', torch.__version__, 'cuda=', torch.cuda.is_available())"
python -c "import sdwsn_controller; print('sdwsn_controller: OK')"
pip check
```

## 6. Kiem tra source truoc khi chay

### Unit test cho co che dieu khien slotframe

```bash
pytest -q SDWSN-controller/tests/test_env_slotframe_controls.py
```

Ket qua mong doi:

```text
..... [100%]
```

### Kiem tra Cooja/Gradle

```bash
cd contiki-ng/tools/cooja
./gradlew test
cd ../../..
```

Ket qua mong doi la `BUILD SUCCESSFUL`. Cooja target duoc build boi Cooja; khong
chay truc tiep `make TARGET=cooja` trong thu muc mote.

### Kiem tra port dieu khien

Mac dinh Cooja va controller giao tiep qua TCP port `60001`.

```bash
ss -ltnp | grep ':60001' || true
```

Neu port bi mot tien trinh Cooja cu chiem:

```bash
pkill -f 'org.contikios.cooja.Main' || true
fuser -k 60001/tcp || true
```

Chi thuc hien hai lenh tren khi khong co thi nghiem khac dang chay.

## 7. Smoke test

Smoke test xac nhan moi truong khoi dong duoc truoc khi chay dot day du.

### 7.1 Trend smoke test

```bash
SMOKE_TREND_OUT="$PWD/smoke/trend/output"
SMOKE_TREND_LOG="$PWD/smoke/trend/logs"

python run_trend_sweep.py \
  --seeds 1 \
  --output-base "$SMOKE_TREND_OUT" \
  --log-base "$SMOKE_TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3 \
  --max-cycles 40 \
  --min-valid-rows 20 \
  --min-slotframes 15
```

Smoke output hop le phai co:

```bash
find "$SMOKE_TREND_OUT/cycle_r500_s1" -maxdepth 1 -type f | sort
```

Trong do can co `example.csv`, `coverage_summary.json` va
`trend_vectors.json`. Tuyet doi khong dung vector tu smoke test de train model
chinh.

### 7.2 Training smoke test

Training smoke test dung mot rollout PPO:

```bash
SMOKE_TRAIN="$PWD/smoke/training"

RL_RUN_DIR="$SMOKE_TRAIN" \
RL_SEED=123 \
RL_TOTAL_STEPS=4096 \
RL_EVAL_FREQ=4096 \
RL_N_EVAL_EPISODES=20 \
python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py
```

### 7.3 Long-run smoke test

```bash
MODEL="$PWD/results/training/trained_model/best_model.zip"

ELISE_MAX_CYCLES=20 \
ELISE_OUTPUT_BASE="$PWD/smoke/long_run/output" \
ELISE_LOG_BASE="$PWD/smoke/long_run/logs" \
./run_long_run_with_seed.sh 43 "$MODEL"
```

Kiem tra:

```bash
wc -l smoke/long_run/output/seed_43/example.csv
```

File gom mot dong header va 20 dong cycle.

## 8. Giai doan 1: thu thap trend vector

Trend duoc thu trong Cooja voi profile `balanced` co dinh. Hanh dong nen dao
chieu tang/giam slotframe; tham so exploration bo sung cac diem lay mau ngau
nhien trong mien hop le.

```bash
TREND_OUT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/output/final_trend"
TREND_LOG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/tensorlog/final_trend"

python run_trend_sweep.py \
  --start 1 --count 20 \
  --output-base "$TREND_OUT" \
  --log-base "$TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3
```

Mac dinh moi seed chay theo `max_episode_steps=1200` cua
`native_controller_approx_model.json`, yeu cau toi thieu 1.000 cycle hop le va
30 kich thuoc slotframe phan biet.

Script co checkpoint theo seed: seed chi duoc xem la hoan tat khi co du
`example.csv`, `coverage_summary.json` va `trend_vectors.json`. Khi chay lai
cung lenh, cac seed da hoan tat se duoc bo qua.

Kiem tra tien do:

```bash
find "$TREND_OUT" -path '*/trend_vectors.json' | wc -l
```

Kiem tra nhanh so dong tung seed:

```bash
for csv in "$TREND_OUT"/cycle_r500_s*/example.csv; do
  printf '%s: ' "$(basename "$(dirname "$csv")")"
  awk 'END { print NR - 1 }' "$csv"
done
```

Neu mot seed loi, chay rieng seed do:

```bash
python run_trend_sweep.py \
  --seeds 7 \
  --output-base "$TREND_OUT" \
  --log-base "$TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3
```

Them `--rerun-completed` chi khi chu dong muon ghi lai seed da hoan tat.

## 9. Giai doan 1b: fit trend va ghi vao config

Chi fit sau khi du 20 seed hop le:

```bash
TRAIN_CONFIG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/numerical_controller_rl.json"

python SDWSN-controller/tutorials/reinforcement-learning/plot_seed_trends.py \
  --base-dir "$TREND_OUT" \
  --config "$TRAIN_CONFIG" \
  --min-valid-rows 1000 \
  --min-slotframes 30 \
  --required-profile balanced \
  --min-seeds 20 \
  --write-config
```

Ket qua fit nam tai:

```text
$TREND_OUT/summary/power_trends.png
$TREND_OUT/summary/delay_trends.png
$TREND_OUT/summary/reliability_trends.png
$TREND_OUT/summary/summary_fits.json
```

`--write-config` ghi he so gop vao ba truong:

```text
performance_metrics.energy.weights
performance_metrics.delay.weights
performance_metrics.pdr.weights
```

Khong sua thu cong cac he so sau buoc nay neu muc tieu la tai lap cung quy trinh.

## 10. Giai doan 2: train PPO

Trong train:

- profile luan phien `balanced`, `delay`, `energy`, `reliability`;
- slotframe khoi tao ngau nhien trong mien hop le 10-68;
- action `0`, `1`, `2` lan luot la tang, giam va giu slotframe;
- seed mac dinh cua dot cuoi la `123`;
- tong so buoc cua dot cuoi la `5,996,544`.

### Chay foreground

```bash
TRAIN_ROOT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/runs/final_train"
mkdir -p "$TRAIN_ROOT"

RL_RUN_DIR="$TRAIN_ROOT" \
RL_SEED=123 \
RL_TOTAL_STEPS=5996544 \
RL_EVAL_FREQ=8192 \
RL_N_EVAL_EPISODES=20 \
python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py
```

### Chay background bang nohup

```bash
TRAIN_ROOT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/runs/final_train"
mkdir -p "$TRAIN_ROOT"

nohup env \
  RL_RUN_DIR="$TRAIN_ROOT" \
  RL_SEED=123 \
  RL_TOTAL_STEPS=5996544 \
  RL_EVAL_FREQ=8192 \
  RL_N_EVAL_EPISODES=20 \
  python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py \
  > "$TRAIN_ROOT/train.log" 2>&1 &

echo $! | tee "$TRAIN_ROOT/train.pid"
tail -f "$TRAIN_ROOT/train.log"
```

Kiem tra tien trinh:

```bash
ps -p "$(cat "$TRAIN_ROOT/train.pid")" -o pid,etime,cmd
```

Tim model canonical sau khi train:

```bash
MODEL="$(find "$TRAIN_ROOT" -path '*/trained_model/best_model.zip' -type f | sort | tail -n 1)"
test -n "$MODEL" && test -f "$MODEL"
echo "$MODEL"
```

Moi run tao mot thu muc `ppo_run_<timestamp>`. Cac artifact quan trong:

```text
trained_model/best_model.zip
trained_model/model_selection.json
metrics/policy_grid_evaluation.csv
metrics/eval_metrics.csv
numerical_controller_rl.json
output/*.png
```

Chi proceed sang long-run khi `policy_grid_evaluation.csv` co du 20 truong hop va
`direction_ok=True`.

## 11. Giai doan 3: long-run

Long-run chay tuan tu de tranh xung dot Cooja va TCP port 60001. Moi seed gom
1.200 cycle, chia thanh bon doan 300 cycle theo thu tu:

| Profile | Trong so `(alpha, beta, delta)` | Uu tien |
|---|---:|---|
| balanced | `(0.4, 0.3, 0.3)` | can bang ba muc tieu |
| delay | `(0.1, 0.8, 0.1)` | do tre |
| energy | `(0.8, 0.1, 0.1)` | cong suat/nang luong |
| reliability | `(0.1, 0.1, 0.8)` | do tin cay/PDR |

Chay seed 43-50:

```bash
MODEL="/absolute/path/to/trained_model/best_model.zip"
LONG_OUT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/output/final_long_run"
LONG_LOG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/logs/final_long_run"

ELISE_OUTPUT_BASE="$LONG_OUT" \
ELISE_LOG_BASE="$LONG_LOG" \
ELISE_MAX_CYCLES=1200 \
./run_long_run_seed_range.sh 43 50 "$MODEL"
```

Kiem tra tien do:

```bash
for csv in "$LONG_OUT"/seed_*/example.csv; do
  printf '%s: ' "$(basename "$(dirname "$csv")")"
  awk 'END { print NR - 1 }' "$csv"
done
```

Moi seed hoan tat phai co 1.200 dong du lieu. Long-run khong co checkpoint giua
mot seed. Neu mat dien hoac crash giua seed, chay lai rieng seed do tu dau:

```bash
ELISE_OUTPUT_BASE="$LONG_OUT" \
ELISE_LOG_BASE="$LONG_LOG" \
ELISE_MAX_CYCLES=1200 \
./run_long_run_with_seed.sh 47 "$MODEL"
```

Khong chay song song nhieu seed tren cung port 60001.

## 12. Tong hop va ve ket qua long-run

Sau khi du seed:

```bash
python SDWSN-controller/tutorials/reinforcement-learning/long-run/analyze_long_run_results.py \
  --input-dir "$LONG_OUT" \
  --output-dir "$LONG_OUT/analysis" \
  --transition-cycles 50 \
  --timeline-window 15
```

Kiem tra chat luong:

```bash
cat "$LONG_OUT/analysis/quality_summary.json"
```

Dieu kien cua dot cuoi:

```text
seed_count = 8
total_rows = 9600
valid_cycles = 9600
invalid_cycles = 0
wait_timeouts = 0
all_runs_complete = true
```

## 13. Artifact cuoi da commit

Khong can chay lai de xem ket qua cuoi:

```text
results/trend/       20 seed x 1.200 cycle
results/training/    PPO seed 123, 5.996.544 buoc, policy grid 20/20
results/long_run/    seed 43-50 x 1.200 cycle
```

Xac minh artifact khong bi thay doi:

```bash
sha256sum --check results/MANIFEST.sha256
```

Load model tren CPU:

```bash
python - <<'PY'
from stable_baselines3 import PPO

PPO.load("results/training/trained_model/best_model.zip", device="cpu")
print("model: OK")
PY
```

## 14. Dinh nghia du lieu chinh

Ba file CSV chinh la trend `example.csv`, training `eval_metrics.csv` va
long-run `example.csv`.

| Cot | Y nghia |
|---|---|
| `cycle_idx` | chi so cycle trong mot seed |
| `seed` | random seed cua Cooja |
| `profile` | ho so balanced/delay/energy/reliability |
| `alpha`, `beta`, `delta` | trong so muc tieu |
| `current_sf_len` | kich thuoc slotframe dang ap dung |
| `last_ts_in_schedule` | timeslot hoat dong cuoi trong schedule |
| `power_normalized` | cong suat da chuan hoa |
| `delay_mean` | do tre trung binh tho |
| `delay_normalized` | do tre da chuan hoa |
| `pdr_mean` | PDR trung binh giua cac nut |
| `reward` | phan thuong tinh tu chi so va trong so |
| `action` | hanh dong tac tu yeu cau |
| `applied_action` | hanh dong thuc su duoc ap dung |
| `requested_sf_len` | slotframe tac tu yeu cau |
| `applied_sf_len` | slotframe thuc su duoc ap dung |
| `action_overridden` | hanh dong co bi chan tai bien hay khong |
| `wait_timeout` | cua so xu ly bi timeout |
| `valid_cycle` | cycle co duoc dung trong phan tich hay khong |

`delay_mean` la do tre trung binh toan mang cua mot cycle, khong phai danh sach
do tre cua tung goi.

## 15. Stall, retry va tinh dung dan cua du lieu

- Controller cho mot processing window toi da 30 giay.
- Khi stall, cung cau hinh va hanh dong dang danh gia duoc retry toi da ba lan.
- Cycle chi duoc ghi la hop le sau khi xu ly thanh cong.
- `wait_timeout=True` va `valid_cycle=False` danh dau cycle that bai.
- Long-run cuoi trong `results/long_run` khong co wait timeout va du 9.600 cycle
  hop le.

Khong giam timeout hoac bo qua retry chi de chay nhanh hon, vi dieu nay co the
lam thay doi tap du lieu.

## 16. Xu ly loi thuong gap

### Dung o `Waiting for Cooja to start`

1. Kiem tra Java 17: `java -version`.
2. Kiem tra port 60001.
3. Tat Cooja cu bang cac lenh o Muc 6.
4. Chay `./gradlew test` trong `contiki-ng/tools/cooja`.
5. Doc log trong thu muc duoc khai bao boi `ELISE_LOG_BASE`.

### `ModuleNotFoundError`

```bash
source .venv-rl/bin/activate
export PYTHONPATH="$PWD/SDWSN-controller${PYTHONPATH:+:$PYTHONPATH}"
pip check
```

### CUDA khong kha dung

GPU khong bat buoc. Tao lai environment CPU:

```bash
./setup_rl_env.sh .venv-rl-cpu cpu
source .venv-rl-cpu/bin/activate
```

### Permission denied trong output

Khong chay pipeline bang `sudo`. Sua ownership cua thu muc da tung duoc tao boi
root:

```bash
sudo chown -R "$USER:$USER" \
  SDWSN-controller/tutorials/reinforcement-learning/output \
  SDWSN-controller/tutorials/reinforcement-learning/tensorlog \
  SDWSN-controller/tutorials/reinforcement-learning/training/runs \
  SDWSN-controller/tutorials/reinforcement-learning/long-run/output \
  SDWSN-controller/tutorials/reinforcement-learning/long-run/logs
```

### Mat dien hoac crash

- Trend: chay lai cung lenh; seed hoan tat duoc tu dong bo qua.
- Training: dung model chi khi run da tao `model_selection.json` va ket qua policy
  grid. Run dang do khong duoc xem la model cuoi.
- Long-run: giu cac seed da hoan tat va chay lai seed dang do tu dau.

## 17. Nguyen tac khi mo rong nghien cuu

- Tao output folder moi cho moi dot thi nghiem.
- Khong ghi de `results/`, day la baseline cuoi cua de tai.
- Ghi lai seed, config, model path va Git commit cho moi dot chay.
- Chi thay doi mot nhom bien moi lan khi so sanh.
- Danh gia theo seed; khong xem tung cycle trong cung seed la mau doc lap.
- Khong commit virtual environment, log Cooja, checkpoint trung gian hoac bao cao
  ca nhan.

## 18. Nguon va giay phep

Control plane ke thua SDWSN-controller/ELISE cua Fernando Jurado-Lasso; data
plane ke thua Contiki-NG va cac thanh phan phu thuoc cua no. Xem license va
copyright trong tung thu muc/tep nguon truoc khi tai phan phoi.
