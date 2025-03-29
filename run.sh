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
mkdir -p /config/www
chmod -R 777 /share
chmod -R 777 /media/cat_detector
chmod -R 777 /config/www

# Configurer le logger pour écrire dans un fichier
LOG_FILE="/share/cat_detector_logs.txt"
touch $LOG_FILE
chmod 666 $LOG_FILE

# Fichier de log pour le serveur web
WEB_LOG_FILE="/share/web_server_logs.txt"
touch $WEB_LOG_FILE
chmod 666 $WEB_LOG_FILE

# Créer un lien symbolique de latest.jpg vers le dossier www
echo "Création d'un lien symbolique pour latest.jpg..."
ln -sf /media/cat_detector/latest.jpg /config/www/cat_detector_latest.jpg

# Lancer le serveur web en arrière-plan mais avec redirection des logs
echo "Démarrage du serveur web sur le port 8099..."
python /app/server.py > $WEB_LOG_FILE 2>&1 &
WEBSERVER_PID=$!

# Attendre un moment pour s'assurer que le serveur web démarre
sleep 2

# Vérifier si le serveur web a démarré
if ! pgrep -f "python /app/server.py" > /dev/null; then
    echo "ERREUR: Le serveur web n'a pas démarré correctement. Vérifiez les logs: $WEB_LOG_FILE"
    # On continue quand même pour ne pas bloquer le détecteur
fi

# Lancer le détecteur de chat
echo "Démarrage du détecteur de chat..."
python /app/detector.py

# Si le détecteur se termine, arrêter aussi le serveur web
kill $WEBSERVER_PID