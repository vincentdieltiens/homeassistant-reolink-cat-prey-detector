import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import json
import base64
from datetime import datetime
from pathlib import Path
import aiohttp
from reolink_aio.api import Host
from reolink_aio.exceptions import ReolinkError
from abc import ABC, abstractmethod
import google.generativeai as genai

# Configuration du logger pour écrire dans un fichier
log_file = "/share/cat_detector_logs.txt"
os.makedirs("/share", exist_ok=True)

# Configurer le logger principal
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter pour les logs
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Handler pour console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Handler pour fichier
file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Désactiver les logs de debug pour reolink_aio
logging.getLogger("reolink_aio").setLevel(logging.WARNING)

# Lire la configuration de l'add-on Home Assistant
try:
    with open('/data/options.json') as options_file:
        options = json.load(options_file)
    
    # Extraire les options
    CAMERA_IP = options.get('camera_ip', '')
    USERNAME = options.get('username', '')
    PASSWORD = options.get('password', '')
    GEMINI_API_KEY = options.get('gemini_api_key', '')
    SAVE_IMAGES = options.get('save_images', True)
    AUTOMATION_WITH_PREY = options.get('automation_with_prey', '')
    AUTOMATION_WITHOUT_PREY = options.get('automation_without_prey', '')
    
    # Vérifier les options obligatoires
    missing_fields = []
    if not CAMERA_IP:
        missing_fields.append("camera_ip")
    if not USERNAME:
        missing_fields.append("username")
    if not PASSWORD:
        missing_fields.append("password")
    if not GEMINI_API_KEY:
        missing_fields.append("gemini_api_key")
    
    if missing_fields:
        logger.error(f"Configuration incomplète. Champs manquants: {', '.join(missing_fields)}")
        exit(1)
        
except FileNotFoundError:
    logger.error("Fichier de configuration non trouvé: /data/options.json")
    logger.info("Contenu du répertoire /data :")
    import os
    logger.info(str(os.listdir('/data')))
    exit(1)
except json.JSONDecodeError:
    logger.error("Erreur de format dans le fichier de configuration")
    exit(1)
except Exception as e:
    logger.error(f"Erreur lors de la lecture de la configuration: {e}")
    exit(1)

# Interface abstraite pour les connecteurs d'IA
class AIConnector(ABC):
    """Interface de base pour tous les connecteurs d'IA d'analyse d'image"""
    
    @abstractmethod
    async def analyze_image_data(self, image_data):
        """
        Analyse les données brutes d'une image pour détecter un chat et une proie
        
        Args:
            image_data (bytes): Données binaires de l'image à analyser
            
        Returns:
            dict: Un dictionnaire avec les clés 'cat' et 'prey' (booléens)
        """
        pass


