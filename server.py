import os
import time
import glob
import json
import logging
from datetime import datetime
from flask import Flask, render_template_string, send_from_directory, redirect, url_for, request
import sys
from logging.handlers import RotatingFileHandler
from werkzeug.middleware.proxy_fix import ProxyFix

# Configuration du logger
log_file = "/share/cat_detector_logs.txt"
web_log_file = "/share/web_server_logs.txt"
os.makedirs("/share", exist_ok=True)

# Configuration du logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Définir les chemins d'images à afficher
IMAGES_DIR = "/share/cat_detector/images"
MEDIA_DIR = "/media/cat_detector"
# Ajout de chemins supplémentaires où pourraient se trouver les anciennes images
CAPTURES_DIR = "/captures"  # Pour les images dans le dossier captures local
OLD_IMAGES_DIR = "/share/cat_detector"  # Ancien répertoire potentiel sans le sous-dossier images
LOCAL_CAPTURES_DIR = "captures"  # Dossier captures relatif au répertoire courant

# Lire les options de configuration
try:
    with open('/data/options.json') as options_file:
        options = json.load(options_file)
    
    # Extraire les options
    BURST_COUNT = options.get('burst_count', 3)
    BURST_INTERVAL = options.get('burst_interval', 0.3)
    
except Exception as e:
    logger.error(f"Erreur lors de la lecture des options: {e}")
    BURST_COUNT = 3
    BURST_INTERVAL = 0.3

app = Flask(__name__)

# Support pour le proxy Ingress de Home Assistant
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# Classe pour configurer les URLs avec le préfixe d'ingress
class IngressMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Détecte le préfixe d'ingress depuis l'en-tête X-Ingress-Path
        ingress_path = environ.get('HTTP_X_INGRESS_PATH', '')
        if ingress_path:
            environ['SCRIPT_NAME'] = ingress_path
            logger.info(f"Ingress détecté: {ingress_path}")
        return self.app(environ, start_response)

# Appliquer le middleware d'ingress
app.wsgi_app = IngressMiddleware(app.wsgi_app)

