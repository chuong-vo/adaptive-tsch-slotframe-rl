# Tong hop ket qua long-run moi nhat

- Nguon du lieu: `results/long_run`
- So seed: 8 (43-50)
- Tong so cycle hop le: 9600/9600
- Don vi lap doc lap trong thong ke: seed, khong phai tung cycle.
- Trang thai on dinh: bo 50 cycle dau cua moi profile, dung 250 cycle/profile/seed.
- Khoang tin cay: 95% Student-t tren trung binh cua cac seed.

## Ket qua trang thai on dinh

| Profile | Slotframe | Power norm. | Delay norm. | PDR | Reward |
|---|---:|---:|---:|---:|---:|
| Balanced | 30.35 +/- 0.05 | 0.1239 +/- 0.0004 | 0.0235 +/- 0.0021 | 0.9822 +/- 0.0041 | 2.2372 +/- 0.0017 |
| Delay | 10.00 +/- 0.00 | 0.1583 +/- 0.0003 | 0.0123 +/- 0.0042 | 0.9912 +/- 0.0020 | 2.0733 +/- 0.0034 |
| Energy | 68.00 +/- 0.00 | 0.1144 +/- 0.0004 | 0.0484 +/- 0.0014 | 0.9875 +/- 0.0029 | 2.0022 +/- 0.0001 |
| Reliability | 10.00 +/- 0.00 | 0.1579 +/- 0.0004 | 0.0106 +/- 0.0020 | 0.9891 +/- 0.0025 | 2.7728 +/- 0.0026 |

## Doi chieu muc tieu

- Energy: power chuan hoa thay doi -7.68% so voi Balanced (p exact=0.0078).
- Delay: delay chuan hoa thay doi -47.90% so voi Balanced (p exact=0.0156).
- Reliability: PDR thay doi +0.70% so voi Balanced (p exact=0.0312).
- Reliability so voi Delay: cung SF=10 nhung PDR thay doi -0.22% (p exact=0.0312); Reliability khong tao PDR cao hon Delay.
- Energy co PDR thay doi +0.55% so voi Balanced (p exact=0.0703), nhung chenh lech nay chua du manh va khong nen dien giai la SF lon lam tang PDR.
- Dau am nghia la metric giam; voi power va delay day la cai thien, voi PDR thi dau duong moi la cai thien.

## Hanh vi slotframe

- Balanced: SF trung binh 100 cycle cuoi = 30.36 +/- 0.09; hoi tu ve vung trung gian.
- Delay: SF trung binh 100 cycle cuoi = 10.00 +/- 0.00; dat SF toi thieu sau 14.4 +/- 0.4 cycle.
- Energy: SF trung binh 100 cycle cuoi = 68.00 +/- 0.00; dat SF toi da sau 38.0 +/- 0.0 cycle.
- Reliability: SF trung binh 100 cycle cuoi = 10.00 +/- 0.00; dat SF toi thieu sau 38.0 +/- 0.0 cycle.

## Dien giai

1. Delay va Reliability deu dua slotframe ve bien duoi. Day la ket qua mong doi khi chi co mot bien dieu khien: slotframe nho vua rut ngan thoi gian cho, vua ho tro truyen lai som hon.
2. Delay nhay cam voi slotframe hon PDR. PDR da o vung cao va bi nhieu manh, nen loi ich cua profile Reliability nho hon va co the khong tach ro khoi Delay.
3. Energy dua slotframe ve bien tren, giam tan suat radio hoat dong nhung doi lai delay tang. Day la trade-off ro nhat cua thi nghiem.
4. Trung binh toan bo 300 cycle bao gom chuyen tiep, dac biet Reliability bat dau tu SF cao cua Energy. Vi vay ket luan ve chinh sach nen dung bang steady-state; bang full-period chi dung mo ta toan dien bien long-run.
5. Action bi override tai bien khong lam sai metric: action vuot bien duoc ap dung thanh hold. Tuy nhien raw action va applied action phai duoc giu rieng khi bao cao tinh minh bach cua policy.
6. Thu tu profile luon co dinh Balanced -> Delay -> Energy -> Reliability trong ca 8 seed. Vi vay profile bi confound voi thoi gian chay; dac biet chenh lech PDR nho khong duoc dien giai nhu quan he nhan qua hoan toan.
7. Reward cua cac profile dung bo trong so khac nhau, nen gia tri reward tuyet doi giua cac profile khong phai bang xep hang chat luong chung.

## Duoi phan phoi

| Profile | Delay p50 (ms) | Delay p95 (ms) | Delay p99 (ms) | >1 s | PDR <0.9 |
|---|---:|---:|---:|---:|---:|
| Balanced | 365.3 | 558.4 | 2262.9 | 50 | 137 |
| Delay | 138.1 | 237.8 | 2257.6 | 33 | 70 |
| Energy | 871.4 | 1003.0 | 1969.1 | 104 | 107 |
| Reliability | 135.8 | 237.0 | 1251.6 | 27 | 85 |

## File minh hoa

- `longrun_slotframe_timeline.png`: SF theo thoi gian va bon profile.
- `longrun_mean_timeline.png`: SF, power, delay va PDR tren cung truc long-run.
- `longrun_profile_summary.png`: so sanh steady-state kem CI 95%.
- `longrun_power_delay_tradeoff.png`: trade-off power-delay, kem SF va PDR.
- `longrun_pdr_by_seed.png`: PDR steady-state cua tung seed va trung binh.
