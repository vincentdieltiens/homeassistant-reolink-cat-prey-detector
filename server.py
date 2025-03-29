from flask import Flask, render_template, send_from_directory, Response
import os
import glob
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

app = Flask(__name__)

# Configuration du logger
log_file = "/share/cat_detector_logs.txt"
os.makedirs("/share", exist_ok=True)

@app.route('/')
def index():
    # Créer le dossier d'images s'il n'existe pas
    image_dir = "/media/cat_detector"
    os.makedirs(image_dir, exist_ok=True)
    
    # Liste des 20 dernières captures
    images = sorted(glob.glob(f"{image_dir}/*.jpg"), reverse=True)
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
    
    return template(images, logs)

@app.route('/images/<path:filename>')
def image(filename):
    return send_from_directory('/media/cat_detector', filename)

def template(images, logs):
    """Génère le template HTML"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Détecteur de Chat - Home Assistant</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; margin: 0; padding: 20px; }
            h1 { color: #03a9f4; }
            .container { display: flex; flex-wrap: wrap; }
            .section { flex: 1; min-width: 300px; margin: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
            .images { display: flex; flex-wrap: wrap; }
            .image-card { margin: 10px; text-align: center; }
            img { max-width: 200px; max-height: 200px; border-radius: 5px; }
            pre { background: #f5f5f5; padding: 10px; border-radius: 5px; overflow: auto; max-height: 400px; }
            .timestamp { font-size: 0.8em; color: #666; }
            .cat-with-prey { border: 3px solid red; }
            .cat { border: 3px solid orange; }
            h2 { border-bottom: 1px solid #eee; padding-bottom: 10px; }
            .refresh { display: inline-block; margin-left: 15px; text-decoration: none; background: #03a9f4; color: white; padding: 5px 10px; border-radius: 4px; }
            .status { padding: 10px; background: #e8f5e9; border-radius: 5px; margin-bottom: 20px; }
        </style>
        <script>
            // Auto-refresh toutes les 30 secondes
            setTimeout(function() {
                window.location.reload();
            }, 30000);
        </script>
    </head>
    <body>
        <h1>Détecteur de Chat <a href="/" class="refresh">Rafraîchir</a></h1>
        
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
        if "cat_with_prey" in img:
            css_class = "cat-with-prey"
        elif "cat" in img:
            css_class = "cat"
            
        html += f"""
                    <div class="image-card">
                        <img src="/images/{img}" alt="{img}" class="{css_class}">
                        <div class="timestamp">{img.replace('.jpg', '').replace('cat_with_prey_', '').replace('cat_', '')}</div>
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
    # Configurer le logger
    logging.basicConfig(level=logging.INFO)
    
    # Créer les dossiers nécessaires
    os.makedirs("/media/cat_detector", exist_ok=True)
    os.makedirs("/share", exist_ok=True)
    
    # Démarrer le serveur
    app.run(host='0.0.0.0', port=8099)