# Template HTML principal
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Détecteur de Chat</title>
    <style>
        body {
            font-family: 'Roboto', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background-color: #4CAF50;
            color: white;
            padding: 10px 0;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            margin: 0;
            padding: 0 20px;
            font-size: 24px;
        }
        .status-box {
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .images-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
        }
        .image-card {
            background-color: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .image-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .image-card a {
            display: block;
        }
        .image-card img {
            width: 100%;
            height: 200px;
            object-fit: cover;
            display: block;
        }
        .image-info {
            padding: 10px;
        }
        .image-info p {
            margin: 5px 0;
            font-size: 14px;
        }
        .timestamp {
            color: #666;
        }
        .cat-with-prey {
            color: #f44336;
            font-weight: bold;
        }
        .cat {
            color: #2196F3;
        }
        .status {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-active {
            background-color: #4CAF50;
        }
        .status-inactive {
            background-color: #f44336;
        }
        .refresh-btn {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-bottom: 20px;
            transition: background-color 0.3s;
        }
        .refresh-btn:hover {
            background-color: #45a049;
        }
        .no-images {
            grid-column: 1 / -1;
            padding: 20px;
            text-align: center;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .footer {
            margin-top: 30px;
            text-align: center;
            font-size: 14px;
            color: #666;
        }
        .badge {
            display: inline-block;
            background-color: #4CAF50;
            color: white;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            text-align: center;
            line-height: 24px;
            font-size: 12px;
            margin-left: 5px;
        }
        .view-all {
            display: inline-block;
            background-color: #2196F3;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            margin-top: 5px;
            text-decoration: none;
            transition: background-color 0.3s;
        }
        .view-all:hover {
            background-color: #0b7dda;
        }
    </style>
</head>
<body>
    <header>
        <h1>Détecteur de Chat</h1>
    </header>
    
    <div class="container">
        <div class="status-box">
            <div class="status">
                <div class="status-dot status-active"></div>
                <h2>Détecteur actif</h2>
            </div>
            <p>Ce système surveille l'activité des chats et détecte s'ils portent une proie.</p>
            <p><strong>Mode rafale:</strong> {{ burst_count }} images par détection, intervalle de {{ burst_interval }}s</p>
            <p><strong>Dernière mise à jour:</strong> {{ last_updated }}</p>
        </div>
        
        <button class="refresh-btn" onclick="window.location.reload();">Rafraîchir</button>
        
        <div class="images-container">
            {% if image_groups %}
                {% for group in image_groups %}
                    <div class="image-card">
                        <a href="{{ url_for('view_image', filename=group['best_image']['filename']) }}">
                            <img src="{{ url_for('serve_image', filename=group['best_image']['filename']) }}" alt="Photo de chat">
                        </a>
                        <div class="image-info">
                            <p class="timestamp">{{ group['date'] }}</p>
                            {% if group['detection_type'] == 'cat_with_prey' %}
                                <p class="cat-with-prey">Chat avec proie</p>
                            {% elif group['detection_type'] == 'cat' %}
                                <p class="cat">Chat sans proie</p>
                            {% else %}
                                <p>Mouvement détecté</p>
                            {% endif %}
                            {% if group['count'] > 1 %}
                                <p>Images: <span class="badge">{{ group['count'] }}</span>
                                <a href="{{ url_for('view_group', group_id=group['group_id']) }}" class="view-all">Voir toutes</a>
                                </p>
                            {% endif %}
                        </div>
                    </div>
                {% endfor %}
            {% else %}
                <div class="no-images">
                    <p>Aucune image capturée pour le moment.</p>
                </div>
            {% endif %}
        </div>
        
        <div class="footer">
            <p>Détecteur de Chat v0.7 - Addon Home Assistant</p>
        </div>
    </div>
</body>
</html>
"""

# Template pour la vue d'image en plein écran
VIEW_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vue d'image - Détecteur de Chat</title>
    <style>
        body {
            font-family: 'Roboto', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #000;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        .image-container {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
        }
        img {
            max-width: 100%;
            max-height: 90vh;
            object-fit: contain;
        }
        .actions {
            position: fixed;
            top: 20px;
            left: 20px;
            z-index: 10;
        }
        .back-btn {
            background-color: rgba(76, 175, 80, 0.8);
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            transition: background-color 0.3s;
            text-decoration: none;
            display: inline-block;
        }
        .back-btn:hover {
            background-color: rgba(69, 160, 73, 1);
        }
        .image-info {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 10px 20px;
            text-align: center;
        }
        .image-info p {
            margin: 5px 0;
        }
        .cat-with-prey {
            color: #ff6b6b;
            font-weight: bold;
        }
        .cat {
            color: #63cdff;
        }
    </style>
</head>
<body>
    <div class="actions">
        <a href="{{ url_for('index') }}" class="back-btn">Retour</a>
    </div>
    
    <div class="image-container">
        <img src="{{ url_for('serve_image', filename=filename) }}" alt="Photo de chat">
    </div>
    
    <div class="image-info">
        <p>{{ filename }}</p>
        {% if 'cat_with_prey' in filename %}
            <p class="cat-with-prey">Chat avec proie</p>
        {% elif 'cat' in filename %}
            <p class="cat">Chat sans proie</p>
        {% else %}
            <p>Mouvement détecté</p>
        {% endif %}
    </div>
</body>
</html>
"""

# Template pour la vue d'un groupe d'images
GROUP_VIEW_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vue du groupe - Détecteur de Chat</title>
    <style>
        body {
            font-family: 'Roboto', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background-color: #4CAF50;
            color: white;
            padding: 10px 0;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
        }
        h1 {
            margin: 0;
            padding: 0 20px;
            font-size: 24px;
        }
        .back-btn {
            background-color: white;
            color: #4CAF50;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-left: 20px;
            text-decoration: none;
            display: inline-block;
        }
        .back-btn:hover {
            background-color: #f1f1f1;
        }
        .images-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        .image-card {
            background-color: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .image-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .image-card a {
            display: block;
        }
        .image-card img {
            width: 100%;
            height: 250px;
            object-fit: cover;
            display: block;
        }
        .image-info {
            padding: 10px;
        }
        .image-info p {
            margin: 5px 0;
            font-size: 14px;
        }
        .timestamp {
            color: #666;
        }
        .sequence {
            color: #2196F3;
            font-weight: bold;
        }
        .best-label {
            background-color: #4CAF50;
            color: white;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            display: inline-block;
            margin-left: 10px;
        }
        .group-info {
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .cat-with-prey {
            color: #f44336;
            font-weight: bold;
        }
        .cat {
            color: #2196F3;
        }
    </style>
</head>
<body>
    <header>
        <h1>Séquence d'images</h1>
        <a href="{{ url_for('index') }}" class="back-btn">Retour</a>
    </header>
    
    <div class="container">
        <div class="group-info">
            <h2>{{ group['date'] }}</h2>
            <p>
                {% if group['detection_type'] == 'cat_with_prey' %}
                    <span class="cat-with-prey">Chat avec proie</span>
                {% elif group['detection_type'] == 'cat' %}
                    <span class="cat">Chat sans proie</span>
                {% else %}
                    Mouvement détecté
                {% endif %}
            </p>
            <p>Groupe: {{ group['group_id'] }}</p>
            <p>{{ group['count'] }} images dans cette séquence</p>
        </div>
        
        <div class="images-grid">
            {% for image in group['images'] %}
                <div class="image-card">
                    <a href="{{ url_for('view_image', filename=image['filename']) }}">
                        <img src="{{ url_for('serve_image', filename=image['filename']) }}" alt="Photo de chat">
                    </a>
                    <div class="image-info">
                        <p class="sequence">
                            Séquence: {{ image['sequence_index'] if image['sequence_index'] else 'N/A' }}
                            {% if image['is_best'] %}
                                <span class="best-label">Meilleure</span>
                            {% endif %}
                        </p>
                        <p class="timestamp">{{ image['date'] }}</p>
                    </div>
                </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Route principale affichant les images récentes"""
    try:
        # Récupérer le préfixe d'ingress et le logger
        ingress_path = request.headers.get('X-Ingress-Path', '')
        if ingress_path:
            logger.info(f"En-tête X-Ingress-Path trouvé: {ingress_path}")
        
        # Trouver toutes les images
        image_files = []
        for ext in ['jpg', 'jpeg', 'png']:
            image_files.extend(glob.glob(os.path.join(IMAGES_DIR, f'*.{ext}')))
            
            # Chercher aussi dans le répertoire media si différent
            if MEDIA_DIR != IMAGES_DIR:
                image_files.extend(glob.glob(os.path.join(MEDIA_DIR, f'*.{ext}')))
                
            # Chercher aussi dans le répertoire captures si différent
            image_files.extend(glob.glob(os.path.join(CAPTURES_DIR, f'*.{ext}')))
                
            # Chercher aussi dans l'ancien répertoire potentiel
            image_files.extend(glob.glob(os.path.join(OLD_IMAGES_DIR, f'*.{ext}')))
                
            # Chercher aussi dans le dossier captures local
            image_files.extend(glob.glob(os.path.join(LOCAL_CAPTURES_DIR, f'*.{ext}')))
        
        # Ignorer l'image "latest.jpg"
        image_files = [f for f in image_files if "latest.jpg" not in f]
        
        # liste des images dans le logs
        logger.info(f"Images trouvées: {image_files}")
        
        # Créer une liste d'objets image
        images = []
        image_groups = {}  # Dictionnaire pour regrouper les images par group_id
        
        for image_path in image_files:
            filename = os.path.basename(image_path)
            timestamp = os.path.getmtime(image_path)
            date = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(timestamp))
            
            # Extraire le group_id du nom de fichier
            # Format attendu: type_best_groupid_seqX.jpg ou type_groupid_seqX.jpg
            parts = os.path.splitext(filename)[0].split('_')
            
            # Traiter les différents formats possibles
            group_id = None
            is_best = False
            sequence_index = None
            detection_type = None
            
            # Format 1: type_best_groupid_seqX.jpg
            if len(parts) >= 4 and 'best' in parts and any(p.startswith('seq') for p in parts):
                detection_type = parts[0] if parts[0] in ['cat', 'cat_with_prey'] else None
                is_best = 'best' in parts
                
                # Trouver le group_id (la partie avant seq)
                seq_index = next((i for i, p in enumerate(parts) if p.startswith('seq')), None)
                if seq_index is not None and seq_index > 0:
                    group_id = parts[seq_index-1]
                    sequence_index = parts[seq_index][3:]  # Extraire le numéro après 'seq'
            
            # Format 2: type_groupid_seqX.jpg
            elif len(parts) >= 3 and any(p.startswith('seq') for p in parts):
                detection_type = parts[0] if parts[0] in ['cat', 'cat_with_prey'] else None
                
                # Trouver le group_id (la partie avant seq)
                seq_index = next((i for i, p in enumerate(parts) if p.startswith('seq')), None)
                if seq_index is not None and seq_index > 0:
                    group_id = parts[seq_index-1]
                    sequence_index = parts[seq_index][3:]  # Extraire le numéro après 'seq'
            
            # Format 3: Pour l'ancien format (type_timestamp.jpg)
            elif len(parts) == 2:
                detection_type = parts[0] if parts[0] in ['cat', 'cat_with_prey'] else None
                group_id = parts[1]  # Timestamp sert de group_id
                is_best = True  # Considéré comme la meilleure image
            
            # Si group_id n'a pas été trouvé, utiliser le nom du fichier comme fallback
            if not group_id:
                group_id = os.path.splitext(filename)[0]
                is_best = True  # Par défaut, considérer comme la meilleure image
            
            # Créer l'objet image
            image_info = {
                'filename': filename,
                'date': date,
                'timestamp': timestamp,
                'group_id': group_id,
                'is_best': is_best,
                'sequence_index': sequence_index,
                'detection_type': detection_type
            }
            
            # Ajouter l'image au groupe correspondant
            if group_id not in image_groups:
                image_groups[group_id] = []
            image_groups[group_id].append(image_info)
            
            # Aussi l'ajouter à la liste complète
            images.append(image_info)
        
        # Trier les images dans chaque groupe par timestamp
        for group_id, group_images in image_groups.items():
            group_images.sort(key=lambda x: int(x['sequence_index']) if x['sequence_index'] and x['sequence_index'].isdigit() else 0)
        
        # Trier les groupes par timestamp (plus récents en premier)
        # Utiliser le timestamp de la meilleure image ou de la première image du groupe
        sorted_groups = []
        for group_id, group_images in image_groups.items():
            # Trouver la meilleure image du groupe
            best_image = next((img for img in group_images if img['is_best']), group_images[0] if group_images else None)
            
            if best_image:
                sorted_groups.append({
                    'group_id': group_id,
                    'images': group_images,
                    'best_image': best_image,
                    'timestamp': best_image['timestamp'],
                    'date': best_image['date'],
                    'detection_type': best_image['detection_type'],
                    'count': len(group_images)
                })
        
        # Trier les groupes par timestamp (plus récents en premier)
        sorted_groups.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Limiter à 50 groupes maximum
        sorted_groups = sorted_groups[:50]
        
        # Dernier horodatage de mise à jour
        last_updated = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())
        
        return render_template_string(
            HTML_TEMPLATE, 
            image_groups=sorted_groups,
            last_updated=last_updated,
            burst_count=BURST_COUNT,
            burst_interval=BURST_INTERVAL
        )
    except Exception as e:
        logger.error(f"Erreur dans index(): {str(e)}")
        return f"Erreur: {str(e)}", 500

@app.route('/view/<path:filename>')
def view_image(filename):
    """Afficher une image en plein écran"""
    # Récupérer le préfixe d'ingress pour le logging
    ingress_path = request.headers.get('X-Ingress-Path', '')
    if ingress_path:
        logger.info(f"[view_image] En-tête X-Ingress-Path trouvé: {ingress_path}")
    
    return render_template_string(VIEW_TEMPLATE, filename=filename)

@app.route('/view_group/<group_id>')
def view_group(group_id):
    """Afficher toutes les images d'un groupe"""
    try:
        # Récupérer le préfixe d'ingress pour le logging
        ingress_path = request.headers.get('X-Ingress-Path', '')
        if ingress_path:
            logger.info(f"[view_group] En-tête X-Ingress-Path trouvé: {ingress_path}")
        
        # Trouver toutes les images avec ce group_id
        image_files = []
        for ext in ['jpg', 'jpeg', 'png']:
            for dir_path in [IMAGES_DIR, MEDIA_DIR, CAPTURES_DIR, OLD_IMAGES_DIR, LOCAL_CAPTURES_DIR]:
                if dir_path:
                    pattern = os.path.join(dir_path, f"*{group_id}*.{ext}")
                    image_files.extend(glob.glob(pattern))
        
        # Créer la liste d'objets image pour ce groupe
        group_images = []
        
        for image_path in image_files:
            if "latest.jpg" in image_path:
                continue
                
            filename = os.path.basename(image_path)
            timestamp = os.path.getmtime(image_path)
            date = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(timestamp))
            
            # Déterminer si c'est la meilleure image
            is_best = 'best' in filename
            
            # Essayer d'extraire l'index de séquence (seq0, seq1, etc.)
            sequence_index = None
            parts = os.path.splitext(filename)[0].split('_')
            for part in parts:
                if part.startswith('seq') and part[3:].isdigit():
                    sequence_index = part[3:]
                    break
            
            # Déterminer le type de détection
            detection_type = None
            if 'cat_with_prey' in filename:
                detection_type = 'cat_with_prey'
            elif 'cat_' in filename:
                detection_type = 'cat'
            
            group_images.append({
                'filename': filename,
                'date': date,
                'timestamp': timestamp,
                'is_best': is_best,
                'sequence_index': sequence_index,
                'detection_type': detection_type
            })
        
        # Trier les images par index de séquence
        group_images.sort(key=lambda x: int(x['sequence_index']) if x['sequence_index'] and x['sequence_index'].isdigit() else 999)
        
        # Si aucune image trouvée
        if not group_images:
            return "Groupe non trouvé", 404
        
        # Trouver la meilleure image ou la première image
        best_image = next((img for img in group_images if img['is_best']), group_images[0] if group_images else None)
        
        # Créer l'objet groupe
        group = {
            'group_id': group_id,
            'images': group_images,
            'best_image': best_image,
            'date': best_image['date'] if best_image else '',
            'detection_type': best_image['detection_type'] if best_image else None,
            'count': len(group_images)
        }
        
        return render_template_string(GROUP_VIEW_TEMPLATE, group=group)
    except Exception as e:
        logger.error(f"Erreur dans view_group(): {str(e)}")
        return f"Erreur: {str(e)}", 500

# Fonction utilitaire pour rechercher une image dans tous les dossiers possibles
def find_image_path(filename):
    """Recherche un fichier image dans tous les dossiers possibles et retourne le chemin complet et le dossier parent."""
    # Vérifier d'abord dans le répertoire media (prioritaire)
    media_path = os.path.join(MEDIA_DIR, filename)
    if os.path.exists(media_path):
        app.logger.info(f"Image {filename} trouvée dans {MEDIA_DIR}")
        return MEDIA_DIR, filename
    
    # Vérifier dans le répertoire share/images
    share_path = os.path.join(IMAGES_DIR, filename)
    if os.path.exists(share_path):
        app.logger.info(f"Image {filename} trouvée dans {IMAGES_DIR}")
        return IMAGES_DIR, filename
    
    # Vérifier dans le répertoire captures dans le container
    captures_path = os.path.join(CAPTURES_DIR, filename)
    if os.path.exists(captures_path):
        app.logger.info(f"Image {filename} trouvée dans {CAPTURES_DIR}")
        return CAPTURES_DIR, filename
        
    # Vérifier dans l'ancien répertoire potentiel
    old_path = os.path.join(OLD_IMAGES_DIR, filename)
    if os.path.exists(old_path):
        app.logger.info(f"Image {filename} trouvée dans {OLD_IMAGES_DIR}")
        return OLD_IMAGES_DIR, filename
        
    # Vérifier dans le dossier captures local
    local_captures_path = os.path.join(LOCAL_CAPTURES_DIR, filename)
    if os.path.exists(local_captures_path):
        app.logger.info(f"Image {filename} trouvée dans {LOCAL_CAPTURES_DIR}")
        return LOCAL_CAPTURES_DIR, filename
    
    # Image non trouvée
    app.logger.warning(f"Image {filename} non trouvée dans aucun dossier")
    return None, None

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Servir les images depuis le répertoire d'images"""
    # Récupérer le préfixe d'ingress pour le logging
    ingress_path = request.headers.get('X-Ingress-Path', '')
    if ingress_path:
        logger.info(f"[serve_image] En-tête X-Ingress-Path trouvé: {ingress_path}, servant l'image: {filename}")
    
    directory, file_to_serve = find_image_path(filename)
    if directory and file_to_serve:
        return send_from_directory(directory, file_to_serve)
    
    # Si l'image n'existe pas
    return "Image non trouvée", 404

@app.route('/latest.jpg')
def latest_image():
    """Route directe pour servir latest.jpg"""
    # Récupérer le préfixe d'ingress pour le logging
    ingress_path = request.headers.get('X-Ingress-Path', '')
    if ingress_path:
        logger.info(f"[latest_image] En-tête X-Ingress-Path trouvé: {ingress_path}")
    
    directory, file_to_serve = find_image_path('latest.jpg')
    if directory and file_to_serve:
        return send_from_directory(directory, file_to_serve)
    
    # Si l'image n'existe pas
    return "Image latest.jpg non trouvée", 404

@app.route('/health')
def health_check():
    """Endpoint de vérification de santé pour Home Assistant"""
    return "OK", 200

if __name__ == '__main__':
    try:
        # Configurer le logger principal
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stdout
        )

        # Créer les répertoires s'ils n'existent pas
        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(MEDIA_DIR, exist_ok=True)

        # Configurer un handler pour logger dans le fichier
        file_handler = RotatingFileHandler(web_log_file, maxBytes=1024*1024, backupCount=3)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Configurer un handler pour logger sur la console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Ajouter les handlers au logger de Flask
        app.logger.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        
        # Log de démarrage
        app.logger.info("Démarrage du serveur Flask sur 0.0.0.0:8099")
        app.logger.info("Support pour Home Assistant Ingress activé - URLs adaptés automatiquement")
        app.logger.info("Les URLs d'images utiliseront le préfixe d'ingress quand nécessaire")

        # Démarrer le serveur
        app.run(host='0.0.0.0', port=8099, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        # Loguer les erreurs critiques
        print(f"ERREUR CRITIQUE DANS LE SERVEUR FLASK: {str(e)}", file=sys.stderr)
        with open(web_log_file, "a") as f:
            f.write(f"ERREUR CRITIQUE: {str(e)}\n")
        raise