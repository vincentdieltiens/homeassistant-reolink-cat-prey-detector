import os
import asyncio
import logging
import json
import base64
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from reolink_aio.api import Host
from reolink_aio.exceptions import ReolinkError
from abc import ABC, abstractmethod
import google.generativeai as genai

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

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
    
    def __init__(self):
        # Récupérer la clé API depuis les variables d'environnement
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            logger.error("GEMINI_API_KEY non définie dans les variables d'environnement")
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
    def __init__(self, ai_connector=None, save_images=True):
        self.camera_ip = os.getenv('REOLINK_IP')
        self.username = os.getenv('REOLINK_USERNAME')
        self.password = os.getenv('REOLINK_PASSWORD')
        self.api = Host(self.camera_ip, self.username, self.password)
        self.last_state = False
        self.last_animal = False
        self.channel = 0  # La plupart des caméras utilisent le canal 0
        
        # Option pour sauvegarder les images
        self.save_images = save_images
        
        # Créer le dossier pour les captures si nécessaire
        if self.save_images:
            self.images_dir = Path("captures")
            self.images_dir.mkdir(exist_ok=True)
        
        # Utiliser le connecteur Gemini par défaut ou celui fourni
        self.ai_connector = ai_connector or GeminiConnector()

    async def connect(self):
        """Établit la connexion avec la caméra"""
        try:
            await self.api.get_host_data()
            await self.api.get_motion_state(self.channel)
            logger.info("Connexion à la caméra établie avec succès")
        except ReolinkError as e:
            logger.error(f"Erreur lors de la connexion à la caméra: {e}")
            raise
            
    async def save_snapshot(self, image_data):
        """Sauvegarde les données d'une image"""
        try:
            # Créer un nom de fichier avec horodatage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.jpg"
            filepath = self.images_dir / filename
            
            # Enregistrer l'image
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            logger.info(f"Image sauvegardée: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'image: {e}")
            return None

    async def start_monitoring(self):
        """Démarre la surveillance des événements de la caméra"""
        try:
            animal_state = False
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
                        # Sauvegarder l'image si l'option est activée
                        if self.save_images:
                            await self.save_snapshot(image_data)
                        
                        # Analyser directement les données de l'image
                        result = await self.ai_connector.analyze_image_data(image_data)
                        
                        # Afficher les résultats de l'analyse
                        if result["cat"]:
                            if result["prey"]:
                                logger.info("🐱 ALERTE: Chat détecté avec une proie ! 🐭")
                            else:
                                logger.info("🐱 Chat détecté sans proie")
                        else:
                            logger.info("Aucun chat détecté dans l'image")
                    else:
                        logger.warning("Impossible d'obtenir une image de la caméra")

      
                self.last_state = motion_state
                self.last_animal = animal_state
                await asyncio.sleep(0.5)  # Pause de 500ms

        except Exception as e:
            logger.error(f"Erreur pendant la surveillance: {e}")
            raise

async def main():
    # Créer le détecteur avec le connecteur Gemini par défaut
    # Pour désactiver la sauvegarde des images, passer save_images=False
    detector = CatDetector(save_images=True)
    try:
        await detector.connect()
        await detector.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Arrêt du programme demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
    finally:
        await detector.api.logout()  # Déconnexion propre de la caméra

if __name__ == "__main__":
    asyncio.run(main()) 