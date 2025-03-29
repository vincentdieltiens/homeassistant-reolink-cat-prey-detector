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
mkdir -p /share/cat_detector/images
mkdir -p /media/cat_detector
mkdir -p /captures
mkdir -p /config/www
chmod -R 777 /share
chmod -R 777 /media/cat_detector
chmod -R 777 /captures
chmod -R 777 /config/www

# Configurer le logger pour écrire dans un fichier
LOG_FILE="/share/cat_detector_logs.txt"
touch $LOG_FILE
chmod 666 $LOG_FILE

# Fichier de log pour le serveur web
WEB_LOG_FILE="/share/web_server_logs.txt"
touch $WEB_LOG_FILE
chmod 666 $WEB_LOG_FILE

# Fonction pour créer des liens symboliques (uniquement si le fichier source existe)
create_symlink() {
    local source=$1
    local target=$2
    if [ -f "$source" ]; then
        echo "Création du lien symbolique: $source -> $target"
        ln -sf "$source" "$target"
        return 0
    fi
    return 1
}

# Création de liens symboliques pour latest.jpg depuis tous les emplacements possibles vers www
echo "Création des liens symboliques pour latest.jpg..."
SYMLINK_CREATED=0

# Essai 1: /media/cat_detector/latest.jpg (prioritaire)
if create_symlink "/media/cat_detector/latest.jpg" "/config/www/cat_detector_latest.jpg"; then
    SYMLINK_CREATED=1
fi

# Essai 2: /share/cat_detector/images/latest.jpg
if [ $SYMLINK_CREATED -eq 0 ] && create_symlink "/share/cat_detector/images/latest.jpg" "/config/www/cat_detector_latest.jpg"; then
    SYMLINK_CREATED=1
fi

# Essai 3: /share/cat_detector/latest.jpg
if [ $SYMLINK_CREATED -eq 0 ] && create_symlink "/share/cat_detector/latest.jpg" "/config/www/cat_detector_latest.jpg"; then
    SYMLINK_CREATED=1
fi

# Essai 4: /captures/latest.jpg
if [ $SYMLINK_CREATED -eq 0 ] && create_symlink "/captures/latest.jpg" "/config/www/cat_detector_latest.jpg"; then
    SYMLINK_CREATED=1
fi

if [ $SYMLINK_CREATED -eq 0 ]; then
    echo "AVERTISSEMENT: Aucun fichier latest.jpg trouvé pour créer un lien symbolique"
fi

# Lancer le serveur web en arrière-plan mais avec redirection des logs
echo "Démarrage du serveur web sur le port 8099..."
python /app/server.py > $WEB_LOG_FILE 2>&1 &
WEBSERVER_PID=$!

# Attendre un moment pour s'assurer que le serveur web démarre
sleep 2

# Vérifier si le serveur web a démarré
#if ! pgrep -f "python /app/server.py" > /dev/null; then
    #echo "ERREUR: Le serveur web n'a pas démarré correctement. Vérifiez les logs: $WEB_LOG_FILE"
    # On continue quand même pour ne pas bloquer le détecteur
#fi

# Lancer le détecteur de chat
echo "Démarrage du détecteur de chat..."
python /app/detector.py

# Si le détecteur se termine, arrêter aussi le serveur web
kill $WEBSERVER_PID