class GeminiConnector(AIConnector):
    """Connecteur pour l'API Gemini de Google utilisant le SDK officiel"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        if not self.api_key:
            logger.error("Clé API Gemini manquante")
            raise ValueError("Clé API Gemini manquante")
        
        # Initialiser le client Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    async def analyze_image_data(self, image_data):
        """
        Analyse les données brutes d'une image avec l'API Gemini pour détecter un chat et une proie
        
        Args:
            image_data (bytes): Données binaires de l'image à analyser
            
        Returns:
            dict: Un dictionnaire avec les clés 'cat' et 'prey' (booléens)
        """
        try:
            # Construire le prompt pour Gemini
            prompt = """
            Analyse cette image de caméra de surveillance.
            
            1. Y a-t-il un chat présent dans cette image? 
            2. Si un chat est présent, a-t-il une proie dans sa gueule (oiseau, souris, etc.)?
            
            Réponds uniquement avec un objet JSON formaté comme ceci:
            {
                "cat": true/false,  # true si un chat est détecté, sinon false
                "prey": true/false  # true si le chat a une proie, sinon false (toujours false s'il n'y a pas de chat)
            }
            """
            
            # Créer la requête avec contenu mixte (texte + image)
            contents = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": base64.b64encode(image_data).decode("utf-8")
                                }
                            }
                        ]
                    }
                ]
            }
            
            # Obtenir la réponse en utilisant le loop asyncio actuel
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.model.generate_content(**contents)
            )
            
            text_response = response.text
            
            # Extraire la partie JSON de la réponse
            try:
                json_str = text_response
                # Si la réponse contient du texte avant ou après le JSON, essayer d'extraire uniquement le JSON
                if "{" in text_response and "}" in text_response:
                    start = text_response.find("{")
                    end = text_response.rfind("}") + 1
                    json_str = text_response[start:end]
                    
                result = json.loads(json_str)
                logger.info(f"Analyse d'image: {result}")
                
                # Vérifier les clés requises
                if "cat" not in result or "prey" not in result:
                    logger.warning(f"Réponse incomplète de l'API: {result}")
                    return {"cat": False, "prey": False}
                    
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Erreur décodage JSON: {e}, réponse: {text_response}")
                return {"cat": False, "prey": False}
        
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse de l'image: {e}")
            return {"cat": False, "prey": False}


class CatDetector:
    def __init__(self, camera_ip, username, password, ai_connector, save_images=True):
        self.camera_ip = camera_ip
        self.username = username
        self.password = password
        self.api = Host(self.camera_ip, self.username, self.password)
        self.last_state = False
        self.last_animal = False
        self.channel = 0  # La plupart des caméras utilisent le canal 0
        
        # Option pour sauvegarder les images
        self.save_images = save_images
        
        # Créer le dossier pour les captures si nécessaire
        if self.save_images:
            # Utiliser le dossier media pour que les images soient accessibles dans l'interface HA
            self.images_dir = Path("/media/cat_detector")
            self.images_dir.mkdir(exist_ok=True, parents=True)
        
        # Utiliser le connecteur IA fourni
        self.ai_connector = ai_connector

    async def connect(self):
        """Établit la connexion avec la caméra"""
        try:
            await self.api.get_host_data()
            await self.api.get_motion_state(self.channel)
            logger.info("Connexion à la caméra établie avec succès")
        except ReolinkError as e:
            logger.error(f"Erreur lors de la connexion à la caméra: {e}")
            raise
            
    async def save_snapshot(self, image_data, detection_type=None):
        """Sauvegarde les données d'une image"""
        try:
            # Créer un nom de fichier avec horodatage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.jpg"
            
            # Ajouter un préfixe si un type de détection est fourni
            if detection_type:
                filename = f"{detection_type}_{filename}"
                
            filepath = self.images_dir / filename
            latest_path = self.images_dir / "latest.jpg"
            
            # Enregistrer l'image
            with open(filepath, "wb") as f:
                f.write(image_data)
                
            # Également sauvegarder comme latest.jpg pour HA
            with open(latest_path, "wb") as f:
                f.write(image_data)
            
            logger.info(f"Image sauvegardée: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'image: {e}")
            return None
    
    async def trigger_home_assistant_automation(self, automation_id):
        """Déclenche une automatisation dans Home Assistant"""
        if not automation_id:
            logger.warning("Aucun ID d'automatisation fourni, abandon de l'appel")
            return
        
        logger.info(f"Tentative de déclenchement de l'automatisation: {automation_id}")
            
        try:
            # Vérifier si le token Supervisor est disponible
            supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
            if not supervisor_token:
                logger.error("Token Supervisor non disponible. Vérifiez que hassio_api et auth_api sont activés dans config.json")
                return
                
            # Afficher des informations de débogage
            logger.info(f"Token Supervisor trouvé, longueur: {len(supervisor_token)}")
            logger.info(f"URL de l'API: http://supervisor/core/api/services/automation/trigger")
            
            # Préparer les en-têtes et données
            headers = {
                "Authorization": f"Bearer {supervisor_token}",
                "Content-Type": "application/json"
            }
            data = {"entity_id": automation_id}
            
            # Faire l'appel à l'API
            async with aiohttp.ClientSession() as session:
                logger.info(f"Envoi de la requête à Home Assistant: {data}")
                response = await session.post(
                    "http://supervisor/core/api/services/automation/trigger", 
                    json=data, 
                    headers=headers
                )
                
                status = response.status
                response_text = await response.text()
                
                if status == 200:
                    logger.info(f"Automatisation {automation_id} déclenchée avec succès")
                else:
                    logger.error(f"Erreur {status} lors du déclenchement de l'automatisation: {response_text}")
                    
                # Essayer une autre URL si la première échoue
                if status != 200:
                    logger.info("Tentative avec une URL alternative...")
                    response = await session.post(
                        "http://homeassistant:8123/api/services/automation/trigger", 
                        json=data, 
                        headers=headers
                    )
                    
                    status = response.status
                    response_text = await response.text()
                    
                    if status == 200:
                        logger.info(f"Automatisation {automation_id} déclenchée avec succès via URL alternative")
                    else:
                        logger.error(f"Erreur {status} lors du déclenchement via URL alternative: {response_text}")
                        
        except Exception as e:
            logger.error(f"Erreur lors de l'appel à Home Assistant: {e}")
            logger.error(f"Détails de l'erreur: {type(e).__name__}: {str(e)}")
            # Afficher la trace complète pour le débogage
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def start_monitoring(self):
        """Démarre la surveillance des événements de la caméra"""
        try:
            animal_state = False
            logger.info("Démarrage de la surveillance...")
            
            while True:
                # Vérification des événements toutes les 500ms
                motion_state = await self.api.get_motion_state(self.channel)
                ai_state = await self.api.get_ai_state(self.channel)

                animal_state = ai_state['dog_cat'] or ai_state['people']

                if animal_state and animal_state != self.last_animal:
                    logger.info(f"Chat ou personne détecté ! Timestamp: {datetime.now()}")
                        
                    # Obtenir l'image
                    image_data = await self.api.get_snapshot(self.channel)
                    
                    if image_data:
                        # D'abord analyser l'image
                        result = await self.ai_connector.analyze_image_data(image_data)
                        
                        # Ensuite sauvegarder l'image avec le type de détection approprié
                        if self.save_images:
                            detection_type = None
                            if result["cat"]:
                                if result["prey"]:
                                    detection_type = "cat_with_prey"
                                else:
                                    detection_type = "cat"
                            
                            await self.save_snapshot(image_data, detection_type)
                        
                        # Afficher les résultats de l'analyse
                        if result["cat"]:
                            if result["prey"]:
                                logger.info("🐱 ALERTE: Chat détecté avec une proie ! 🐭")
                                # Déclencher l'automatisation pour chat avec proie
                                await self.trigger_home_assistant_automation(AUTOMATION_WITH_PREY)
                            else:
                                logger.info("🐱 Chat détecté sans proie")
                                # Déclencher l'automatisation pour chat sans proie
                                await self.trigger_home_assistant_automation(AUTOMATION_WITHOUT_PREY)
                        else:
                            logger.info("Aucun chat détecté dans l'image")
                    else:
                        logger.warning("Impossible d'obtenir une image de la caméra")
                
                elif not animal_state and animal_state != self.last_animal:
                    logger.info("Animal parti")
      
                self.last_state = motion_state
                self.last_animal = animal_state
                await asyncio.sleep(0.5)  # Pause de 500ms

        except Exception as e:
            logger.error(f"Erreur pendant la surveillance: {e}")
            raise

async def main():
    # Créer le connecteur Gemini avec la clé API
    try:
        gemini_connector = GeminiConnector(GEMINI_API_KEY)
        
        # Créer le détecteur de chat
        detector = CatDetector(
            camera_ip=CAMERA_IP,
            username=USERNAME,
            password=PASSWORD,
            ai_connector=gemini_connector,
            save_images=SAVE_IMAGES
        )
        
        await detector.connect()
        await detector.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Arrêt du programme demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        raise
    finally:
        if 'detector' in locals() and detector.api:
            await detector.api.logout()  # Déconnexion propre de la caméra

if __name__ == "__main__":
    asyncio.run(main())