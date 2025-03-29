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
import threading
import queue
import uuid

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
    BURST_COUNT = options.get('burst_count', 3)  # Nouveau paramètre: nombre d'images en rafale
    BURST_INTERVAL = options.get('burst_interval', 0.3)  # Nouvel intervalle entre les photos en secondes
    
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

    async def analyze_image_burst(self, image_data_list):
        """
        Analyse un groupe d'images pour détecter un chat et une proie dans l'une d'elles
        
        Args:
            image_data_list (list): Liste de données binaires d'images à analyser
            
        Returns:
            dict: Un dictionnaire avec les clés 'cat', 'prey' et 'best_image_index'
        """
        if not image_data_list:
            return {"cat": False, "prey": False, "best_image_index": -1}
            
        results = []
        for i, image_data in enumerate(image_data_list):
            result = await self.analyze_image_data(image_data)
            result["index"] = i
            results.append(result)
            
            # Si on a détecté une proie, on peut s'arrêter là
            if result["cat"] and result["prey"]:
                logger.info(f"Proie détectée dans l'image {i+1}/{len(image_data_list)} de la rafale")
                return {"cat": True, "prey": True, "best_image_index": i}
        
        # Si aucune proie n'a été trouvée, chercher le meilleur résultat (chat sans proie)
        for result in results:
            if result["cat"]:
                return {"cat": True, "prey": False, "best_image_index": result["index"]}
                
        # Si aucun chat n'a été trouvé
        return {"cat": False, "prey": False, "best_image_index": -1}


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

    async def analyze_image_burst(self, image_data_list):
        """
        Analyse un groupe d'images en même temps pour détecter un chat et une proie
        
        Args:
            image_data_list (list): Liste de données binaires d'images à analyser
            
        Returns:
            dict: Un dictionnaire avec les clés 'cat', 'prey' et 'best_image_index'
        """
        if not image_data_list:
            return {"cat": False, "prey": False, "best_image_index": -1}
            
        # Construire le prompt pour Gemini avec plusieurs images
        prompt = """
        Analyse ces images de caméra de surveillance. Elles ont été prises en rafale en quelques fractions de seconde.
        
        1. Y a-t-il un chat présent dans l'une de ces images? 
        2. Si un chat est présent, a-t-il une proie dans sa gueule (oiseau, souris, etc.) dans l'une des images?
        
        Réponds uniquement avec un objet JSON formaté comme ceci:
        {
            "cat": true/false,  # true si un chat est détecté dans au moins une image, sinon false
            "prey": true/false,  # true si un chat a une proie dans au moins une image, sinon false
            "best_image_index": 0-N,  # l'index (commençant à 0) de la meilleure image montrant un chat avec une proie,
                                     # ou simplement un chat si aucune proie n'est visible
        }
        """
        
        # Créer la requête avec contenu mixte (texte + images)
        try:
            contents = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            }
            
            # Ajouter chaque image à la requête
            for i, image_data in enumerate(image_data_list):
                contents["contents"][0]["parts"].append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(image_data).decode("utf-8")
                    }
                })
            
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
                logger.info(f"Analyse d'images en rafale: {result}")
                
                # Vérifier les clés requises
                if "cat" not in result or "prey" not in result or "best_image_index" not in result:
                    logger.warning(f"Réponse incomplète de l'API: {result}")
                    # Fallback à l'analyse individuelle
                    return await super().analyze_image_burst(image_data_list)
                
                # Vérifier que l'index est valide
                if result["best_image_index"] >= len(image_data_list) or result["best_image_index"] < 0:
                    logger.warning(f"Index d'image invalide: {result['best_image_index']}")
                    result["best_image_index"] = 0
                    
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Erreur décodage JSON: {e}, réponse: {text_response}")
                # Fallback à l'analyse individuelle
                return await super().analyze_image_burst(image_data_list)
        
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des images en rafale: {e}")
            # Fallback à l'analyse individuelle
            return await super().analyze_image_burst(image_data_list)


# Structure pour représenter une tâche d'analyse d'image
class ImageAnalysisTask:
    def __init__(self, session_id, image_data_list):
        self.session_id = session_id  # Identifiant unique pour cette rafale d'images
        self.image_data_list = image_data_list  # Liste des données d'images
        self.timestamp = datetime.now()


