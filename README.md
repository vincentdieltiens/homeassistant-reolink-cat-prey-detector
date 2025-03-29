# Détecteur de Chat

Un add-on Home Assistant pour détecter les chats et leurs proies en utilisant une caméra Reolink et l'API Google Gemini.

## Fonctionnalités

- Détection des chats grâce à la caméra Reolink
- Prise de photos en rafale lorsqu'un chat est détecté
- Analyse des images avec l'API Gemini pour identifier si le chat porte une proie
- Déclenchement d'automatisations Home Assistant selon les résultats
- Interface web pour visualiser les dernières images
- Traitement asynchrone des images pour ne pas ralentir la détection

## Configuration

| Option | Description |
|--------|-------------|
| `camera_ip` | Adresse IP de la caméra Reolink |
| `username` | Nom d'utilisateur pour la caméra |
| `password` | Mot de passe pour la caméra |
| `gemini_api_key` | Clé API pour Google Gemini |
| `save_images` | Sauvegarder les images (true/false) |
| `automation_with_prey` | ID de l'automatisation à déclencher quand un chat avec proie est détecté |
| `automation_without_prey` | ID de l'automatisation à déclencher quand un chat sans proie est détecté |
| `burst_count` | Nombre d'images à prendre en rafale (1-10) |
| `burst_interval` | Intervalle entre les images en secondes (0.1-1.0) |

## Fonctionnement du mode rafale

Le système fonctionne comme suit :
1. Quand un chat ou une personne est détecté par la caméra, le système prend plusieurs photos en rafale (configurable avec `burst_count`)
2. Ces images sont mises en file d'attente pour être analysées par Gemini en arrière-plan
3. Le système continue de surveiller immédiatement les nouveaux mouvements sans attendre l'analyse
4. Gemini analyse l'ensemble des images pour déterminer si un chat avec proie est présent
5. Si une proie est détectée, l'automatisation configurée est déclenchée

Ce mode de fonctionnement permet :
- D'augmenter les chances de capturer le chat avec sa proie clairement visible
- De ne pas ralentir la détection pour les mouvements suivants
- D'optimiser l'analyse en envoyant plusieurs images à Gemini en une seule fois

## Visualisation des images

L'interface web permet de voir les dernières images capturées et d'ouvrir chaque image en plein écran en cliquant dessus.

## Logs

Les logs sont disponibles dans `/share/cat_detector_logs.txt` et dans l'interface de logs de Home Assistant. 