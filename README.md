# Air Quality Monitor — SDG 11

Aplikasi pemantauan kualitas udara (AQI) untuk 5 kota di Indonesia, dibuat untuk
Evaluasi 3 mata kuliah Cloud Computing. Tema mengacu pada **SDG 11: Kota dan
Permukiman yang Berkelanjutan** — menyediakan informasi kualitas udara perkotaan
secara real-time agar warga dapat mengambil keputusan yang lebih sehat.

Aplikasi dikemas dalam container dan dijalankan di atas cluster **Kubernetes**
dengan **LoadBalancing** dan **Horizontal Pod Autoscaler (HPA)**.

## Fitur

- **Gauge AQI real-time** dengan auto-refresh tiap 5 detik (warna mengikuti status).
- **Pemilihan lokasi via peta** (Leaflet) + tombol cepat untuk 5 kota.
- **Data historis 24 jam** dalam grafik garis (Chart.js).
- **Rekomendasi kesehatan** otomatis sesuai kategori AQI.
- **Endpoint simulasi sensor IoT** (`POST /api/update`).

Data dummy dibangkitkan secara **deterministik terhadap waktu** (gabungan gelombang
sinus), sehingga:
1. Semua replica/worker menghasilkan angka **sama** pada saat yang sama — tidak ada
   nilai yang "meloncat" saat request dilayani pod berbeda di belakang LoadBalancer.
2. Perubahan nilai **halus / tidak spiking** (live maks ±1 per 5 detik, historis
   maks ±12 per jam).

## Tech Stack

- Python 3.9 + Flask (disajikan oleh **gunicorn** di dalam container)
- Frontend: HTML + Leaflet + Chart.js (via CDN, butuh koneksi internet saat runtime)
- Docker, Kubernetes (Deployment, Service `LoadBalancer`, HPA)

## Struktur File

```
.
├── app.py              # Backend Flask + API
├── templates/
│   └── index.html      # Dashboard frontend
├── requirements.txt    # Dependency Python
├── Dockerfile          # Image container (gunicorn)
└── k8s/                # Manifest Kubernetes
    ├── configmap.yaml      # ConfigMap: judul, kota default, interval refresh
    ├── deployment.yaml     # Deployment (2 replica, baca ConfigMap via envFrom)
    ├── service.yaml        # Service tipe ClusterIP (diekspos lewat Ingress)
    ├── ingress.yaml        # Ingress (ingress-nginx) -> air-quality-service
    └── hpa.yaml            # Horizontal Pod Autoscaler (2-5 pod, target CPU 50%)
```

## API

| Method | Endpoint               | Keterangan                                  |
|--------|------------------------|---------------------------------------------|
| GET    | `/`                    | Halaman dashboard                           |
| GET    | `/api/cities`          | Daftar kota + AQI (untuk marker peta)       |
| GET    | `/api/data?city=<id>`  | Data live satu kota                         |
| GET    | `/api/history?city=<id>` | Data historis 24 jam                      |
| POST   | `/api/update`          | Simulasi sensor IoT mengirim data baru      |

`<id>` kota: `jakarta`, `bandung`, `surabaya`, `medan`, `denpasar`.

---

## 1. Menjalankan Secara Lokal

### Tanpa Docker (pengembangan)
```powershell
pip install -r requirements.txt
python app.py
# buka http://localhost:5000
```

### Dengan Docker
```powershell
docker build -t sdg-air-quality:v1 .
docker run -p 5000:5000 sdg-air-quality:v1
# buka http://localhost:5000
```

## 2. Build & Push Image ke Docker Hub

Ganti `<username>` dengan username Docker Hub kamu.
```powershell
docker build -t sdg-air-quality:v1 .
docker login
docker tag sdg-air-quality:v1 <username>/sdg-air-quality:v1
docker push <username>/sdg-air-quality:v1
```
Lalu sunting `deployment.yaml` baris `image:` → ganti `<USERNAME_DOCKER_HUB>`
dengan username kamu.

