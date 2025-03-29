from flask import Flask, render_template, send_from_directory, Response, redirect, url_for, request
import os
import glob
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

# Initialiser l'application Flask
app = Flask(__name__)

# Configuration du logger
log_file = "/share/cat_detector_logs.txt"
web_log_file = "/share/web_server_logs.txt"
os.makedirs("/share", exist_ok=True)

# Dossier où sont stockées les images
IMAGES_DIR = "/media/cat_detector"

# Obtenir le préfixe de chemin pour les URL relatives
def get_relative_url():
    return ""  # URL relatives, fonctionnent avec n'importe quel proxy

@app.route('/')
def index():
    try:
        # Créer le dossier d'images s'il n'existe pas
        os.makedirs(IMAGES_DIR, exist_ok=True)
        
        # Liste des 20 dernières captures
        images = sorted(glob.glob(f"{IMAGES_DIR}/*.jpg"), reverse=True)
        # Exclure latest.jpg
        images = [img for img in images if not img.endswith('latest.jpg')][:20]
        images = [os.path.basename(img) for img in images]
        
        # Lire les 100 dernières lignes de logs
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = f.readlines()[-100:]
        else:
            logs = ["Aucun log disponible"]
        
        # Utiliser des URLs relatives
        base_url = get_relative_url()
        app.logger.info(f"Utilisation d'URLs relatives")
        
        return template(images, logs, base_url)
    except Exception as e:
        app.logger.error(f"Erreur dans index(): {str(e)}")
        return f"Erreur: {str(e)}", 500

@app.route('/images/<path:filename>')
def image(filename):
    try:
        app.logger.info(f"Requête pour l'image: {filename} via {request.url}")
        return send_from_directory(IMAGES_DIR, filename)
    except Exception as e:
        app.logger.error(f"Erreur dans image(): {str(e)}")
        return f"Erreur: {str(e)}", 500

