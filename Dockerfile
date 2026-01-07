# Usa un'immagine Python leggera
FROM python:3.9-slim

# Installa Pandoc (fondamentale per la conversione)
RUN apt-get update && apt-get install -y pandoc && rm -rf /var/lib/apt/lists/*

# Imposta la cartella di lavoro
WORKDIR /app

# Copia tutti i file del progetto nel server
COPY . .

# Installa le librerie Python (Flask, Gunicorn)
RUN pip install --no-cache-dir -r requirements.txt

# Crea le cartelle per i file (per sicurezza)
RUN mkdir -p uploads downloads

# Comando di avvio: usa Gunicorn sulla porta 10000 (standard per Render)
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]