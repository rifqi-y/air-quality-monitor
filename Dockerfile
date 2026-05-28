# Gunakan image Python versi ringan
FROM python:3.9-slim

# Set direktori kerja di dalam container
WORKDIR /app

# Salin file requirements dan instal dependency
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode aplikasi ke dalam container
COPY . .

# Ekspos port yang digunakan aplikasi
EXPOSE 5000

# Jalankan aplikasi dengan gunicorn (WSGI server siap produksi).
# 2 worker; aman karena data dibangkitkan deterministik (tanpa state bersama).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "app:app"]