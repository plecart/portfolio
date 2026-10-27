"""Le stockage des fichiers téléversés — originaux, variantes, icônes —, choisi par `MEDIA_STORAGE`.

Le disque de Django sur le poste et dans les tests, Cloudflare R2 en production par
`django-storages` (ADR 0004). Le choix est une valeur d'`Env`, jamais une branche sur
l'environnement : modèles et tâches ne connaissent que le stockage de Django.
"""

from typing import Any

from config.env import Env


def media_storage(env: Env) -> dict[str, Any]:
    """L'entrée `default` de `STORAGES` que désigne `env.MEDIA_STORAGE`.

    Sous `r2`, le bucket public des images, joint par son API S3 : les adresses des fichiers sont
    celles du CDN devant lui, `https://<MEDIA_HOST>/<chemin>`, sans signature ; et un nom pris en
    rend un autre au lieu d'écraser l'objet — `django-storages` écrase par défaut.

    Args:
        env: l'environnement validé, qui porte sous `r2` chacune de ses variables (`Env`).

    Returns:
        Le `BACKEND`, et sous `r2` ses `OPTIONS`.
    """
    match env.MEDIA_STORAGE:
        case "disk":
            return {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        case "r2":
            return {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {
                    "endpoint_url": env.MEDIA_R2_ENDPOINT,
                    "bucket_name": env.MEDIA_R2_BUCKET,
                    "access_key": env.MEDIA_R2_ACCESS_KEY_ID,
                    "secret_key": env.MEDIA_R2_SECRET_ACCESS_KEY.get_secret_value(),
                    # La région d'un bucket R2 vue par l'API S3 (doc Cloudflare R2).
                    "region_name": "auto",
                    "custom_domain": env.MEDIA_HOST,
                    "file_overwrite": False,
                },
            }
