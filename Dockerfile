FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers nécessaires
COPY requirements.txt /app/
COPY detector_ha.py /app/detector.py
COPY server.py /app/
COPY run.sh /app/

# Rendre le script d'exécution exécutable
RUN chmod +x /app/run.sh

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Créer les dossiers nécessaires
RUN mkdir -p /share && \
    mkdir -p /media/cat_detector && \
    chmod -R 777 /share && \
    chmod -R 777 /media

# Exécuter le script d'exécution
CMD [ "/app/run.sh" ] 