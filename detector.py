import os
import asyncio
import logging
from datetime import datetime
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
        self.channel = 0  # La plupart des caméras utilisent le canal 0

    async def connect(self):
        """Établit la connexion avec la caméra"""
        try:
            await self.api.get_host_data()
            await self.api.get_motion_state(self.channel)
            logger.info("Connexion à la caméra établie avec succès")
        except ReolinkError as e:
            logger.error(f"Erreur lors de la connexion à la caméra: {e}")
            raise

    async def start_monitoring(self):
        """Démarre la surveillance des événements de la caméra"""
        try:
            while True:
                # Vérification des événements toutes les 100ms
                motion_state = await self.api.get_motion_state(self.channel)
                
                # Si l'état a changé et qu'il y a du mouvement
                if motion_state != self.last_state and motion_state:
                    logger.info(f"Mouvement détecté ! Timestamp: {datetime.now()}")
                    # TODO: Ajouter ici la capture d'image et l'envoi à Gemini
                
                self.last_state = motion_state
                await asyncio.sleep(0.1)  # Pause de 100ms

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