@app.route('/view/<path:filename>')
def view_image(filename):
    """Affiche une seule image en plein écran"""
    try:
        app.logger.info(f"Affichage de l'image en grand: {filename}")
        
        # Déterminer si c'est une image de chat avec proie
        cat_with_prey = "cat_with_prey" in filename
        cat_only = "cat_" in filename and not cat_with_prey
        
        # Construire le HTML pour afficher l'image en grand
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Image: {filename}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ margin: 0; padding: 20px; text-align: center; background-color: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                h1 {{ color: #03a9f4; margin-bottom: 20px; }}
                .image-container {{ position: relative; display: inline-block; }}
                img {{ max-width: 100%; max-height: 80vh; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }}
                .timestamp {{ font-size: 1.2em; margin: 15px 0; color: #666; }}
                .back-button {{ display: inline-block; margin: 20px 0; padding: 10px 20px; background-color: #03a9f4; 
                              color: white; text-decoration: none; border-radius: 5px; }}
                .cat-with-prey {{ border: 8px solid red; }}
                .cat {{ border: 8px solid orange; }}
                .label {{ position: absolute; top: 10px; left: 10px; padding: 5px 10px; color: white; border-radius: 3px;
                       font-weight: bold; background-color: rgba(0,0,0,0.7); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Détecteur de Chat - Image en grand</h1>
                <div class="image-container">
                    <img src="../images/{filename}" class="{
                        'cat-with-prey' if cat_with_prey else 'cat' if cat_only else ''
                    }">
                    {
                        '<div class="label">CHAT AVEC PROIE</div>' if cat_with_prey else
                        '<div class="label">CHAT</div>' if cat_only else ''
                    }
                </div>
                <div class="timestamp">{filename.replace('.jpg', '').replace('cat_with_prey_', '').replace('cat_', '')}</div>
                <a href="../" class="back-button">Retour à la liste</a>
            </div>
        </body>
        </html>
        """
        return Response(html, mimetype='text/html')
    except Exception as e:
        app.logger.error(f"Erreur dans view_image(): {str(e)}")
        return f"Erreur: {str(e)}", 500

@app.route('/latest.jpg')
def latest_image():
    """Route directe pour servir latest.jpg"""
    try:
        app.logger.info(f"Requête pour latest.jpg via {request.url}")
        return send_from_directory(IMAGES_DIR, 'latest.jpg')
    except Exception as e:
        app.logger.error(f"Erreur dans latest_image(): {str(e)}")
        return f"Erreur: {str(e)}", 500

def template(images, logs, base_url):
    """Génère le template HTML"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Détecteur de Chat - Home Assistant</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 20px; }}
            h1 {{ color: #03a9f4; }}
            .container {{ display: flex; flex-wrap: wrap; }}
            .section {{ flex: 1; min-width: 300px; margin: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
            .images {{ display: flex; flex-wrap: wrap; }}
            .image-card {{ margin: 10px; text-align: center; }}
            .image-link {{ text-decoration: none; color: inherit; cursor: pointer; }}
            img {{ max-width: 200px; max-height: 200px; border-radius: 5px; transition: transform 0.2s; }}
            img:hover {{ transform: scale(1.05); box-shadow: 0 3px 10px rgba(0,0,0,0.2); }}
            pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; overflow: auto; max-height: 400px; }}
            .timestamp {{ font-size: 0.8em; color: #666; }}
            .cat-with-prey {{ border: 3px solid red; }}
            .cat {{ border: 3px solid orange; }}
            h2 {{ border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            .refresh {{ display: inline-block; margin-left: 15px; text-decoration: none; background: #03a9f4; color: white; padding: 5px 10px; border-radius: 4px; }}
            .status {{ padding: 10px; background: #e8f5e9; border-radius: 5px; margin-bottom: 20px; }}
            .label {{ position: absolute; top: 5px; left: 5px; padding: 2px 5px; font-size: 0.7em; 
                   color: white; border-radius: 2px; background-color: rgba(0,0,0,0.7); }}
            .image-container {{ position: relative; display: inline-block; }}
        </style>
        <script>
            // Fonction pour obtenir le chemin de base actuel
            function getBasePath() {{
                const path = window.location.pathname;
                return path.substring(0, path.lastIndexOf('/') + 1);
            }}
            
            // Auto-refresh toutes les 30 secondes
            setTimeout(function() {{
                window.location.reload();
            }}, 30000);
        </script>
    </head>
    <body>
        <h1>Détecteur de Chat <a href="." class="refresh">Rafraîchir</a></h1>
        
        <div class="status">
            <strong>Statut:</strong> Le détecteur est actif et surveille votre caméra
        </div>
        
        <div class="container">
            <div class="section">
                <h2>Images récentes</h2>
                <div class="images">
    """
    
    # Ajouter les images
    for img in images:
        css_class = ""
        label = ""
        if "cat_with_prey" in img:
            css_class = "cat-with-prey"
            label = '<div class="label">PROIE</div>'
        elif "cat" in img:
            css_class = "cat"
            label = '<div class="label">CHAT</div>'
            
        html += f"""
                    <div class="image-card">
                        <a href="view/{img}" class="image-link">
                            <div class="image-container">
                                <img src="images/{img}" alt="{img}" class="{css_class}">
                                {label}
                            </div>
                            <div class="timestamp">{img.replace('.jpg', '').replace('cat_with_prey_', '').replace('cat_', '')}</div>
                        </a>
                    </div>
        """
    
    html += """
                </div>
            </div>
            <div class="section">
                <h2>Logs récents</h2>
                <pre>"""
    
    # Ajouter les logs
    for log in logs:
        html += log
    
    html += """</pre>
            </div>
        </div>
    </body>
    </html>
    """
    return Response(html, mimetype='text/html')

if __name__ == "__main__":
    try:
        # Configurer le logger principal
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stdout
        )
        
        # Créer les dossiers nécessaires
        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs("/share", exist_ok=True)
        
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
        
        # Démarrer le serveur avec les options adaptées pour un conteneur
        app.run(host='0.0.0.0', port=8099, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        # Loguer les erreurs critiques
        print(f"ERREUR CRITIQUE DANS LE SERVEUR FLASK: {str(e)}", file=sys.stderr)
        with open(web_log_file, "a") as f:
            f.write(f"ERREUR CRITIQUE: {str(e)}\n")
        raise