FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# `libpq-dev` et `gcc` pour psycopg ; `fonts-dejavu-core` pour ReportLab, qui
# sinon rend les bulletins et les fiches de paie sans accents ; `libjpeg` et
# `zlib` pour Pillow, qui traite les photos de profil et les QR codes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev gcc fonts-dejavu-core libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