## 3. Menyiapkan Cluster

### Opsi A — Lokal (Minikube)
```powershell
minikube start --nodes 2 --driver=docker
minikube addons enable metrics-server   # WAJIB untuk HPA
kubectl get nodes
```

### Opsi B — AWS EKS
```powershell
eksctl create cluster --name sdg-cluster --region ap-southeast-1 --nodes 2 --node-type t3.small
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl get nodes
```

## 4. Deploy ke Kubernetes

Pasang **ingress controller** (sekali saja per cluster):
```powershell
# EKS: varian AWS (membuat Network Load Balancer untuk ingress-nginx)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/aws/deploy.yaml
# Minikube cukup: minikube addons enable ingress
kubectl get pods -n ingress-nginx        # tunggu controller Running
```

Terapkan semua manifest aplikasi (kubectl memproses seluruh file di folder `k8s/`):
```powershell
kubectl apply -f k8s/

kubectl get pods        # 2 pod Running
kubectl get svc         # air-quality-service (ClusterIP)
kubectl get ingress     # air-quality-ingress (lihat ADDRESS)
kubectl get hpa         # TARGETS harus angka %, bukan <unknown>
```

> Catatan: kode aplikasi membaca ConfigMap (`APP_TITLE`, `DEFAULT_CITY`,
> `REFRESH_INTERVAL`, dst). Jika ConfigMap diubah, lakukan
> `kubectl rollout restart deployment/air-quality-app` agar pod memuat nilai baru.

### Mengakses aplikasi (lewat Ingress)
- **EKS:** ambil alamat dari `kubectl get ingress air-quality-ingress`
  (kolom ADDRESS = hostname NLB ingress-nginx), buka di browser.
- **Minikube:** `kubectl get ingress` lalu akses lewat `minikube tunnel`
  atau IP dari `minikube ip`.

## 5. Pengujian (untuk laporan)

### Load Balancing
```powershell
kubectl get pods -o wide
kubectl get endpoints air-quality-service          # harus tampil 2 IP pod
kubectl logs -f -l app=air-quality --prefix        # akses log diaktifkan via --access-logfile
```
Buka/refresh aplikasi beberapa kali. Di log akan terlihat baris request
(`"GET /api/data ..."`) dengan **prefix nama pod yang bergantian** → bukti trafik
dibagi ke beberapa pod.

### Auto-scaling (HPA)
Terminal 1 — pantau:
```powershell
kubectl get hpa -w
kubectl top pods -l app=air-quality    # (opsional) lihat CPU per pod
```
Terminal 2 — bangkitkan beban. **Penting:** aplikasi ini sangat ringan, jadi satu
loop `wget` ke URL eksternal TIDAK cukup memicu scaling. Gunakan **banyak koneksi
paralel** dan arahkan ke **Service internal** (tanpa latensi internet):
```powershell
kubectl run load-generator --image=busybox --restart=Never -- /bin/sh -c 'for i in $(seq 40); do (while true; do wget -q -O- http://air-quality-service/ >/dev/null 2>&1; done) & done; wait'
```
Dalam ~30–60 detik: `TARGETS` melewati `50%` (bisa sampai ratusan persen) dan
`REPLICAS` naik dari 2 → 5. Hentikan beban:
```powershell
kubectl delete pod load-generator
```
Setelah beban berhenti, HPA menurunkan jumlah pod kembali ke 2 (ada jeda
stabilisasi default ~5 menit sebelum scale-down).

## 6. Membersihkan

```powershell
kubectl delete -f k8s/
minikube stop          # atau: eksctl delete cluster --name sdg-cluster --region us-east-1
```

## Catatan

- Override dari `POST /api/update` tersimpan di memori per-instance. Untuk
  konsistensi penuh lintas pod, gunakan penyimpanan bersama (Redis/RDS).
- Peta dan grafik memuat Leaflet & Chart.js dari CDN, jadi browser memerlukan
  koneksi internet saat membuka aplikasi.