class ImageAnalysisWorker:
    """Classe pour traiter les analyses d'images en arrière-plan"""
    
    def __init__(self, ai_connector, detector):
        self.task_queue = queue.Queue()  # File d'attente pour les tâches d'analyse
        self.ai_connector = ai_connector
        self.detector = detector
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()
    
    def add_task(self, session_id, image_data_list):
        """Ajoute une tâche à la file d'attente"""
        task = ImageAnalysisTask(session_id, image_data_list)
        self.task_queue.put(task)
        logger.info(f"Tâche d'analyse ajoutée à la file d'attente, session_id: {session_id}, {len(image_data_list)} images")
    
    def stop(self):
        """Arrête le thread de traitement"""
        self.running = False
        if self.worker_thread.is_alive():
            self.task_queue.put(None)  # Sentinel pour arrêter le thread
            self.worker_thread.join(timeout=2.0)
    
    def _worker_loop(self):
        """Boucle principale du thread de traitement"""
        async def process_task(task):
            try:
                logger.info(f"Traitement de la session {task.session_id} avec {len(task.image_data_list)} images")
                
                # Analyser les images
                result = await self.ai_connector.analyze_image_burst(task.image_data_list)
                
                # Traiter les résultats
                best_index = result.get("best_image_index", 0)
                if best_index >= 0 and best_index < len(task.image_data_list):
                    best_image = task.image_data_list[best_index]
                    
                    # Sauvegarder la meilleure image
                    if self.detector.save_images:
                        detection_type = None
                        if result["cat"]:
                            if result["prey"]:
                                detection_type = "cat_with_prey"
                            else:
                                detection_type = "cat"
                        
                        await self.detector.save_snapshot(best_image, detection_type)
                    
                    # Déclencher les automatisations appropriées
                    if result["cat"]:
                        if result["prey"]:
                            logger.info("🐱 ALERTE: Chat détecté avec une proie ! 🐭")
                            await self.detector.trigger_home_assistant_automation(AUTOMATION_WITH_PREY)
                        else:
                            logger.info("🐱 Chat détecté sans proie")
                            await self.detector.trigger_home_assistant_automation(AUTOMATION_WITHOUT_PREY)
                    else:
                        logger.info("Aucun chat détecté dans les images")
                
            except Exception as e:
                logger.error(f"Erreur lors du traitement d'une tâche d'analyse: {e}")
        
        while self.running:
            try:
                task = self.task_queue.get(timeout=1.0)
                if task is None:  # Sentinel
                    break
                
                # Traiter la tâche de manière asynchrone
                asyncio.run(process_task(task))
                
                self.task_queue.task_done()
            except queue.Empty:
                pass  # Aucune tâche dans la file d'attente
            except Exception as e:
                logger.error(f"Erreur dans le worker d'analyse: {e}")


class CatDetector:
    def __init__(self, camera_ip, username, password, ai_connector, save_images=True, burst_count=3, burst_interval=0.3):
        self.camera_ip = camera_ip
        self.username = username
        self.password = password
        self.api = Host(self.camera_ip, self.username, self.password)
        self.last_state = False
        self.last_animal = False
        self.channel = 0  # La plupart des caméras utilisent le canal 0
        
        # Option pour sauvegarder les images
        self.save_images = save_images
        
        # Paramètres pour la prise de photos en rafale
        self.burst_count = burst_count
        self.burst_interval = burst_interval
        
        # Créer le dossier pour les captures si nécessaire
        if self.save_images:
            # Utiliser le dossier media pour que les images soient accessibles dans l'interface HA
            self.images_dir = Path("/media/cat_detector")
            self.images_dir.mkdir(exist_ok=True, parents=True)
        
        # Utiliser le connecteur IA fourni
        self.ai_connector = ai_connector
        
        # Créer le worker d'analyse d'images
        self.analysis_worker = ImageAnalysisWorker(ai_connector, self)
        
        # Flag pour indiquer si une analyse est en cours
        self.analysis_in_progress = False

    async def connect(self):
        """Établit la connexion avec la caméra"""
        try:
            await self.api.get_host_data()
            await self.api.get_motion_state(self.channel)
            logger.info("Connexion à la caméra établie avec succès")
        except ReolinkError as e:
            logger.error(f"Erreur lors de la connexion à la caméra: {e}")
            raise
    
    async def capture_image_burst(self):
        """Capture plusieurs images en rafale"""
        images = []
        try:
            for i in range(self.burst_count):
                # Prendre une photo
                image_data = await self.api.get_snapshot(self.channel)
                
                if image_data:
                    images.append(image_data)
                    logger.info(f"Image {i+1}/{self.burst_count} capturée ({len(image_data)} octets)")
                else:
                    logger.warning(f"Échec de capture de l'image {i+1}/{self.burst_count}")
                
                # Attendre un peu avant la prochaine photo (sauf pour la dernière)
                if i < self.burst_count - 1:
                    await asyncio.sleep(self.burst_interval)
        
        except Exception as e:
            logger.error(f"Erreur lors de la capture d'images en rafale: {e}")
        
        return images
            
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
                    
                    # Générer un ID de session unique pour cette détection
                    session_id = str(uuid.uuid4())
                    
                    # Prendre plusieurs photos en rafale
                    image_data_list = await self.capture_image_burst()
                    
                    if image_data_list:
                        # Envoyer les images au worker d'analyse (traitement asynchrone)
                        self.analysis_worker.add_task(session_id, image_data_list)
                    else:
                        logger.warning("Aucune image capturée en rafale")
                
                elif not animal_state and animal_state != self.last_animal:
                    logger.info("Animal parti")
      
                self.last_state = motion_state
                self.last_animal = animal_state
                await asyncio.sleep(0.5)  # Pause de 500ms

        except Exception as e:
            logger.error(f"Erreur pendant la surveillance: {e}")
            raise
        finally:
            # Arrêter le worker d'analyse
            self.analysis_worker.stop()

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
            save_images=SAVE_IMAGES,
            burst_count=BURST_COUNT,
            burst_interval=BURST_INTERVAL
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