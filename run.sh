#!/bin/bash

echo "Démarrage du Détecteur de Chat..."

# Vérifier l'existence des fichiers nécessaires
if [ ! -f "/app/detector.py" ]; then
    echo "ERREUR: Le fichier detector.py est introuvable!"
    exit 1
fi

if [ ! -f "/app/server.py" ]; then
    echo "ERREUR: Le fichier server.py est introuvable!"
    exit 1
fi

# Créer les dossiers nécessaires
mkdir -p /share
mkdir -p /media/cat_detector
chmod -R 777 /share
chmod -R 777 /media/cat_detector

# Configurer le logger pour écrire dans un fichier
LOG_FILE="/share/cat_detector_logs.txt"
touch $LOG_FILE
chmod 666 $LOG_FILE

# Lancer le serveur web en arrière-plan
echo "Démarrage du serveur web sur le port 8099..."
python /app/server.py > /dev/null 2>&1 &
WEBSERVER_PID=$!

# Lancer le détecteur de chat
echo "Démarrage du détecteur de chat..."
python /app/detector.py

# Si le détecteur se termine, arrêter aussi le serveur web
kill $WEBSERVER_PID 