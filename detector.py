import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from reolink_aio.api import Host
from reolink_aio.exceptions import ReolinkError

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

class CatDetector:
    def __init__(self):
        self.camera_ip = os.getenv('REOLINK_IP')
        self.username = os.getenv('REOLINK_USERNAME')
        self.password = os.getenv('REOLINK_PASSWORD')
        self.api = Host(self.camera_ip, self.username, self.password)
        self.last_state = False
        self.last_animal = False
        self.channel = 0  # La plupart des caméras utilisent le canal 0
        
        # Créer le dossier pour les captures si nécessaire
        self.images_dir = Path("captures")
        self.images_dir.mkdir(exist_ok=True)

    async def connect(self):
        """Établit la connexion avec la caméra"""
        try:
            await self.api.get_host_data()
            await self.api.get_motion_state(self.channel)
            logger.info("Connexion à la caméra établie avec succès")
        except ReolinkError as e:
            logger.error(f"Erreur lors de la connexion à la caméra: {e}")
            raise
            
    async def save_snapshot(self):
        """Récupère et sauvegarde une image de la caméra"""
        try:
            # Obtenir l'image
            image_data = await self.api.get_snapshot(self.channel)
            
            if image_data:
                # Créer un nom de fichier avec horodatage
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}.jpg"
                filepath = self.images_dir / filename
                
                # Enregistrer l'image
                with open(filepath, "wb") as f:
                    f.write(image_data)
                
                logger.info(f"Image sauvegardée: {filepath}")
                return str(filepath)
            else:
                logger.warning("Impossible d'obtenir une image de la caméra")
                return None
        except Exception as e:
            logger.error(f"Erreur lors de la capture d'image: {e}")
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
                        
                    # Récupérer et sauvegarder l'image
                    await self.save_snapshot()

      
                self.last_state = motion_state
                self.last_animal = animal_state
                await asyncio.sleep(0.5)  # Pause de 500ms

        except Exception as e:
            logger.error(f"Erreur pendant la surveillance: {e}")
            raise

async def main():
    detector = CatDetector()
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