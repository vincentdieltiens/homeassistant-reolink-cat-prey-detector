# Cat Prey Detector

Ce projet utilise une caméra Reolink pour détecter si un chat entre avec une proie via une chatière connectée, et verrouille la chatière si nécessaire.

## Prérequis

- Python 3.11 ou supérieur
- Une caméra Reolink (testée avec RLC-510A)
- Une chatière connectée SureFlap intégrée à Home Assistant
- Home Assistant

## Installation

1. Cloner le repository :
```bash
git clone https://github.com/votre-username/cat-prey-detector.git
cd cat-prey-detector
```

2. Créer un environnement virtuel et l'activer :
```bash
python3 -m venv venv
source venv/bin/activate  # Sur Linux/Mac
# ou
.\venv\Scripts\activate  # Sur Windows
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Configurer les variables d'environnement :
```bash
cp .env.example .env
```
Puis éditer le fichier `.env` avec vos informations.

## Utilisation

Pour lancer le détecteur :

```bash
python detector.py
```

## Structure du projet

- `detector.py` : Script principal de détection
- `requirements.txt` : Liste des dépendances Python
- `.env.example` : Exemple de configuration
- `.gitignore` : Fichiers à ignorer par Git

## Fonctionnement

1. Le script se connecte à la caméra Reolink
2. Il surveille en continu les mouvements détectés
3. Lorsqu'un mouvement est détecté, il capture une image
4. L'image est analysée par l'API Gemini pour détecter la présence d'une proie
5. Si une proie est détectée, la chatière est verrouillée via Home Assistant

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request. 